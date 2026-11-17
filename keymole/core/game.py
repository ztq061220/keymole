"""打地鼠的游戏内核 —— 纯逻辑，不 import 任何 GUI / 硬件库。

时间全部由外部传入（`now`，单位秒），这样同一份逻辑既能跑在 tkinter 里，
也能被无头模拟器批量跑，用来调难度曲线。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Rgb = Tuple[int, int, int]


@dataclass
class Config:
    lives: int = 4
    lives_max: int = 7        # 回血上限（每升一级 +1 命）
    spawn_first: float = 1.20         # 第一只地鼠出现前的准备时间
    spawn_interval_from: float = 1.05  # 开局出怪间隔
    spawn_interval_to: float = 0.30    # 满难度出怪间隔
    life_from: float = 1.55            # 开局地鼠停留时间
    life_to: float = 0.45              # 满难度停留时间
    max_active_from: int = 1           # 开局同屏地鼠数
    max_active_to: int = 4
    ramp_seconds: float = 130.0        # 从最易到最难的爬坡时长
    level_seconds: float = 15.0
    wrong_penalty: int = 25
    hit_base: int = 100
    hit_speed_bonus: int = 80
    combo_step: float = 0.10           # 每连击 +10%
    combo_max_mult: float = 3.0
    flash_seconds: float = 0.24


@dataclass
class Mole:
    code: str
    born: float
    life: float

    @property
    def die_at(self) -> float:
        return self.born + self.life

    def remaining(self, now: float) -> float:
        return max(0.0, (self.die_at - now) / max(self.life, 1e-6))


@dataclass
class Event:
    kind: str          # spawn | hit | miss | wrong | gameover
    code: str = ""
    value: int = 0     # 本次得分，仅 hit 有意义


class Game:
    def __init__(self, holes: Sequence[str], config: Optional[Config] = None,
                 rng: Optional[random.Random] = None) -> None:
        self.holes: List[str] = list(holes)
        self.cfg: Config = config or Config()
        self.rng: random.Random = rng or random.Random()
        self.flashes: Dict[str, List] = {}
        self.reset(0.0)

    # ---------- 生命周期 ----------

    def reset(self, now: float) -> None:
        self.moles: Dict[str, Mole] = {}
        self.flashes: Dict[str, List] = {}
        self.score = 0
        self.combo = 0
        self.best_combo = 0
        self.lives = self.cfg.lives
        self._last_level = 1
        self.hits = 0
        self.misses = 0
        self.wrongs = 0
        self.started_at = now
        self.now = now
        self.next_spawn = now + self.cfg.spawn_first
        self.running = True
        self.over = False
        self.over_at = 0.0

    def shift(self, dt: float) -> None:
        """把整局的时间轴整体往后推 dt 秒（窗口失焦暂停用）。

        做法是平移所有时间戳，而不是「停止计时」—— 这样地鼠的剩余寿命、
        出怪节奏、等级进度都会原样保留，回来接着玩。
        """
        if dt <= 0:
            return
        self.started_at += dt
        self.now += dt
        self.next_spawn += dt
        for mole in self.moles.values():
            mole.born += dt
        for flash in self.flashes.values():
            flash[1] += dt

    # ---------- 难度 ----------

    @property
    def elapsed(self) -> float:
        return self.now - self.started_at

    @property
    def level(self) -> int:
        return 1 + int(max(0.0, self.elapsed) // self.cfg.level_seconds)

    @property
    def accuracy(self) -> float:
        total = self.hits + self.misses + self.wrongs
        return self.hits / total if total else 1.0

    def difficulty(self) -> float:
        """0 = 开局最易，1 = 满难度。"""
        return min(1.0, max(0.0, self.elapsed / max(self.cfg.ramp_seconds, 1e-6)))

    @staticmethod
    def _lerp(a: float, b: float, d: float) -> float:
        return a + (b - a) * d

    def spawn_interval(self) -> float:
        return self._lerp(self.cfg.spawn_interval_from, self.cfg.spawn_interval_to,
                          self.difficulty() ** 0.8)

    def mole_life(self) -> float:
        return self._lerp(self.cfg.life_from, self.cfg.life_to,
                          self.difficulty() ** 0.9)

    def max_active(self) -> int:
        return int(round(self._lerp(self.cfg.max_active_from, self.cfg.max_active_to,
                                    self.difficulty() ** 1.2)))

    # ---------- 每帧推进 ----------

    def update(self, now: float) -> List[Event]:
        self.now = now
        out: List[Event] = []
        if not self.running:
            return out

        # 0) 升级 —— 每升一级回 1 条命。只扣命不回血的话，一局撑不过半分钟。
        lvl = self.level
        if lvl > self._last_level:
            self._last_level = lvl
            self.lives = min(self.cfg.lives_max, self.lives + 1)
            out.append(Event("levelup", "", lvl))

        # 1) 超时的地鼠 —— 扣命
        for code, mole in list(self.moles.items()):
            if now >= mole.die_at:
                del self.moles[code]
                self.misses += 1
                self.combo = 0
                self.lives -= 1
                self._flash(code, (255, 48, 48), now)
                out.append(Event("miss", code))
                if self.lives <= 0:
                    self.lives = 0
                    self.running = False
                    self.over = True
                    self.over_at = now
                    out.append(Event("gameover"))
                    return out

        # 2) 生成新地鼠 —— 不排队：落后太多就重新对齐，绝不一次补生成一堆
        guard = 0
        while now >= self.next_spawn and len(self.moles) < self.max_active() and guard < 8:
            guard += 1
            code = self._pick()
            if code is None:
                break
            self.moles[code] = Mole(code, now, self.mole_life())
            out.append(Event("spawn", code))
            self.next_spawn += self.spawn_interval()
        if self.next_spawn < now:
            self.next_spawn = now + self.spawn_interval() * 0.5
        return out

    def _pick(self) -> Optional[str]:
        free = [c for c in self.holes if c not in self.moles]
        if not free:
            return None
        return self.rng.choice(free)

    # ---------- 输入 ----------

    def press(self, code: str, now: float) -> List[Event]:
        self.now = now
        out: List[Event] = []
        if not self.running or code not in self.holes:
            return out       # 打到洞位以外的键不算失误，否则手放着都会扣分

        mole = self.moles.pop(code, None)
        if mole is not None:
            remain = mole.remaining(now)
            mult = min(self.cfg.combo_max_mult, 1.0 + self.combo * self.cfg.combo_step)
            pts = int((self.cfg.hit_base + self.cfg.hit_speed_bonus * remain) * mult)
            self.score += pts
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
            self.hits += 1
            self._flash(code, (48, 255, 120), now)
            out.append(Event("hit", code, pts))
        else:
            # 打在空位上 —— 打地鼠的灵魂惩罚
            self.combo = 0
            self.wrongs += 1
            self.score = max(0, self.score - self.cfg.wrong_penalty)
            if code:
                self._flash(code, (64, 120, 255), now)
            out.append(Event("wrong", code))
        return out

    def _flash(self, code: str, rgb: Rgb, now: float) -> None:
        self.flashes[code] = [rgb, now + self.cfg.flash_seconds]
