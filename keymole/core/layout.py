"""物理键位表（60% 主键区）。

坐标单位是「键宽」(1U = 1 个标准键)，左上角为原点。
这张表是整个项目唯一的几何真相：游戏用 code 描述洞位，屏幕用它画键盘，
真实键盘后端用它把 LED 的物理坐标对回逻辑键。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Key:
    code: str      # 逻辑键 id，如 "a" / "tab" / "lshift"
    label: str     # 画在键帽上的字
    x: float       # 左边缘，单位 U
    y: float       # 上边缘，单位 U
    w: float = 1.0

    @property
    def right(self) -> float:
        return self.x + self.w


# 每行：(y, [(code, label, width), ...])，每行总宽度都必须是 15U
_ROWS = [
    (0.0, [
        ("grave", "`", 1), ("1", "1", 1), ("2", "2", 1), ("3", "3", 1),
        ("4", "4", 1), ("5", "5", 1), ("6", "6", 1), ("7", "7", 1),
        ("8", "8", 1), ("9", "9", 1), ("0", "0", 1), ("minus", "-", 1),
        ("equal", "=", 1), ("backspace", "⌫", 2),
    ]),
    (1.0, [
        ("tab", "Tab", 1.5),
        ("q", "Q", 1), ("w", "W", 1), ("e", "E", 1), ("r", "R", 1), ("t", "T", 1),
        ("y", "Y", 1), ("u", "U", 1), ("i", "I", 1), ("o", "O", 1), ("p", "P", 1),
        ("lbracket", "[", 1), ("rbracket", "]", 1), ("backslash", "\\", 1.5),
    ]),
    (2.0, [
        ("capslock", "Caps", 1.75),
        ("a", "A", 1), ("s", "S", 1), ("d", "D", 1), ("f", "F", 1), ("g", "G", 1),
        ("h", "H", 1), ("j", "J", 1), ("k", "K", 1), ("l", "L", 1),
        ("semicolon", ";", 1), ("quote", "'", 1), ("enter", "Enter", 2.25),
    ]),
    (3.0, [
        ("lshift", "Shift", 2.25),
        ("z", "Z", 1), ("x", "X", 1), ("c", "C", 1), ("v", "V", 1), ("b", "B", 1),
        ("n", "N", 1), ("m", "M", 1), ("comma", ",", 1), ("period", ".", 1),
        ("slash", "/", 1), ("rshift", "Shift", 2.75),
    ]),
    (4.0, [
        ("lctrl", "Ctrl", 1.25), ("lwin", "Win", 1.25), ("lalt", "Alt", 1.25),
        ("space", "", 6.25),
        ("ralt", "Alt", 1.25), ("rwin", "Win", 1.25), ("menu", "Menu", 1.25),
        ("rctrl", "Ctrl", 1.25),
    ]),
]


def _build() -> List[Key]:
    keys: List[Key] = []
    for y, row in _ROWS:
        x = 0.0
        for code, label, w in row:
            keys.append(Key(code=code, label=label, x=x, y=y, w=float(w)))
            x += w
    return keys


KEYBOARD: List[Key] = _build()
BY_CODE: Dict[str, Key] = {k.code: k for k in KEYBOARD}

WIDTH_U: float = max(k.right for k in KEYBOARD)   # 15.0
HEIGHT_U: float = max(k.y for k in KEYBOARD) + 1.0  # 5.0

# 洞位池：左手三行，15 个键。只玩固定这些键是「适配大部分键盘」的关键——
# 适配成本从「支持全键盘所有键」降到「在这 15 个位置找到 LED 就行」。
HOLE_ROWS = [
    ("q", "w", "e", "r", "t"),
    ("a", "s", "d", "f", "g"),
    ("z", "x", "c", "v", "b"),
]
HOLE_ROWS_RIGHT = (
    ("y", "u", "i", "o", "p"),
    ("h", "j", "k", "l", "semicolon"),
    ("n", "m", "comma", "period", "slash"),
)

HOLE_CODES_RIGHT = tuple(code for row in HOLE_ROWS_RIGHT for code in row)

HAND_SETS = {
    "left": tuple(code for row in HOLE_ROWS for code in row),
    "right": HOLE_CODES_RIGHT,
    "both": tuple(code for row in HOLE_ROWS for code in row) + HOLE_CODES_RIGHT,
}

HAND_LABEL = {"left": "左手", "right": "右手", "both": "双手"}

HOLE_CODES: List[str] = [c for row in HOLE_ROWS for c in row]

# tkinter keysym -> 逻辑键 code
TK_KEYSYM: Dict[str, str] = {
    "grave": "grave", "minus": "minus", "equal": "equal", "backspace": "backspace",
    "tab": "tab", "bracketleft": "lbracket", "bracketright": "rbracket",
    "backslash": "backslash", "caps_lock": "capslock", "semicolon": "semicolon",
    "apostrophe": "quote", "return": "enter", "kp_enter": "enter",
    "shift_l": "lshift", "shift_r": "rshift",
    "comma": "comma", "period": "period", "slash": "slash",
    "control_l": "lctrl", "control_r": "rctrl",
    "alt_l": "lalt", "alt_r": "ralt",
    "win_l": "lwin", "win_r": "rwin", "super_l": "lwin", "super_r": "rwin",
    "menu": "menu", "space": "space",
}


def code_from_keysym(keysym: str) -> Optional[str]:
    """把 tkinter 的 keysym 归一化成逻辑键 code，认不出就返回 None。"""
    if not keysym:
        return None
    low = keysym.lower()
    if low in TK_KEYSYM:
        return TK_KEYSYM[low]
    if low in BY_CODE:            # 字母 / 数字
        return low
    return None
