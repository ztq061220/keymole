"""对着假 OpenRGB 服务器跑一遍 L3 后端：握手 → 解析设备 → 点灯。

    python -m tools.test_orgb
"""
from __future__ import annotations

import time

from keymole.display.openrgb import OpenRGBDisplay
from keymole.core.layout import HOLE_CODES
from keymole.render import HIT, OFF
from keymole.display.mock import MockServer

PORT = 16742


def main() -> int:
    srv = MockServer(PORT)
    srv.start()
    time.sleep(0.2)

    disp = OpenRGBDisplay(port=PORT)
    disp.open()
    print("连上：", disp.device_label)
    keys = disp.supported_keys()
    print("识别出 %d 个键，其中洞位 %d/15" % (len(keys), sum(c in keys for c in HOLE_CODES)))
    assert sum(c in keys for c in HOLE_CODES) == 15, "15 个洞位必须全部识别"

    frame = {c: OFF for c in HOLE_CODES}
    frame["a"] = HIT
    disp.flush(frame)

    ctrl = srv.controller
    for _ in range(300):                 # 服务器是异步的，等它收完这一帧
        if ctrl.updates:
            break
        time.sleep(0.01)
    idx = ctrl.codes.index("a")
    got = ctrl.colors[idx]
    print("A 键收到颜色：", got, " 提交次数：", ctrl.updates, " Direct 模式：", ctrl.direct)
    assert got == HIT, "颜色没送到正确位置：%r != %r" % (got, HIT)
    assert ctrl.direct, "应该已经切到 Direct 模式"
    disp.close()
    srv.stop()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
