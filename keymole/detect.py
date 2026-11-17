"""能力探测：这台机器上的键盘，到底能控到哪一级？

设计原则：**探测不到的绝不假装成功**。启动时明确告诉用户「你的键盘支持到 L?」，
比默默闪两下不亮强一百倍。

探测顺序 = 覆盖广度顺序，也是「用户要装多少东西」从少到多：
  1. 厂商 SDK（罗技/雷蛇）—— 用户本来就有 G HUB / Synapse
  2. OpenRGB SDK —— 上百品牌、六百多型号，要用 KeyMole 一键装
  3. Win11 HID LampArray —— 新标准，无需装任何东西（本版只探测不控制）
  4. 屏幕 —— 永远可用
"""
from __future__ import annotations

import importlib.util
import os
import re
import socket
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .display.base import Display, Tier

OPENRGB_HOST = "127.0.0.1"
OPENRGB_PORT = 6742

TIER_LABEL = {
    Tier.OFF: "L0 只有屏幕",
    Tier.WHOLE: "L1 整块单色",
    Tier.ZONES: "L2 分区",
    Tier.PER_KEY: "L3 逐键",
}

_PREF_MIN = {"whole": Tier.WHOLE, "zones": Tier.ZONES, "perkey": Tier.PER_KEY}


@dataclass
class Backend:
    key: str
    title: str
    tier: Tier
    ok: bool
    detail: str
    make: Optional[Callable[[], Display]] = None
    install_hint: str = ""


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------- 厂商 SDK ----------------

def _vendor_backend(key: str, title: str) -> Backend:
    try:
        mod = importlib.import_module("keymole.display.vendor.%s" % key)
    except Exception as exc:                       # 模块本身坏了也不能拖死探测
        return Backend(key, title, Tier.PER_KEY, False, "后端加载失败：%r" % (exc,))
    try:
        ok, detail = mod.probe()
    except Exception as exc:
        ok, detail = False, "探测失败：%r" % (exc,)
    return Backend(key, title, Tier.PER_KEY, ok, detail, mod.make if ok else None)


# ---------------- OpenRGB ----------------

def _openrgb_backend() -> Backend:
    """OpenRGB 通道：客户端是我们自己实现的，所以只差「服务器有没有跑」。"""
    from .setup_openrgb import find_exe
    hint = "一键装好并启动：python -m keymole.setup_openrgb --start"
    if _port_open(OPENRGB_HOST, OPENRGB_PORT):
        from .display.openrgb import OpenRGBDisplay
        return Backend("openrgb", "OpenRGB 通道", Tier.PER_KEY, True,
                       "在线 · 覆盖六百多型号，开游戏时自动判定逐键/分区（127.0.0.1:%d）"
                       % OPENRGB_PORT, OpenRGBDisplay)
    exe = find_exe()
    state = "已下载但没启动" if exe else "还没下载"
    return Backend("openrgb", "OpenRGB 通道", Tier.PER_KEY, False,
                   "服务器没在跑（%s:%d 无响应，%s）" % (OPENRGB_HOST, OPENRGB_PORT, state),
                   None, hint)


# ---------------- Windows 11 HID LampArray（新标准）----------------

def lamp_array_devices() -> List[str]:
    """扫注册表找 HID usage page 0x59（Lighting And Illumination）的设备。

    Windows 11 的「动态光效」就靠这个：符合标准的键盘，系统原生就能点灯，
    不用装任何厂商软件。这是未来两年覆盖面会涨得最快的一条路。
    """
    found: List[str] = []
    base = r"SYSTEM\CurrentControlSet\Enum\HID"
    try:
        hk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return found
    for i in range(winreg.QueryInfoKey(hk)[0]):
        inst = winreg.EnumKey(hk, i)
        try:
            dev = winreg.OpenKey(hk, inst)
            sub = winreg.EnumKey(dev, 0)
            k2 = winreg.OpenKey(dev, sub)
            ids = list(winreg.QueryValueEx(k2, "HardwareID")[0])
        except OSError:
            continue
        if any("UP:0059_U:0001" in s for s in ids):
            found.append(inst)
    return found


def _lamp_backend() -> Backend:
    devs = lamp_array_devices()
    if not devs:
        return Backend("lamp", "Win11 动态光效", Tier.PER_KEY, False,
                       "本机没有 LampArray 设备（键盘没按这个标准实现）")
    return Backend("lamp", "Win11 动态光效", Tier.PER_KEY, False,
                   "检测到 %d 个 LampArray 设备，但本版还没实现控制" % len(devs),
                   None, "（规划中）可直接调 Windows.Devices.Lights")


