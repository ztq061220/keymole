"""扫描插着的 HID 设备，判断「这块键盘有没有可点灯的通道」。

回答一个很具体的疑惑：**明明检测到键盘了，为什么点不亮它的灯？**
"检测到"只要求它是个键盘；"能点灯"要求固件额外开一条控制通道：
LampArray（Win11 标准）、VIA/QMK raw HID、厂商私有页、或被 OpenRGB 逆向的协议。
另有一种情况：厂商把控制通道藏在了**键盘接口本身**（一条 64/65 字节的收发报文），
没有单独的私有页，探测表里看不出厂商名，但它确实可能能点灯。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .hidwin import attrs_of, caps_of, close_hid, list_paths, open_hid, product_string

LAMP_ARRAY_PAGE = 0x59
VIA_PAGE = 0xFF60

Report = Tuple[int, int, int, int, int]   # page, usage, in, out, feature


@dataclass
class Device:
    vid: int
    pid: int
    name: str
    pages: Tuple[int, ...] = ()
    interfaces: int = 0
    paths: List[str] = field(default_factory=list)
    reports: Tuple[Report, ...] = ()

    @property
    def hw_id(self) -> str:
        return "VID_%04X&PID_%04X" % (self.vid, self.pid)

    @property
    def is_keyboard(self) -> bool:
        return 0x01 in self.pages

    def channel(self) -> str:
        if LAMP_ARRAY_PAGE in self.pages:
            return "lamp"
        if VIA_PAGE in self.pages:
            return "via"
        if any(p >= 0xFF00 for p in self.pages):
            return "vendor"
        return "hidden" if self.big_report() else "none"

    def big_report(self) -> Report | None:
        """键盘接口上 >16 字节的收发报文：常见于「没有私有页」的杂牌键盘。"""
        for page, usage, il, ol, fl in self.reports:
            if page == 0x01 and (il > 16 or ol > 16 or fl > 16):
                return (page, usage, il, ol, fl)
        return None

    def verdict(self) -> str:
        ch = self.channel()
        if ch == "lamp":
            return "Win11 动态光效（可点灯）"
        if ch == "via":
            return "VIA/QMK raw HID（可点灯，看固件）"
        if ch == "vendor":
            pages = ",".join("0x%02X" % p for p in self.pages if p >= 0xFF00)
            if self.vid == 0x3837 and 0xFF70 in self.pages:
                return "厂商私有页 %s（迈从逐键灯效协议已还原，实验性）" % pages
            return "厂商私有页 %s（未公开，需逆向）" % pages
        if ch == "hidden":
            r = self.big_report()
            return "私有报文通道 in=%d out=%d（无私有页，疑似厂商控制）" % (r[2], r[3])
        return "纯输入设备，没有点灯通道" if self.is_keyboard else "非键盘"


def scan_devices() -> List[Device]:
    found: Dict[Tuple[int, int, str], Device] = {}
    for path in list_paths():
        h = open_hid(path, write=False)
        if not h:
            continue
        try:
            a = attrs_of(h)
            c = caps_of(h)
            if not a or not c:
                continue
            key = (a.VendorID, a.ProductID, product_string(h))
            dev = found.get(key)
            if dev is None:
                dev = Device(vid=a.VendorID, pid=a.ProductID, name=key[2])
                found[key] = dev
            dev.pages = tuple(sorted(set(dev.pages) | {c.UsagePage}))
            dev.reports = tuple(sorted(set(dev.reports) | {
                (c.UsagePage, c.Usage, c.InputReportByteLength,
                 c.OutputReportByteLength, c.FeatureReportByteLength)}))
            dev.interfaces += 1
            dev.paths.append(path)
        finally:
            close_hid(h)
    return sorted(found.values(), key=lambda d: (d.channel() == "none", d.vid, d.pid))


def format_devices(devices: List[Device] | None = None) -> List[str]:
    devices = scan_devices() if devices is None else devices
    if not devices:
        return ["没扫到 HID 设备"]
    lines = ["检测到的 HID 设备（%d 个）：" % len(devices)]
    for d in devices:
        lines.append("  %-24s %s  %s" % (d.name[:24] or "(无产品名)", d.hw_id, d.verdict()))
    return lines


if __name__ == "__main__":
    for line in format_devices():
        print(line)
