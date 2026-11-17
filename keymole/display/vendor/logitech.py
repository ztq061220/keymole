"""罗技：Logitech LED Illumination SDK（G HUB / LGS 自带的 DLL）。

为什么值得单独做：罗技是市占最高的 RGB 键盘品牌之一，而它的 SDK
**随 G HUB 一起装机，用户不用额外装任何东西**，比 OpenRGB 还省事。

按键编号不是「键名」，是 USB HID 之前的 set-1 扫描码（Q=0x10、A=0x1E、Z=0x2C），
这份表取自官方 LogitechLEDLib.h（Delphi 翻译版逐行核对过），不是猜的。
"""
from __future__ import annotations

import ctypes
import os
import winreg
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..base import Display, Tier

Rgb = Tuple[int, int, int]

# 15 个洞位对应的罗技键码
KEY = {
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30,
}

DLL_NAMES = (
    "sdk_legacy_led_x64.dll",       # G HUB 里的实际文件名
    "LogitechLedEnginesWrapper.dll",  # 老版 LGS 的名字
    "LogitechLed.dll",
)

_SEARCH_DIRS = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LGHUB" / "sdks",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "LGHUB" / "sdks",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Logitech Gaming Software",
    Path(os.environ.get("ProgramW6432", r"C:\Program Files")) / "LGHUB" / "sdks",
    Path(r"C:\Windows\System32"),
)


def find_dll() -> Optional[Path]:
    for d in _SEARCH_DIRS:
        for name in DLL_NAMES:
            p = d / name
            try:
                if p.is_file():
                    return p
            except OSError:
                continue
    return None


def _has_device() -> bool:
    """注册表里有没有 VID_046D 的 HID 设备。比真 init 快，也不用碰灯。"""
    base = r"SYSTEM\CurrentControlSet\Enum\HID"
    try:
        hk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return False
    n = winreg.QueryInfoKey(hk)[0]
    for i in range(n):
        name = winreg.EnumKey(hk, i).upper()
        if "VID_046D" in name:
            return True
    return False


def probe() -> Tuple[bool, str]:
    p = find_dll()
    if p is None:
        return False, "没找到罗技 LED SDK（装 G HUB 后位于 LGHUB\sdks\）"
    if not _has_device():
        return False, "SDK 已装（%s），但没插罗技设备" % p.name
    try:
        dll = ctypes.WinDLL(str(p))
        dll.LogiLedInit.restype = ctypes.c_bool
        dll.LogiLedInit.argtypes = []
        if not dll.LogiLedInit():
            return False, "SDK 在，但 LogiLedInit 失败（G HUB 没运行？）"
        dll.LogiLedShutdown()
        return True, "已连接：%s" % p.name
    except Exception as exc:
        return False, "SDK 调用失败：%r" % (exc,)


class LogitechDisplay(Display):
    """逐键点亮（G Pro / G915 / G512 等支持 PER_KEY 的型号）。

    只有分区灯效的老型号（G213 等）会退化到「就近分区」，效果是 L2，不是 L3。
    """

    name = "logitech"
    tier = Tier.PER_KEY
    refresh_hz = 25.0          # SDK 调用是同步 IPC，别打太快

    def __init__(self, dll_path: Optional[Path] = None) -> None:
        super().__init__()
        self.dll_path = dll_path or find_dll()
        self.dll = None
        self._init_ok = False

    def open(self) -> None:
        if self.dll_path is None:
            raise RuntimeError("罗技 LED SDK 不存在")
        self.dll = ctypes.WinDLL(str(self.dll_path))
        for fn in ("LogiLedInit", "LogiLedSetLightingForKeyWithKeyName", "LogiLedShutdown"):
            if not hasattr(self.dll, fn):
                raise RuntimeError("SDK 缺少导出函数 %s（版本太老）" % fn)

        self.dll.LogiLedInit.restype = ctypes.c_bool
        self.dll.LogiLedInit.argtypes = []
        if not self.dll.LogiLedInit():
            raise RuntimeError("LogiLedInit 失败：G HUB 没运行，或者没插罗技键盘")
        if hasattr(self.dll, "LogiLedSetTargetDevice"):
            self.dll.LogiLedSetTargetDevice.argtypes = [ctypes.c_int]
            self.dll.LogiLedSetTargetDevice(0)      # 0 = LOGI_DEVICETYPE_ALL
        if hasattr(self.dll, "LogiLedSaveCurrentLighting"):
            self.dll.LogiLedSaveCurrentLighting()

        self.dll.LogiLedSetLightingForKeyWithKeyName.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        if hasattr(self.dll, "LogiLedSetLightingForKeyWithKeyName"):
            pass
        self._init_ok = True

    def _commit(self, frame: Dict[str, Rgb]) -> None:  # type: ignore[override]
        fn = self.dll.LogiLedSetLightingForKeyWithKeyName
        for code, (r, g, b) in frame.items():
            key = KEY.get(code)
            if key is None:
                continue
            fn(key, int(r), int(g), int(b))

    def close(self) -> None:
        if self.dll is None:
            return
        try:
            if hasattr(self.dll, "LogiLedRestoreLighting"):
                self.dll.LogiLedRestoreLighting()
            self.dll.LogiLedShutdown()
        except Exception:
            pass
        self.dll = None


def make() -> Display:
    return LogitechDisplay()
