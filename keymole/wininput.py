"""Windows 输入层：绕开中文输入法，直接问系统「这个键现在按着没有」。

中文输入法激活时，按键会被 IME 吃掉（进到候选框），tkinter 的 <KeyPress>
可能收不到。两条对策一起上：

1. disable_ime(hwnd)：把这个窗口的 IME 上下文摘掉（ImmAssociateContext(hwnd, NULL)），
   窗口内不再触发输入法。
2. KeyPoller：用 GetAsyncKeyState 轮询硬件按键状态，完全绕过 IME 和焦点转发，
   只要窗口在前台就能判定「刚按下」。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
imm32 = ctypes.WinDLL("imm32", use_last_error=True)

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wintypes.HWND
imm32.ImmAssociateContext.argtypes = [wintypes.HWND, ctypes.c_void_p]
imm32.ImmAssociateContext.restype = ctypes.c_void_p

VK_ESCAPE = 0x1B
VK_F5 = 0x74
VK_SPACE = 0x20
VK_RETURN = 0x0D
GA_ROOT = 2


def root_hwnd(widget_id: int) -> int:
    """tkinter 的 winfo_id() 给的是子窗口，IME 上下文挂在顶层窗口上。"""
    h = user32.GetAncestor(wintypes.HWND(widget_id), GA_ROOT)
    return int(h) if h else int(widget_id)


def disable_ime(hwnd: int) -> bool:
    """摘掉这个窗口的输入法上下文：窗口内打字不再进 IME。"""
    try:
        imm32.ImmAssociateContext(wintypes.HWND(hwnd), None)
        return True
    except Exception:
        return False


def key_down(vk: int) -> bool:
    """不管窗口有没有焦点，直接问系统这个键现在是按下状态吗。"""
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def foreground() -> int:
    try:
        return int(user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def _down(vk: int) -> bool:
    return (user32.GetAsyncKeyState(vk) & 0x8000) != 0


class KeyPoller:
    """轮询一组虚拟键，返回「本帧新按下」的键码。"""

    def __init__(self, codes):
        self.vk = {}
        for code in codes:
            if len(code) == 1 and code.isalpha():
                self.vk[ord(code.upper())] = code
        self.down = set()

    def poll(self):
        hit = []
        for vk, code in self.vk.items():
            if _down(vk):
                if vk not in self.down:
                    self.down.add(vk)
                    hit.append(code)
            elif vk in self.down:
                self.down.discard(vk)
        return hit

    def escape(self) -> bool:
        return _down(VK_ESCAPE)

    def enter(self) -> bool:
        return _down(VK_RETURN)

    def _once(self, vk: int) -> bool:
        if _down(vk):
            if vk not in self.down:
                self.down.add(vk)
                return True
        elif vk in self.down:
            self.down.discard(vk)
        return False

    def f5(self) -> bool:
        return self._once(VK_F5)

    def space(self) -> bool:
        return self._once(VK_SPACE)


    def clear(self) -> None:
        self.down.clear()
