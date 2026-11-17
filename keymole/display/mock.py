"""内置的假 OpenRGB SDK Server：没硬件也能开发和自测 L3 通道。

它按 OpenRGB 源码（RGBController::GetDeviceDescriptionData，protocol 3）
逐字节写出设备描述，所以拿它验证客户端 = 验证打包/解包是否跟官方一致。

    python -m keymole --mock        # 游戏里直接用它
    python -m tools.mock_orgb_server  # 单独跑
"""
from __future__ import annotations

import argparse
import socket
import struct
import threading
from typing import Dict, List, Tuple

from ..core.layout import KEYBOARD
from .orgb import (
    DEV_SERVER, HEADER, MAGIC, PKT_REQUEST_CONTROLLER_COUNT, PKT_REQUEST_CONTROLLER_DATA,
    PKT_REQUEST_PROTOCOL_VERSION, PKT_SET_CLIENT_NAME, PKT_SET_CUSTOM_MODE, PKT_UPDATE_LEDS,
    pack_string,
)

_LABELS = {
    "backspace": "Backspace", "tab": "Tab", "capslock": "Caps Lock", "enter": "Enter",
    "lshift": "Left Shift", "rshift": "Right Shift", "lctrl": "Left Ctrl",
    "rctrl": "Right Ctrl", "lalt": "Left Alt", "ralt": "Right Alt",
    "lwin": "Left Windows", "rwin": "Right Windows", "menu": "Menu", "space": "Space",
    "grave": "`", "minus": "-", "equal": "=", "lbracket": "[", "rbracket": "]",
    "backslash": "\\", "semicolon": ";", "quote": "'", "comma": ",", "period": ".",
    "slash": "/",
}


def led_name(code: str) -> str:
    if code in _LABELS:
        return "Key: " + _LABELS[code]
    return "Key: " + code.upper()


class MockController:
    """默认是一台 61 键、LED 名字规范的逐键键盘。

    `zone_counts=[16,16,16,16]` 则模拟一台「认不出键名、只有 4 个区」的键盘，
    用来验证 L2 降级路径。
    """

    def __init__(self, name: str = "Mock Keyboard", vendor: str = "MockCorp",
                 zone_counts=None) -> None:
        self.name = name
        self.vendor = vendor
        self.codes = [k.code for k in KEYBOARD]
        self.zone_counts = list(zone_counts) if zone_counts else None
        if self.zone_counts:
            total = sum(self.zone_counts)
            self.leds = ["LED %d" % (i + 1) for i in range(total)]
        else:
            self.leds = [led_name(c) for c in self.codes]
        self.colors = [(0, 0, 0)] * len(self.leds)
        self.direct = False
        self.updates = 0

    # ---- 序列化（照抄 C++ 字段顺序）----

    def describe(self) -> bytes:
        out = bytearray()
        out += struct.pack("<I", 1)                 # device_type = KEYBOARD
        out += pack_string(self.name)
        out += pack_string(self.vendor)
        out += pack_string("mock device for KeyMole")
        out += pack_string("1.0")
        out += pack_string("SN-MOCK")
        out += pack_string("mock://0")

        out += struct.pack("<H", 1)                 # num_modes
        out += struct.pack("<I", 0)                 # active_mode
        out += pack_string("Direct")
        out += struct.pack("<I", 0)                 # value
        out += struct.pack("<I", 0)                 # flags
        for _ in range(2):                          # speed_min/max
            out += struct.pack("<I", 0)
        for _ in range(2):                          # brightness_min/max
            out += struct.pack("<I", 0)
        for _ in range(2):                          # colors_min/max
            out += struct.pack("<I", 0)
        out += struct.pack("<I", 0)                 # speed
        out += struct.pack("<I", 0)                 # brightness
        out += struct.pack("<I", 0)                 # direction
        out += struct.pack("<I", 0)                 # color_mode
        out += struct.pack("<H", 0)                 # mode colors

        if self.zone_counts:
            out += struct.pack("<H", len(self.zone_counts))
            for zi, cnt in enumerate(self.zone_counts):
                out += pack_string("Zone %d" % (zi + 1))
                out += struct.pack("<I", 1)         # zone type = LINEAR
                out += struct.pack("<I", cnt)        # leds_min
                out += struct.pack("<I", cnt)        # leds_max
                out += struct.pack("<I", cnt)        # leds_count
                out += struct.pack("<H", 0)          # matrix_map_size = 0
        else:
            out += struct.pack("<H", 1)                 # num_zones
            out += pack_string("Keyboard")
            out += struct.pack("<I", 1)                 # zone type = LINEAR
            out += struct.pack("<I", len(self.leds))    # leds_min
            out += struct.pack("<I", len(self.leds))    # leds_max
            out += struct.pack("<I", len(self.leds))    # leds_count
            out += struct.pack("<H", 0)                 # matrix_map_size = 0

        out += struct.pack("<H", len(self.leds))    # num_leds
        for i, _n in enumerate(self.leds):
            out += pack_string(self.leds[i])
            out += struct.pack("<I", i)             # LED value（protocol < 6）

        out += struct.pack("<H", len(self.colors))  # num_colors
        for r, g, b in self.colors:
            out += bytes((r, g, b, 0))
        return bytes(out)


class MockServer(threading.Thread):
    daemon = True

    def __init__(self, port: int = 6742, controller: MockController | None = None) -> None:
        super().__init__(name="mock-orgb")
        self.port = port
        self.controller = controller or MockController()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(4)
        self.sock.settimeout(0.5)
        self._stop = threading.Event()
        self.hello: List[str] = []

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass

    # ---- 单个连接 ----

    def _serve(self, conn: socket.socket) -> None:
        conn.settimeout(5.0)
        with conn:
            while True:
                try:
                    head = self._recv(conn, HEADER.size)
                except (OSError, ConnectionError):
                    return
                if not head:
                    return
                magic, dev_id, pkt_id, size = HEADER.unpack(head)
                if magic != MAGIC:
                    return
                data = self._recv(conn, size) if size else b""
                if pkt_id == PKT_SET_CLIENT_NAME:
                    self.hello.append(data[2:].split(b"\x00", 1)[0].decode("utf-8", "replace"))
                elif pkt_id == PKT_REQUEST_CONTROLLER_COUNT:
                    self._send(conn, DEV_SERVER, pkt_id, struct.pack("<I", 1))
                elif pkt_id == PKT_REQUEST_CONTROLLER_DATA:
                    desc = self.controller.describe()
                    self._send(conn, dev_id, pkt_id, struct.pack("<I", len(desc) + 4) + desc)
                elif pkt_id == PKT_REQUEST_PROTOCOL_VERSION:
                    self._send(conn, DEV_SERVER, pkt_id, struct.pack("<I", 6))
                elif pkt_id == PKT_SET_CUSTOM_MODE:
                    self.controller.direct = True
                elif pkt_id == PKT_UPDATE_LEDS:
                    self._apply_colors(data)

    def _apply_colors(self, data: bytes) -> None:
        n = struct.unpack("<H", data[4:6])[0]
        colors = []
        for i in range(n):
            off = 6 + i * 4
            r, g, b, _ = data[off:off + 4]
            colors.append((r, g, b))
        if colors:
            self.controller.colors = colors
            self.controller.updates += 1

    def _recv(self, conn: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return b""
            buf += chunk
        return bytes(buf)

    def _send(self, conn: socket.socket, dev_id: int, pkt_id: int, payload: bytes) -> None:
        conn.sendall(HEADER.pack(MAGIC, dev_id, pkt_id, len(payload)) + payload)
