"""分区降级：把「一帧逐键颜色」压成「几个区的颜色」。

为什么必须有这一层：市面上一大半带灯键盘只能整块或分区亮。
地鼠在哪个区、就让哪个区亮 —— 玩家至少知道往哪边看。
这比「什么都不亮」强，比「逐键」差，但它把 L1/L2 的键盘救活了。
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence, Tuple

from .base import Display, Tier

Rgb = Tuple[int, int, int]

# 优先级：地鼠 > 命中 > 误按 > 暗色/空洞。
# 地鼠最高，因为「哪儿有地鼠」是玩家唯一必须知道的信息。
_RANK_MOLE, _RANK_HIT, _RANK_WRONG, _RANK_DIM, _RANK_OFF = 4, 3, 2, 1, 0


def classify(rgb: Rgb) -> int:
    """把一帧里的颜色归类，用来决定分区聚合时谁说了算。"""
    r, g, b = rgb
    if r > 120 and b < 90:          # 琥珀/红：地鼠（含快跑了的红）
        return _RANK_MOLE
    if g > 150 and r < 130:         # 绿：命中闪
        return _RANK_HIT
    if b > 150 and r < 110:         # 蓝：误按闪
        return _RANK_WRONG
    if max(rgb) > 90:               # 空洞底色
        return _RANK_DIM
    return _RANK_OFF


def aggregate(frame: Mapping[str, Rgb], codes: Iterable[str]) -> Rgb:
    """一个区显示什么颜色：取该区里「最要紧」的那个格子的颜色。"""
    best: Rgb = (0, 0, 0)
    best_rank = -1
    best_sum = -1
    for code in codes:
        rgb = frame.get(code)
        if not rgb:
            continue
        rank = classify(tuple(rgb))
        total = sum(rgb)
        if rank > best_rank or (rank == best_rank and total > best_sum):
            best, best_rank, best_sum = tuple(rgb), rank, total
    return best  # type: ignore[return-value]


# 三种常见分区形态。品牌键盘里 4 分区/单区最多，所以提供 5 列、3 列、3 行、整块。
ZONE_LAYOUTS = {
    "cols5": (("q", "a", "z"), ("w", "s", "x"), ("e", "d", "c"), ("r", "f", "v"), ("t", "g", "b")),
    "cols3": (("q", "w", "a", "s", "z", "x"), ("e", "d", "c"), ("r", "t", "f", "g", "v", "b")),
    "rows3": (("q", "w", "e", "r", "t"), ("a", "s", "d", "f", "g"), ("z", "x", "c", "v", "b")),
    "whole": (("q", "w", "e", "r", "t", "a", "s", "d", "f", "g", "z", "x", "c", "v", "b"),),
}


class ZoneDisplay(Display):
    """只能分区/整块亮的后端基类：子类实现 _paint(colors)。"""

    tier = Tier.ZONES
    layout = "cols5"

    def __init__(self) -> None:
        super().__init__()
        self.zones: Sequence[Sequence[str]] = ZONE_LAYOUTS[self.layout]

    def _commit(self, frame: Mapping[str, Rgb]) -> None:
        self._paint([aggregate(frame, z) for z in self.zones])

    def _paint(self, colors: Sequence[Rgb]) -> None:
        raise NotImplementedError


class WholeDisplay(ZoneDisplay):
    """整块键盘只有一个颜色。打地鼠只能当「命中/失误」的氛围灯。"""

    tier = Tier.WHOLE
    layout = "whole"
