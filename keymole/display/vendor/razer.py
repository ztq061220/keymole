"""雷蛇：Razer Chroma SDK（随 Synapse 安装）。

逐键用 CHROMA_CUSTOM_KEY 效果：Color 是底色，Key 是逐键覆盖（0 表示「用底色」）。
网格是 6 行 × 22 列，字母区从第 2 列开始（左侧有 Tab/Caps/Shift 占位）。

注意：这张 (row, col) 表是业界通用的 Chroma 键盘网格，但**没有在真机上验证过**——
本机没装 Synapse。若发现点亮了相邻的键，用 `python -m keymole.selftest razer`
逐个点亮核对，改 GRID 即可。
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Optional, Tuple

from ..base import Display, Tier

Rgb = Tuple[int, int, int]

GRID = {
    "q": (2, 2), "w": (2, 3), "e": (2, 4), "r": (2, 5), "t": (2, 6),
    "a": (3, 2), "s": (3, 3), "d": (3, 4), "f": (3, 5), "g": (3, 6),
    "z": (4, 2), "x": (4, 3), "c": (4, 4), "v": (4, 5), "b": (4, 6),
}

RZMAXROW, RZMAXCOL = 6, 22
CHROMA_CUSTOM_KEY = 5

_SEARCH = (
    Path(r"C:\Windows\System32"),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Razer Chroma SDK" / "bin",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Razer" / "Chroma SDK" / "bin",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Razer Chroma SDK" / "bin",
)


class _CustomKey(ctypes.Structure):
    _fields_ = [("Color", (ctypes.c_uint32 * RZMAXCOL) * RZMAXROW),
                ("Key", (ctypes.c_uint32 * RZMAXCOL) * RZMAXROW)]


def find_dll() -> Optional[Path]:
    for d in _SEARCH:
        for name in ("RzChromaSDK64.dll", "RzChromaSDK.dll"):
            p = d / name
            try:
                if p.is_file():
                    return p
            except OSError:
                continue
    return None


def probe() -> Tuple[bool, str]:
    """DLL 在不等于能用 —— 必须真 Init 一次（Synapse 没跑会直接失败）。"""
    p = find_dll()
    if p is None:
        return False, "没找到 Chroma SDK（装 Razer Synapse 后会有 RzChromaSDK64.dll）"
    try:
        dll = ctypes.WinDLL(str(p))
        rc = ctypes.c_long(dll.Init()).value
        if rc != 0:
            return False, "SDK 在，但 Init 返回 0x%08X（Synapse 没运行？）" % (rc & 0xFFFFFFFF)
        dll.UnInit()
        return True, "SDK 就绪：%s" % p.name
    except OSError as exc:
        return False, "DLL 加载失败：%s" % exc


class RazerDisplay(Display):
    name = "razer"
    tier = Tier.PER_KEY
    refresh_hz = 20.0

    def __init__(self, dll_path: Optional[Path] = None) -> None:
        super().__init__()
        self.dll_path = dll_path or find_dll()
        self.dll = None

    def open(self) -> None:
        if self.dll_path is None:
            raise RuntimeError("Chroma SDK 不存在")
        self.dll = ctypes.WinDLL(str(self.dll_path))
        self.dll.Init.restype = ctypes.c_long
        self.dll.CreateKeyboardEffect.restype = ctypes.c_long
        self.dll.CreateKeyboardEffect.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        rc = self.dll.Init()
        if rc != 0:
            raise RuntimeError("Chroma Init 返回 %d：Synapse 没运行？" % rc)

    def _commit(self, frame) -> None:  # type: ignore[override]
        eff = _CustomKey()
        for code, (r, g, b) in frame.items():
            pos = GRID.get(code)
            if pos is None:
                continue
            row, col = pos
            eff.Key[row][col] = (int(b) << 16) | (int(g) << 8) | int(r)   # 0x00BBGGRR
        rc = self.dll.CreateKeyboardEffect(CHROMA_CUSTOM_KEY, ctypes.byref(eff), None)
        if rc != 0:
            raise RuntimeError("CreateKeyboardEffect 返回 %d" % rc)

    def close(self) -> None:
        if self.dll is not None:
            try:
                self.dll.UnInit()
            except Exception:
                pass
            self.dll = None


def make() -> Display:
    return RazerDisplay()
