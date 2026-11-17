"""迈从（MCHOSE）无线通道：从官方 HUB 的前端代码里还原出来的私有协议。

协议要点（全部来自 HUB bundle，非猜测）：
- 帧 = [reportId 0x13][cmd][total][seq][yy][14 字节数据][crc]，一次写 65 字节。
- crc = (reportId + 前面所有字节) & 0xFF（HUB 里就是十进制求和，不是真 CRC）。
- setLightColor 的 cmd = 0x09；data 是「8 字节头 + 18 列 × 6 行 × 3 字节 RGB」，
  每键 3 字节，偏移 = 8 + (col*6 + row)*3；末尾再跟 14 字节 empty15 与 14 字节 empty16。
- 尾包 yy = 该包有效字节数（末尾 0 不算）。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from ..base import Display, Tier
from ... import hidwin as hw

VID = 0x3837
PIDS = {0x1015: "G87/K87 V3", 0x1014: "K7 V2 Ultra+", 0x1012: "MagDock"}
REPORT_ID = 0x13
CMD_SET_LIGHT = 0x09
PAGES = (0xFF70, 0xFF80, 0xFF81)

HEADER = 8
COLS, ROWS = 18, 6
GRID = COLS * ROWS * 3
TAIL_15 = 14
TAIL_16 = bytes([0, 0, 0x5A, 0xA5] + [0] * 10)

# 键 -> 颜色在包里的字节偏移（HUB 的 config 表，code 是 HID usage）
KEY_INDEX: Dict[str, int] = {
    "esc": 8, "f1": 44, "f2": 62, "f3": 80, "f4": 98,
    "quote": 11, "1": 29, "2": 47, "3": 65, "4": 83, "5": 101,
    "6": 119, "7": 137, "8": 155, "9": 173, "0": 191, "minus": 209, "equal": 227,
    "backspace": 245, "tab": 14, "q": 32, "w": 50, "e": 68, "r": 86, "t": 104,
    "y": 122, "u": 140, "i": 158, "o": 176, "p": 194,
    "caps": 17, "a": 35, "s": 53, "d": 71, "f": 89, "g": 107, "h": 125, "j": 143,
    "k": 161, "l": 179, "semicolon": 197,
    "lshift": 20, "z": 38, "x": 56, "c": 74, "v": 92, "b": 110, "n": 128,
    "m": 146, "comma": 164, "period": 182, "slash": 200,
    "lctrl": 23, "lwin": 41, "lalt": 59, "space": 113, "ralt": 167, "fn": 185,
}


def build_payload(frame: Dict[str, Tuple[int, int, int]]) -> bytes:
    """把 {键: (r,g,b)} 打成 setLightColor 的完整（未分片）载荷。"""
    body = bytearray(HEADER + GRID)
    body[0] = CMD_SET_LIGHT
    for code, rgb in frame.items():
        idx = KEY_INDEX.get(code)
        if idx is None:
            continue
        body[idx:idx + 3] = bytes(max(0, min(255, int(c))) for c in rgb)
    return bytes(body) + bytes(TAIL_15) + TAIL_16


def split_frames(payload: bytes, report_id: int = REPORT_ID) -> List[bytes]:
    """按 HUB 的规则切片：首字节是命令，其余每 14 字节一包，带累加校验。"""
    cmd = payload[0]
    rest = payload[1:]
    chunks = [rest[i:i + 14] for i in range(0, len(rest), 14)]
    out = []
    for seq, chunk in enumerate(chunks):
        data = list(chunk) + [0] * (14 - len(chunk))
        yy = 14
        if seq == len(chunks) - 1:
            tail = 0
            for b in reversed(data):
                if b == 0:
                    tail += 1
                else:
                    break
            yy = 14 - tail
        body = [cmd, len(chunks), seq, yy] + data
        crc = (report_id + sum(body)) & 0xFF
        out.append(bytes([report_id] + body + [crc]))
    return out


def find_interface(write: bool = True):
    """找一块迈从键盘的可写接口，返回 (handle, caps, page, name)。"""
    for pid, name in PIDS.items():
        for page in PAGES:
            for path in hw.list_paths():
                if "vid_%04x&pid_%04x" % (VID, pid) not in path.lower():
                    continue
                h = hw.open_hid(path, write=False)
                if not h:
                    continue
                caps = hw.caps_of(h)
                hw.close_hid(h)
                if not caps or caps.UsagePage != page or caps.OutputReportByteLength == 0:
                    continue
                handle = hw.open_hid_overlapped(path, write=write)
                if handle:
                    return handle, caps, page, name
    return None, None, None, None


def probe() -> Tuple[bool, str]:
    handle, caps, page, name = find_interface(write=True)
    if not handle:
        return False, "没找到可写的迈从接口（键盘没插？被 HUB 独占？）"
    hw.close_hid(handle)
    return True, "实验性：%s · page 0x%04X · out=%d" % (name, page, caps.OutputReportByteLength)


class MchoseDisplay(Display):
    name = "mchose"
    tier = Tier.PER_KEY
    refresh_hz = 8

    def __init__(self) -> None:
        super().__init__()
        self.handle = None
        self.caps = None
        self.acked = 0
        self.sent = 0
        self.last_error = ""

    def open(self) -> None:
        handle, caps, page, name = find_interface(write=True)
        if not handle:
            raise RuntimeError("没找到可写的迈从接口")
        self.handle, self.caps = handle, caps
        self.device_label = "%s (0x%04X)" % (name, page)
        self._flush_pending()

    def _flush_pending(self) -> None:
        while True:
            if not hw.read_report_timeout(self.handle, self.caps.InputReportByteLength, 30):
                return

    def _commit(self, frame, now: float = 0.0) -> None:
        payload = build_payload(frame)
        packets = split_frames(payload)
        ok = 0
        for pkt in packets:
            if hw.send_report_timeout(self.handle, pkt, self.caps.OutputReportByteLength):
                ok += 1
                reply = hw.read_report_timeout(self.handle, self.caps.InputReportByteLength, 20)
                if reply:
                    self.acked += 1
        self.sent += 1
        if ok < len(packets):
            self.last_error = "只发出 %d/%d 包" % (ok, len(packets))

    def close(self) -> None:
        if self.handle:
            hw.close_hid(self.handle)
            self.handle = None




# ---------------- 有线通道 ----------------
# HUB 有线写：report id 6 + sendFeatureReport，载荷补零到 519 字节。
# 只有插线时才会枚举出带 feature 报文的集合（无线 dongle 的 feat 全是 0）。

WIRED_RID = 0x06
WIRED_CMD_LIGHT = 0x10
WIRED_SIZE = 519


def wired_candidates():
    """找带 feature 报文、能写的迈从集合（有线模式才会出现）。"""
    out = []
    for path in hw.list_paths():
        low = path.lower()
        if "vid_3837" not in low and "vid_41e4" not in low:
            continue
        h = hw.open_hid_overlapped(path, write=True)
        if not h:
            continue
        caps = hw.caps_of(h)
        if caps.FeatureReportByteLength >= 64:
            out.append((path, h, caps))
        else:
            hw.close_hid(h)
    return out


def build_wired_payload(frame, size=None):
    """有线载荷：命令字节 0x10 + 与无线相同的 360 字节布局，补零到 size。"""
    body = bytearray(build_payload(frame))
    body[0] = WIRED_CMD_LIGHT
    total = size if size else max(WIRED_SIZE, len(body) + 1)
    buf = bytearray(total)
    buf[0] = WIRED_RID              # 第一个字节是 report id
    n = min(len(body), total - 1)
    buf[1:1 + n] = body[:n]
    return bytes(buf)


def set_feature(handle, payload):
    import ctypes
    arr = (ctypes.c_ubyte * len(payload))(*payload)
    return bool(hw.hid.HidD_SetFeature(ctypes.c_void_p(handle), arr, len(payload)))


def make() -> "MchoseDisplay":
    """给 detect._vendor_backend 用：探测通过后构造后端。"""
    return MchoseDisplay()