# ---------------- 汇总 ----------------

_PREFER_OVER = {"mchose": "ace68"}


def scan() -> List[Backend]:
    from .display.screen import ScreenDisplay
    return [
        _vendor_backend("logitech", "罗技 LED SDK"),
        _vendor_backend("razer", "雷蛇 Chroma SDK"),
        _openrgb_backend(),
        _vendor_backend("ace68", "迈从 Ace 68（实验）"),
        _vendor_backend("mchose", "迈从 MCHOSE（实验）"),
        _lamp_backend(),
        Backend("screen", "屏幕虚拟键盘", Tier.OFF, True,
                "始终可用，同时作为真机灯效的预览器", ScreenDisplay),
    ]


def hardware_displays(preference: str = "auto") -> List[Display]:
    """按能力从高到低挑出可用的真机后端；screen 由调用方自己加。"""
    if preference == "screen":
        return []
    min_tier = _PREF_MIN.get(preference)
    backends = scan()
    ok_keys = {b.key for b in backends if b.ok}
    skip = {key for key, better in _PREFER_OVER.items() if better in ok_keys}
    out: List[Display] = []
    for b in backends:
        if b.key == "screen" or b.key in skip or not b.ok or b.make is None:
            continue
        if min_tier is not None and b.tier < min_tier:
            continue
        try:
            out.append(b.make())
        except Exception as exc:
            print("[display:%s] 构造失败：%r" % (b.key, exc))
    return out


# ---------- 迈从（MCHOSE）专项情报 ----------

def mchose_devices() -> List[str]:
    """从 MCHOSE HUB 的本地缓存里读出已连接过的型号（只读，不碰设备）。"""
    base = Path(os.environ.get("APPDATA", "")) / "MCHOSEHUB" / "Local Storage" / "leveldb"
    if not base.is_dir():
        return []
    pattern = re.compile(r'"deviceName":"([^"]{1,60})"')
    names = set()
    try:
        files = list(base.glob("*.ldb")) + list(base.glob("*.log"))
    except OSError:
        return []
    for f in files:
        try:
            if f.stat().st_size > 24 * 1024 * 1024:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        for enc in ("utf-16-le", "latin-1"):
            text = data.decode(enc, "ignore")
            names.update(m.group(1) for m in pattern.finditer(text))
    return sorted(n for n in names if n)


def report() -> List[str]:
    lines = ["KeyMole 能力探测", "=" * 52]
    best = Tier.OFF
    hints: List[str] = []
    for b in scan():
        mark = "[OK]" if b.ok else "[--]"
        lines.append("%s %-14s %-12s %s" % (mark, b.title, TIER_LABEL[b.tier], b.detail))
        if b.ok:
            best = max(best, b.tier)
        elif b.install_hint:
            hints.append("  · %-14s %s" % (b.title, b.install_hint))
    lines.append("-" * 52)
    lines.append("本次可达到：" + TIER_LABEL[best])
    if best != Tier.OFF and any(b.key == "mchose" and b.ok for b in scan()):
        lines.append("  （迈从通道是实验性的：接口能打开、报文能写入，但灯光效果还没被肉眼确认）")
    if hints:
        lines.append("")
        lines.append("想再往上一级，装这个就行：")
        lines.extend(hints)

    devices = mchose_devices()
    if devices:
        lines.append("")
        lines.append("检测到迈从 MCHOSE：%s" % "、".join(devices))
        lines.append("  KeyMole 已从官方 HUB 的前端 bundle 里还原出逐键灯效协议：")
        lines.append("    360 字节载荷 = 8 头 + 18列x6行x3 网格 + empty15 + [00 00 5A A5 ...]")
        lines.append("    无线 = report id 0x13 + setLightColor 0x09，每片 14 字节、共 26 片，末字节是十进制累加校验")
        lines.append("  现在走 FF70 通道推送（FF80 被系统拒写 err=87，FF81 更不行）。")
        lines.append("  但「能写进去」不等于「灯会亮」，先肉眼确认：")
        lines.append("    python -m keymole.mchose_test --seconds 8")
        lines.append("    能亮 → 这条就是 L3；不亮 → 多半是 2.4G 休眠，或有线才认（report id 6 / 519 字节 feature）")
    return lines
