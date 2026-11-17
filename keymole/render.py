"""把游戏状态渲染成一帧颜色：{逻辑键 code: (r, g, b)}。

这是 core 和 display 之间唯一的契约。屏幕后端把这帧画成键盘，
真实键盘后端把这帧按坐标/名字映射到 LED。两者吃的是同一份数据，
所以「屏幕预览」和「真机灯效」不会走样。
"""
from __future__ import annotations

import math
from typing import Dict

from .core.game import Game
from .core.layout import KEYBOARD

Rgb = tuple

# 主题（同时也是真实键盘上会显示的颜色，所以别用太亮的底色）
OFF    = (16, 18, 24)    # 没参与游戏的键
HOLE   = (34, 42, 64)    # 空洞位（暗蓝，能看出「这里是个洞」）
AMBER  = (255, 24, 16)   # 地鼠：高亮正红（用户要求）
DANGER = (255, 24, 16)   # 地鼠快跑了：同色，改用闪烁表达紧迫
HIT    = (48, 255, 120)
MISS   = (255, 48, 48)
WRONG  = (64, 120, 255)
DEAD   = (120, 20, 24)   # 游戏结束


def mix(a, b, t: float):
    t = min(1.0, max(0.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def build_frame(game: Game, now: float) -> Dict[str, Rgb]:
    frame: Dict[str, Rgb] = {k.code: OFF for k in KEYBOARD}

    if game.over:
        # 结束后先红闪 0.6 秒做提示，然后整块键盘归零 —— 用户明确要求「每把结束重置」
        if now - getattr(game, "over_at", 0.0) < 0.6:
            pulse = 0.55 + 0.45 * abs(math.sin(now * 3.0))
            for code in game.holes:
                frame[code] = mix(OFF, DEAD, pulse)
            return frame
        return {code: (0, 0, 0) for code in frame}

    for code in game.holes:
        frame[code] = HOLE

    for code, mole in game.moles.items():
        frac = mole.remaining(now)        # 0..1：1=刚冒头，0=要跑了
        # 每只地鼠相位错开，避免整屏同步呼吸
        pulse = 1.0   # 不再呼吸：键盘每包 8ms，帧帧都变会让更新排队变慢
        # 亮度随剩余寿命衰减 + 最后 45% 往红色走：用颜色教玩家「要来不及了」
        dim = 1.0 * pulse
        # 最后 35% 寿命改为快闪（不再用偏黄的渐变色，那会被看成橙色）
        blink = 1.0
        if frac < 0.35 and int(now * 8.0) % 2 == 0:
            blink = 0.15
        rgb = mix(AMBER, DANGER, 0.0)
        frame[code] = tuple(int(max(0, min(255, c * dim * blink))) for c in rgb)

    for code, (rgb, until) in list(game.flashes.items()):
        if now >= until:
            game.flashes.pop(code, None)
            continue
        fade = min(1.0, (until - now) / 0.12)
        frame[code] = mix(frame.get(code, OFF), rgb, 0.35 + 0.65 * fade)

    return frame
