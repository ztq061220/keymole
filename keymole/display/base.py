"""显示后端的统一接口 + 能力分级。

核心思想：不要假设「点灯一定成功」。每个后端自己声明能控到哪一级，
游戏逻辑完全不关心 —— 它只管往一帧颜色里写，谁接得住谁接。
"""
from __future__ import annotations

import enum
import time
from typing import Dict, Iterable, Mapping, Sequence, Tuple

Rgb = Tuple[int, int, int]


class Tier(enum.IntEnum):
    OFF = 0        # 完全控不了灯，只有屏幕
    WHOLE = 1      # 整块键盘一个颜色
    ZONES = 2      # 能分区
    PER_KEY = 3    # 能逐键


class Display:
    """一个「显示目标」。子类实现 _commit()。"""

    name: str = "base"
    tier: Tier = Tier.OFF
    refresh_hz: float = 30.0

    def __init__(self) -> None:
        self._next_ok = 0.0
        self.errors = 0

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def supported_keys(self) -> Sequence[str]:
        return ()

    def offer(self, frame: Mapping[str, Rgb], now: float) -> bool:
        """节流入口：到点了就提交，没到点直接丢掉这一帧。

        注意这里是「丢帧」而不是「排队」—— 真实键盘固件可能只有 20~30Hz，
        排队会让延迟越堆越高，出现「按了键、灯半秒后才亮」的致命体验。
        """
        if now < self._next_ok:
            return False
        self._next_ok = now + 1.0 / max(self.refresh_hz, 1e-6)
        try:
            self._commit(frame)
            return True
        except Exception as exc:  # 后端挂了不能拖死游戏
            self.errors += 1
            if self.errors <= 3:
                print(f"[display:{self.name}] commit 失败: {exc!r}")
            return False

    def flush(self, frame: Mapping[str, Rgb], now: float = 0.0) -> None:
        """无视节流立刻提交这一帧（截图 / 自测用，正常循环请用 offer）。"""
        self._next_ok = 0.0
        self.offer(frame, now)

    def _commit(self, frame: Mapping[str, Rgb]) -> None:
        raise NotImplementedError


class Fanout(Display):
    """把同一帧同时喂给多个后端（屏幕 + 真键盘）。"""

    def __init__(self, displays: Iterable[Display]) -> None:
        super().__init__()
        self.displays = list(displays)
        self.name = "+".join(d.name for d in self.displays) or "none"
        self.tier = max((d.tier for d in self.displays), default=Tier.OFF)
        self.refresh_hz = max((d.refresh_hz for d in self.displays), default=30.0)

    def open(self) -> None:
        for d in self.displays:
            try:
                d.open()
            except Exception as exc:
                print(f"[display:{d.name}] open 失败: {exc!r}")

    def close(self) -> None:
        for d in self.displays:
            try:
                d.close()
            except Exception:
                pass

    def flush(self, frame: Mapping[str, Rgb], now: float = 0.0) -> None:
        for d in self.displays:
            d.flush(frame, now)

    def _commit(self, frame: Mapping[str, Rgb]) -> None:
        now = time.perf_counter()
        for d in self.displays:
            d.offer(frame, now)
