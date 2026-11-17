"""OpenRGB SDK 的最小客户端（纯标准库，不依赖 openrgb-python）。

为什么自己写：目标是「一条命令装完就能玩」。多一个 pip 依赖就多一次劝退；
而这个协议本身只有十几个字节的分支判断。

协议依据 OpenRGB 源码（NetworkProtocol.h / NetworkServer.cpp / RGBController.cpp）：

    包头 16 字节：b"ORGB" + u32 dev_id + u32 pkt_id + u32 payload_size   （全小端）
    字符串：      u16 长度（含结尾 NUL）+ 原始字节（含 NUL）
    颜色：        4 字节 RGBColor，内存布局 R,G,B,(填充)

我们请求里**声明 protocol_version = 3**，这是个甜点版本：
  · >= 1 有 vendor 字段，>= 3 的 mode 才有 brightness 字段
  · < 4 没有 segment、< 5 没有 flags / led_display_names、< 6 LED 带 value
所以解析器可以写得又短又稳，不用为老/新版本分叉。
"""
from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

MAGIC = b"ORGB"
PROTOCOL_VERSION = 3

PKT_REQUEST_CONTROLLER_COUNT = 0
PKT_REQUEST_CONTROLLER_DATA = 1
PKT_REQUEST_PROTOCOL_VERSION = 40
PKT_SET_CLIENT_NAME = 50
PKT_UPDATE_LEDS = 1050
PKT_SET_CUSTOM_MODE = 1100
DEV_SERVER = 0            # 发给服务器本身的包，dev_id 固定 0
HEADER = struct.Struct("<4sIII")


class OrgbError(RuntimeError):
    pass


def pack_string(text: str) -> bytes:
    raw = text.encode("utf-8") + b"\x00"
    return struct.pack("<H", len(raw)) + raw


class _Reader:
    """顺序读取器。字段顺序全部来自 RGBController::GetDeviceDescriptionData。"""

    __slots__ = ("buf", "off", "end")

    def __init__(self, buf: bytes, off: int = 0):
        self.buf = buf
        self.off = off
        self.end = len(buf)

    def _take(self, n: int) -> bytes:
        if self.off + n > self.end:
            raise OrgbError("OpenRGB 数据被截断：需要 %d 字节，只剩 %d" % (n, self.end - self.off))
        chunk = self.buf[self.off:self.off + n]
        self.off += n
        return chunk

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def string(self) -> str:
        n = self.u16()
        return self._take(n).split(b"\x00", 1)[0].decode("utf-8", "replace")

    def skip_string(self) -> str:
        return self.string()

    def colors(self, count: int) -> List[Tuple[int, int, int]]:
        out = []
        for _ in range(count):
            r, g, b, _pad = self._take(4)
            out.append((r, g, b))
        return out


@dataclass
class Zone:
    name: str
    type: int
    leds_count: int
    matrix: Optional[Tuple[int, int, List[int]]] = None   # (高, 宽, 每格 LED 序号)


@dataclass
class Mode:
    name: str
    value: int


@dataclass
class Controller:
    index: int
    type: int
    name: str
    vendor: str
    description: str
    active_mode: int = 0
    modes: List[Mode] = field(default_factory=list)
    zones: List[Zone] = field(default_factory=list)
    leds: List[str] = field(default_factory=list)
    colors: List[Tuple[int, int, int]] = field(default_factory=list)

    def __str__(self) -> str:
        return "%s %s (%d LED / %d 区)" % (self.vendor, self.name, len(self.leds), len(self.zones))


def parse_controller(r: _Reader, index: int) -> Controller:
    c = Controller(
        index=index,
        type=r.u32(),
        name=r.string(),
        vendor=r.string(),
        description=r.string(),
    )
    r.skip_string()                     # version
    r.skip_string()                     # serial
    r.skip_string()                     # location

    num_modes = r.u16()
    c.active_mode = r.u32()
    for _ in range(num_modes):
        name = r.string()
        value = r.u32()
        r.u32()                         # flags
        r.u32(); r.u32()                # speed_min / speed_max
        r.u32(); r.u32()                # brightness_min / brightness_max
        r.u32(); r.u32()                # colors_min / colors_max
        r.u32(); r.u32()                # speed / brightness
        r.u32()                         # direction
        r.u32()                         # color_mode
        n = r.u16()
        r.colors(n)
        c.modes.append(Mode(name, value))

    num_zones = r.u16()
    for _ in range(num_zones):
        name = r.string()
        ztype = r.u32()
        r.u32(); r.u32()                # leds_min / leds_max
        count = r.u32()
        matrix = None
        matrix_bytes = r.u16()
        if matrix_bytes:
            h, w = r.u32(), r.u32()
            matrix = (h, w, [r.u32() for _ in range(h * w)])
        c.zones.append(Zone(name, ztype, count, matrix))

    num_leds = r.u16()
    for _ in range(num_leds):
        c.leds.append(r.string())
        r.u32()                         # LED value（protocol < 6 才有）
    return c


class OrgbClient:
    """只做 KeyMole 需要的那几个操作，够用就好。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 6742,
                 name: str = "KeyMole", timeout: float = 3.0):
        self.host = host
        self.port = port
        self.name = name
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    # ---- 连接 ----

    def connect(self) -> "OrgbClient":
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.send(PKT_SET_CLIENT_NAME, DEV_SERVER, pack_string(self.name))
        return self

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # ---- 收发 ----

    def send(self, pkt_id: int, dev_id: int = DEV_SERVER, payload: bytes = b"") -> None:
        if self.sock is None:
            raise OrgbError("还没连接 OpenRGB")
        self.sock.sendall(HEADER.pack(MAGIC, dev_id, pkt_id, len(payload)) + payload)

    def _recv_exact(self, n: int) -> bytes:
        if self.sock is None:
            raise OrgbError("还没连接 OpenRGB")
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OrgbError("OpenRGB 断开了连接")
            buf += chunk
        return bytes(buf)

    def recv(self) -> Tuple[int, int, bytes]:
        magic, dev_id, pkt_id, size = HEADER.unpack(self._recv_exact(HEADER.size))
        if magic != MAGIC:
            raise OrgbError("不是 OpenRGB 协议（magic=%r）" % (magic,))
        return dev_id, pkt_id, self._recv_exact(size)

    # ---- 协议动作 ----

    def controller_count(self) -> int:
        self.send(PKT_REQUEST_CONTROLLER_COUNT)
        _dev, _pkt, data = self.recv()
        return struct.unpack("<I", data[:4])[0]

    def controller(self, index: int) -> Controller:
        self.send(PKT_REQUEST_CONTROLLER_DATA, index, struct.pack("<I", PROTOCOL_VERSION))
        _dev, _pkt, data = self.recv()
        body = data[4:]                 # 前 4 字节是整包长度，已知，跳过
        return parse_controller(_Reader(body), index)

    def controllers(self) -> List[Controller]:
        return [self.controller(i) for i in range(self.controller_count())]

    def set_custom_mode(self, index: int) -> None:
        """让设备进 Direct 模式，否则固件灯效会盖掉我们写的颜色。"""
        self.send(PKT_SET_CUSTOM_MODE, index)

    def update_leds(self, index: int, colors: Sequence[Tuple[int, int, int]]) -> None:
        """整帧提交。payload = u32 总长 + u16 数量 + N×RGBColor。"""
        body = bytearray(struct.pack("<H", len(colors)))
        for r, g, b in colors:
            body += bytes((r & 255, g & 255, b & 255, 0))
        payload = struct.pack("<I", len(body) + 4) + bytes(body)
        self.send(PKT_UPDATE_LEDS, index, payload)
