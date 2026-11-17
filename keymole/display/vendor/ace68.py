"""Ace 68 (迈从 CZ / 磁轴家族) 逐键灯效。

协议是从 MCHOSE HUB 的 CZ SDK（https://cdn.mchose.com.cn/customPage/prod/cizhou/
CZ_SHARED_DATA/main.*.js）里读出来的，并用 HUB 自己的运行时报文逐字节核对过：

    55 0B 00 <sum> 38 <addrLo> <addrHi> <page> <最多 56 字节 RGB>

* report id 0，整包 64 字节（HID 输出报文 65 字节，首字节是 report id）
* 0x0B 是灯光命令，0x38 是常量，地址是**字节偏移**，每包前进 56
* 校验 = sum(frame[4:]) & 0xFF
* 键位表来自 CDN 上的 default-keys-ace68_i.js（code = HID usage -> LED 序号）
"""

from __future__ import annotations

import threading
import time as _time
from typing import Dict, List, Optional, Tuple

from ... import hidwin
from ..base import Display, Tier
from ...core.layout import HAND_SETS

VID = 0x41E4
PID = 0x2116
LED_COUNT = 128  # 主键区 128 颗；getDeviceMaxLightKeyCount() 实测 = 128
MAGIC = 0x55
CMD_LIGHT = 0x0B
CONST = 0x38
CHUNK = 56
LEDS_PER_PACKET = 18  # 每包 18 颗灯（54 字节）
PAGE = 0
HOLE_PACKETS = (0, 1, 2, 3)  # 15 个洞位所在的包号
REPORT_ID = 0

KEY_LED = {
    4: 10,  # A
    5: 35,  # B
    6: 15,  # C
    7: 11,  # D
    8: 1,  # E
    9: 62,  # F
    10: 12,  # G
    11: 22,  # H
    12: 43,  # I
    13: 46,  # J
    14: 26,  # K
    15: 47,  # L
    16: 56,  # M
    17: 66,  # N
    18: 13,  # O
    19: 23,  # P
    20: 0,  # Q
    21: 21,  # R
    22: 61,  # S
    23: 42,  # T
    24: 63,  # U
    25: 5,  # V
    26: 71,  # W
    27: 25,  # X
    28: 2,  # Y
    29: 20,  # Z
    30: 30,  # 1 !
    31: 51,  # 2 @
    32: 41,  # 3 #
    33: 31,  # 4 $
    34: 52,  # 5 %
    35: 72,  # 6 ^
    36: 32,  # 7 &
    37: 53,  # 8 *
    38: 73,  # 9 (
    39: 33,  # 0 )
    40: 48,  # Enter
    41: 50,  # Esc
    42: 44,  # Backspace
    43: 70,  # Tab
    44: 76,  # Space
    45: 3,  # - _
    46: 54,  # = +
    47: 64,  # [ {
    48: 74,  # ] }
    49: 14,  # \\\\ |
    51: 67,  # ; :
    54: 16,  # , <
    55: 6,  # . >
    56: 57,  # / ?
    57: 60,  # Caps
    73: 34,  # Insert
    75: 24,  # PgUp
    76: 4,  # Delete
    78: 28,  # PgDn
    79: 18,  # →
    80: 58,  # ←
    81: 78,  # ↓
    82: 68,  # ↑
    135: 17,  # 
    224: 45,  # Ctrl
    225: 40,  # Shift
    226: 55,  # Alt
    227: 75,  # Win
    228: 37,  # Ctrl
    229: 27,  # Shift
    230: 36,  # Alt
    255: 7,  # FN1
}

HOLE_CODES = HAND_SETS["left"]
ALL_CODES = tuple(dict.fromkeys(HAND_SETS["left"] + HAND_SETS["right"]))

USAGE = {
    "q": 20, "w": 26, "e": 8, "r": 21, "t": 23, "y": 28, "u": 24, "i": 12, "o": 18, "p": 19,
    "a": 4, "s": 22, "d": 7, "f": 9, "g": 10, "h": 11, "j": 13, "k": 14, "l": 15,
    "z": 29, "x": 27, "c": 6, "v": 25, "b": 5, "n": 17, "m": 16,
    "1": 30, "2": 31, "3": 32, "4": 33, "5": 34, "6": 35, "7": 36, "8": 37, "9": 38, "0": 39,
    "space": 44, "tab": 43, "caps": 57, "enter": 40, "esc": 41, "backspace": 42,
    "lshift": 225, "lctrl": 224, "lalt": 226, "quote": 52, "comma": 54, "period": 55,
    "slash": 56, "semicolon": 51, "bracketleft": 47, "bracketright": 48, "backslash": 49,
    "minus": 45, "equal": 46, "grave": 53,
}


