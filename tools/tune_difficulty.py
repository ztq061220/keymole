"""难度曲线校准器：让三种「人类」各跑若干局，看存活时间的中位数。

改完 keymole/core/game.py 的 Config 默认值后跑一遍：
    python tools/tune_difficulty.py
目标：菜鸟 ~35s、普通 ~65s、高手 ~100s，且三档拉得开。
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keymole.core.game import Config, Game          # noqa: E402
from keymole.core.layout import HOLE_CODES          # noqa: E402

# 每个「人」两组参数：s0/s1 = 开局/满难度时愿意出手的概率，r0/r1 = 反应时间
PERSONAS = {
    "菜鸟": dict(s0=0.92, s1=0.55, r0=0.34, r1=0.62),
    "普通": dict(s0=0.97, s1=0.72, r0=0.22, r1=0.42),
    "高手": dict(s0=0.995, s1=0.88, r0=0.14, r1=0.28),
}


def run(cfg: Config, persona: dict, seed: int, horizon: float = 300.0):
    rng = random.Random(seed)
    game = Game(HOLE_CODES, cfg, rng=rng)
    game.reset(0.0)
    t, pending = 0.0, []
    while game.running and t < horizon:
        t += 1.0 / 120.0
        d = game.difficulty()
        skill = persona["s0"] + (persona["s1"] - persona["s0"]) * d
        react = persona["r0"] + (persona["r1"] - persona["r0"]) * d
        for ev in game.update(t):
            if ev.kind == "spawn" and rng.random() < skill:
                pending.append((t + rng.uniform(react * 0.6, react * 1.5), ev.code))
        for item in list(pending):
            when, code = item
            if t >= when:
                pending.remove(item)
                if code in game.moles:
                    game.press(code, t)
    return t, game.score, game.level


def stat(cfg: Config, persona: dict, runs: int = 24):
    rows = [run(cfg, persona, s) for s in range(1, runs + 1)]
    surv = sorted(r[0] for r in rows)
    return dict(med=statistics.median(surv), lo=surv[1], hi=surv[-2],
                score=int(statistics.median([r[1] for r in rows])),
                level=int(statistics.median([r[2] for r in rows])))


def main() -> int:
    cfg = Config()
    print("当前 Config：lives=%d/%d level=%gs 出怪 %g→%g 停留 %g→%g ramp=%gs"
          % (cfg.lives, cfg.lives_max, cfg.level_seconds,
             cfg.spawn_interval_from, cfg.spawn_interval_to,
             cfg.life_from, cfg.life_to, cfg.ramp_seconds))
    for name, persona in PERSONAS.items():
        s = stat(cfg, persona)
        print("  %s  中位 %5.1fs (最快 %4.1f / 最慢 %5.1f)  %6d 分  等级 %d"
              % (name, s["med"], s["lo"], s["hi"], s["score"], s["level"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
