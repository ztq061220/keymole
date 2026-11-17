"""L3 后端：任何被 OpenRGB 支持的键盘（目前六百多个型号，几十个品牌）。

走的是 OpenRGB 的 SDK Server（TCP 6742）。相比直接跟厂商软件抢 HID，
这条路的好处是「一份代码覆盖一堆品牌」——OpenRGB 社区已经把各家的私有协议
逆向完了，我们只管发 RGB。

自己实现了协议客户端（见 orgb.py），不需要 pip 装 openrgb-python。
"""
from __future__ import annotations

import re
from typing import Dict, List, Mapping, Sequence, Tuple

from ..core.layout import BY_CODE, HOLE_CODES, HOLE_ROWS
from ..render import OFF
from .base import Display, Tier
from .orgb import OrgbClient
from .zones import aggregate

Rgb = Tuple[int, int, int]

OPENRGB_HOST = "127.0.0.1"
OPENRGB_PORT = 6742

# OpenRGB 的 LED 名字五花八门：「Key: A」「Key: Left Shift」「LED 12」「Zona 1」…
# 先把名字归一化，再对到 layout.py 的逻辑键 code。
_WORD_CODES = {
    "tab": "tab", "caps lock": "capslock", "capslock": "capslock", "caps": "capslock",
    "enter": "enter", "return": "enter", "space": "space", "spacebar": "space",
    "backspace": "backspace", "back space": "backspace", "delete": "backspace",
    "left shift": "lshift", "shift left": "lshift", "lshift": "lshift", "shift": "lshift",
    "right shift": "rshift", "rshift": "rshift",
    "left ctrl": "lctrl", "left control": "lctrl", "lctrl": "lctrl",
    "ctrl": "lctrl", "control": "lctrl",
    "right ctrl": "rctrl", "right control": "rctrl", "rctrl": "rctrl",
    "left alt": "lalt", "lalt": "lalt", "alt": "lalt",
    "right alt": "ralt", "ralt": "ralt", "alt gr": "ralt", "altgr": "ralt",
    "left win": "lwin", "left windows": "lwin", "lwin": "lwin",
    "windows": "lwin", "super": "lwin", "os": "lwin",
    "right win": "rwin", "right windows": "rwin", "rwin": "rwin",
    "menu": "menu", "application": "menu",
    "semicolon": "semicolon", "apostrophe": "quote", "quote": "quote",
    "comma": "comma", "period": "period", "dot": "period", "slash": "slash",
    "backslash": "backslash", "minus": "minus", "equal": "equal", "equals": "equal",
    "grave": "grave", "backtick": "grave", "tilde": "grave", "tick": "grave",
}
_CHAR_CODES = {
    "-": "minus", "=": "equal", "[": "lbracket", "]": "rbracket", "\\": "backslash",
    ";": "semicolon", "'": "quote", ",": "comma", ".": "period", "/": "slash",
    "`": "grave", "~": "grave",
}
_PREFIX = re.compile(r"^(key|led|light|rgb|switch|row\s*\d+\s*col\s*\d+)\s*[:#]?\s*")
_JUNK = re.compile(r"^(led|light|rgb|lamp|pixel|zone|zona)\s*\d+$")


def led_name_to_code(name: str) -> str | None:
    """把 OpenRGB 的 LED 名翻译成 layout.py 的逻辑键 code，认不出返回 None。"""
    if not name:
        return None
    low = name.strip().lower().replace("_", " ")
    low = re.sub(r"\s+", " ", low)
    if _JUNK.match(low):                 # 「LED 1」不是一个键
        return None
    low = _PREFIX.sub("", low).strip()   # 「Key: A」→「a」
    if low in _WORD_CODES:
        return _WORD_CODES[low]
    if len(low) == 1:
        if low.isalnum():
            return low
        return _CHAR_CODES.get(low)
    if low in BY_CODE:
        return low
    # 「key a」「switch q」之类的尾巴
    tail = low.rsplit(" ", 1)[-1]
    if len(tail) == 1 and (tail.isalnum() or tail in _CHAR_CODES):
        return tail if tail.isalnum() else _CHAR_CODES[tail]
    return _WORD_CODES.get(tail)


HOLE_ORDER = tuple(code for row in HOLE_ROWS for code in row)


def _chunks(codes: Sequence[str], n: int) -> List[Tuple[str, ...]]:
    """把 15 个洞位切成 n 段。

    区少（<=5）时按「竖条」切 —— 键盘分区大多是左/中/右；
    区多时按行优先切，粒度更细一点。
    """
    n = max(1, min(int(n), len(codes)))
    if n <= 5:
        cols = [tuple(row[i] for row in HOLE_ROWS) for i in range(len(HOLE_ROWS[0]))]
        size, extra = divmod(len(cols), n)
        out: List[Tuple[str, ...]] = []
        i = 0
        for k in range(n):
            take = size + (1 if k < extra else 0)
            out.append(tuple(code for col in cols[i:i + take] for code in col))
            i += take
        return out
    size, extra = divmod(len(codes), n)
    out, i = [], 0
    for k in range(n):
        take = size + (1 if k < extra else 0)
        out.append(tuple(codes[i:i + take]))
        i += take
    return out