def build_frames(rgb: bytes, page: int = PAGE) -> List[bytes]:
    """把 RGB 字节流切成帧。地址字段是【字节偏移】(3 字节/灯)，每包 18 颗灯。"""
    frames: List[bytes] = []
    led = 0
    total = len(rgb) // 3
    while led < total:
        take = min(LEDS_PER_PACKET, total - led)
        body = bytes(rgb[led * 3:(led + take) * 3])
        body = body + bytes(CHUNK - len(body))
        frame = bytearray(64)
        frame[0] = MAGIC
        frame[1] = CMD_LIGHT
        frame[2] = 0x00
        frame[4] = CONST
        addr = led * 3
        frame[5] = addr & 0xFF
        frame[6] = (addr >> 8) & 0xFF
        frame[7] = page
        frame[8:8 + CHUNK] = body
        frame[3] = sum(frame[4:]) & 0xFF
        frames.append(bytes(frame))
        led += take
    return frames


def key_led(code: str) -> Optional[int]:
    usage = USAGE.get(code)
    if usage is None:
        return None
    return KEY_LED.get(usage)


def find_interface(write: bool = True) -> Tuple[object, object, str]:
    for path in hidwin.list_paths():
        handle = hidwin.open_hid(path, write=write)
        if not handle:
            continue
        attrs = hidwin.attrs_of(handle)
        caps = hidwin.caps_of(handle)
        if (attrs and getattr(attrs, "VendorID", None) == VID
                and getattr(attrs, "ProductID", None) == PID
                and caps and caps.OutputReportByteLength >= 32):
            name = hidwin.product_string(handle) or "Ace 68"
            return handle, caps, name
        hidwin.close_hid(handle)
    return None, None, ""


def probe() -> Tuple[bool, str]:
    handle, caps, name = find_interface(write=True)
    if not handle:
        return False, "没找到 Ace 68 的可写灯效接口"
    hidwin.close_hid(handle)
    return True, "实验性：%s · 输出报文 %d 字节 · 逐键 %d 颗" % (
        name, caps.OutputReportByteLength, LED_COUNT)


class Ace68Display(Display):
    name = "ace68"
    tier = Tier.PER_KEY
    refresh_hz = 25

    def __init__(self) -> None:
        super().__init__()
        self._handle = None
        self._caps = None
        self._pending = None          # (colors, packets)，只留最新一帧
        self._applied = None          # 真正写进键盘的那一版颜色
        self._t_commit = 0.0
        self.latencies = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._sender = None
        self._todo = set()      # 必须补发的包（整帧强刷时排队）
        self._last_full = 0.0
        self._full_cursor = 0
        self._keep_cursor = 0
        self._base = [0] * (LED_COUNT * 3)
        self._last_full = _time.perf_counter()
        self._last = [0] * (LED_COUNT * 3)
        self._last_full = 0.0
        self._last_keep = 0.0
        self._hole_packets = {led // LEDS_PER_PACKET
                              for led in (key_led(c) for c in ALL_CODES)
                              if led is not None}
        self.device_label = ""
        self.frames_sent = 0

    def supported_keys(self) -> List[str]:
        codes = {c for codes in HAND_SETS.values() for c in codes}
        return [code for code in codes if key_led(code) is not None]

    def open(self) -> None:
        handle, caps, name = find_interface(write=True)
        if not handle:
            raise RuntimeError("没找到 Ace 68 的可写接口，检查键盘是否插线")
        self._handle = handle
        self._caps = caps
        self.device_label = name
        self._base = [0] * (LED_COUNT * 3)
        self._last = list(self._base)
        self._applied = list(self._base)
        self._send(self._base)
        self._last = list(self._base)
        self._stop = False
        self._sender = threading.Thread(target=self._send_loop, name="ace68-send", daemon=True)
        self._sender.start()

    def _send(self, colors, packets=None, timeout: int = 80) -> None:
        """一次把要发的包都发出去（异步并行），比逐包串行快一倍。"""
        payloads = []
        for index, frame in enumerate(build_frames(bytes(colors))):
            if packets is not None and index not in packets:
                continue
            payloads.append(bytes([REPORT_ID]) + frame)
        if not payloads:
            return
        # 并行发多包时设备会丢包（实测 v/b 两键整轮不亮），必须逐包串行。
        ok = 0
        for payload in payloads:
            if hidwin.send_report_timeout(self._handle, payload, len(payload), timeout):
                ok += 1
            _time.sleep(0.004)      # 连发太快设备会静默吞包，留一点气口
        self.frames_sent += ok
        return ok, len(payloads)

    def _write(self, payloads, timeout: int = 80) -> int:
        try:
            ok = hidwin.send_reports(self._handle, payloads, timeout)
        except Exception:
            ok = 0
            for payload in payloads:
                if hidwin.send_report_timeout(self._handle, payload, len(payload), timeout):
                    ok += 1
        self.frames_sent += ok

    def _dirty_packets(self, colors, previous) -> set:
        """只发颜色变了的包，一帧通常 2-5 包，比整帧快 8 倍。"""
        if previous is None:
            return set(range(len(colors) // (LEDS_PER_PACKET * 3) + 1))
        packets = set()
        for i in range(0, len(colors), 3):
            if (colors[i] != previous[i] or colors[i + 1] != previous[i + 1]
                    or colors[i + 2] != previous[i + 2]):
                packets.add((i // 3) // LEDS_PER_PACKET)   # 这里 i 是字节偏移，先除以 3 变成灯号
        return packets

    def _commit(self, frame: Dict[str, Tuple[int, int, int]], now: float = 0.0) -> None:
        colors = list(self._base)
        for code, rgb in frame.items():
            led = key_led(code)
            if led is None or led >= LED_COUNT:
                continue
            base = led * 3
            colors[base] = rgb[0]
            colors[base + 1] = rgb[1]
            colors[base + 2] = rgb[2]
        # 洞位只落在前 4 包里（q/e/v/a/d/g/c = 0 号包，z/r/x/b = 1，t = 2，w = 3），
        # 每帧只发这 4 包（≈27ms）就能保证游戏画面；其余灯区每 2 秒整帧压一次。
        # 固件会自己重绘，只发一次会亮一下就灭 → 亮着的包必须持续刷新；
        # 但全发 4 包要 30ms，所以只发「有内容的包」+「刚变过的包」。
        # 15 个洞位全部落在 0-3 号包里（q/e/v/a/d/g/c=0，z/r/x/b=1，t=2，w=3）。
        # 只发这 4 包：一帧 ≈ 4×5ms，既不会堆积，也不会把洞位挤掉。
        dirty = self._dirty_packets(colors, self._applied)
        self._last = list(colors)
        order = [p for p in sorted(dirty) if p in HOLE_PACKETS]
        # 设备每秒只吞得下 ~55 包，一帧塞满 4 包就要 70ms 以上。
        # 所以：变化的包立刻发（最多 2 个），没变化时轮转发 1 个保活包。
        if not order:
            order = [HOLE_PACKETS[self._keep_cursor % len(HOLE_PACKETS)]]
            self._keep_cursor += 1
        if now - self._last_full >= 0.7:                        # 其余灯区慢慢压一遍，保持熄灭
            self._last_full = now
            extra = sorted(self._todo)
            if extra and len(order) < 2:
                cut = self._full_cursor % len(extra)
                extra = extra[cut:] + extra[:cut]
                self._full_cursor += 1
                order += [p for p in extra[:1] if p not in order]
        packets = order[:2]
        if packets:
            # 发送要几毫秒/包，放在 UI 线程里会把画面拖慢；丢给后台线程，只保留最新一帧
            with self._lock:
                self._pending = (colors, packets, _time.perf_counter())
            self._wake.set()

    def invalidate(self) -> None:
        """让下一帧整帧重发（换局、从结束画面重开时用）。"""
        self._applied = None
        self._last_keep = 0.0
        self._todo = set(range(len(self._base) // (LEDS_PER_PACKET * 3) + 1))
        with self._lock:
            self._pending = None

    def _send_loop(self) -> None:
        while True:
            self._wake.wait(0.2)
            if self._stop:
                return
            self._wake.clear()
            with self._lock:
                job, self._pending = self._pending, None
            if not job:
                continue
            colors, packets, t0 = job
            try:
                ok, total = self._send(colors, packets=packets)
            except Exception:
                _time.sleep(0.01)
                continue
            if ok >= total:
                if self._applied is None:
                    self._applied = list(self._base)
                self._todo -= set(packets)
                self.latencies.append((_time.perf_counter() - t0) * 1000)
                for index in packets:
                    lo = index * LEDS_PER_PACKET * 3
                    hi = min(lo + LEDS_PER_PACKET * 3, len(colors))
                    if self._applied is not None:
                        self._applied[lo:hi] = colors[lo:hi]

    def close(self) -> None:
        if self.latencies:
            lat = sorted(self.latencies)
            print("[ace68] 提交→落地 ms: 中位 %.0f  p90 %.0f  最大 %.0f  样本 %d"
                  % (lat[len(lat) // 2], lat[max(0, int(len(lat) * 0.9) - 1)], lat[-1], len(lat)))
        self._stop = True
        self._wake.set()
        if self._sender:
            self._sender.join(timeout=1.0)
            self._sender = None
        if self._handle:
            try:
                self._send([0] * (LED_COUNT * 3))
            except Exception:
                pass
            hidwin.close_hid(self._handle)
            self._handle = None


def make() -> Ace68Display:
    return Ace68Display()