def _zone_slices(ctrl) -> List[Tuple[int, int]]:
    """每个区在整条 LED 数组里占哪一段（OpenRGB 的区就是按顺序切 LED）。"""
    counts = [int(getattr(z, "leds_count", 0) or 0) for z in ctrl.zones]
    n_leds = len(ctrl.leds)
    if counts and sum(counts) == n_leds and all(c > 0 for c in counts):
        out, i = [], 0
        for c in counts:
            out.append((i, c))
            i += c
        return out
    n = max(1, len(counts))
    size, extra = divmod(n_leds, n)
    out, i = [], 0
    for k in range(n):
        c = size + (1 if k < extra else 0)
        out.append((i, c))
        i += c
    return out


class OpenRGBDisplay(Display):
    """OpenRGB 后端：认得出键名就逐键（L3），认不出就按区（L2/L1）退一步。

    降级不是妥协 —— 市面上一大半带灯键盘本来就没有逐键协议，
    但它们几乎都有「分区」，地鼠跑到哪一区就让哪一区亮，玩家照样知道往哪看。
    """

    name = "openrgb"
    tier = Tier.PER_KEY
    refresh_hz = 30.0

    def __init__(self, client_name: str = "KeyMole", device_index: int | None = None,
                 host: str = OPENRGB_HOST, port: int = OPENRGB_PORT) -> None:
        super().__init__()
        self.client_name = client_name
        self.device_index = device_index
        self.host = host
        self.port = port
        self.client: OrgbClient | None = None
        self.controller = None
        self.device_label = ""
        self.mode = "perkey"                 # perkey | zones
        self.zones: List[Tuple[str, ...]] = []
        self._slices: List[Tuple[int, int]] = []
        self._index: Dict[str, int] = {}
        self._base: List[Rgb] = []

    # ---- 生命周期 ----

    def open(self) -> None:
        self.client = OrgbClient(self.host, self.port, self.client_name).connect()
        controllers = self.client.controllers()
        if not controllers:
            raise RuntimeError("OpenRGB 里一个设备都没有（先在 OpenRGB 里点一下 Rescan）")

        best: Tuple[Tuple[int, int], object, Dict[str, int]] | None = None
        for ctrl in controllers:
            if self.device_index is not None and ctrl.index != self.device_index:
                continue
            mapping: Dict[str, int] = {}
            for i, led_name in enumerate(ctrl.leds):
                code = led_name_to_code(led_name)
                if code and code not in mapping:
                    mapping[code] = i
            score = sum(1 for code in HOLE_CODES if code in mapping)
            key = (score, len(ctrl.leds))
            if best is None or key > best[0]:
                best = (key, ctrl, mapping)
        if best is None:
            raise RuntimeError("指定的设备不存在（device_index=%r）" % (self.device_index,))

        (score, _n_leds), ctrl, mapping = best
        self.controller = ctrl
        self.device_label = str(ctrl)
        self.client.set_custom_mode(ctrl.index)      # 切 Direct，否则固件灯效会盖掉
        self._base = list(ctrl.colors) or [OFF] * len(ctrl.leds)
        if len(self._base) < len(ctrl.leds):
            self._base += [OFF] * (len(ctrl.leds) - len(self._base))

        if score >= 6:
            self.mode = "perkey"
            self._index = mapping
            self.tier = Tier.PER_KEY
            return

        slices = _zone_slices(ctrl)
        if not slices or not ctrl.leds:
            raise RuntimeError(
                "这台设备既认不出键名（%d/15），也没有分区可用（%d 个 LED）"
                % (score, len(ctrl.leds)))
        self.mode = "zones"
        self._index = {}
        self._slices = slices
        self.zones = _chunks(HOLE_ORDER, len(slices))
        self.tier = Tier.WHOLE if len(slices) == 1 else Tier.ZONES

    def close(self) -> None:
        if self.client is None:
            return
        try:
            if self.controller is not None and self._base:
                self.client.update_leds(self.controller.index, self._base)   # 还原原色
        except Exception:
            pass
        finally:
            self.client.close()
            self.client = None

    def supported_keys(self) -> Sequence[str]:
        if self.mode == "zones":
            return tuple(HOLE_CODES)
        return tuple(self._index)

    # ---- 渲染 ----

    def _commit(self, frame: Mapping[str, Rgb]) -> None:
        if self.client is None or self.controller is None:
            return
        colors = list(self._base)
        if self.mode == "perkey":
            for code, rgb in frame.items():
                i = self._index.get(code)
                if i is not None:
                    colors[i] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        else:
            for (start, count), bucket in zip(self._slices, self.zones):
                rgb = aggregate(frame, bucket)
                for j in range(start, min(start + count, len(colors))):
                    colors[j] = rgb
        self.client.update_leds(self.controller.index, colors)
