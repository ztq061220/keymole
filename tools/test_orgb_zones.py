"""验证 L2 降级：一台「认不出键名、只有 4 个区」的键盘也能玩打地鼠。"""
from __future__ import annotations

import time

from keymole.display.base import Tier
from keymole.display.mock import MockController, MockServer
from keymole.display.openrgb import OpenRGBDisplay
from keymole.render import AMBER, HIT, OFF

PORT = 16743


def main() -> int:
    ctrl = MockController(name="Mock 4-Zone Keyboard", zone_counts=[16, 16, 16, 16])
    server = MockServer(port=PORT, controller=ctrl)
    server.start()

    disp = OpenRGBDisplay(port=PORT)
    disp.open()
    print("设备：", disp.device_label)
    print("模式：", disp.mode, "  能力：", disp.tier)
    assert disp.mode == "zones", disp.mode
    assert disp.tier == Tier.ZONES, disp.tier
    assert len(disp.zones) == 4, disp.zones

    frame = {code: OFF for code in disp.supported_keys()}
    frame["e"] = HIT
    frame["t"] = AMBER
    disp.flush(frame)

    for _ in range(300):
        if ctrl.updates:
            break
        time.sleep(0.01)
    assert ctrl.updates >= 1, "假键盘没收到颜色"

    print("四个区收到的颜色：")
    for (start, count), bucket in zip(disp._slices, disp.zones):
        print("  区 %d  灯 %2d..%2d  %s -> %s"
              % ((start // max(count, 1)) + 1, start, start + count - 1,
                 bucket[:6], ctrl.colors[start]))
    # 命中在 e 那一竖条 -> 第二个 16 灯区；地鼠在 t 那一竖条 -> 第四个区
    assert ctrl.colors[16] == HIT, ctrl.colors[16]
    assert ctrl.colors[48] == AMBER, ctrl.colors[48]
    assert ctrl.colors[0] != ctrl.colors[16], "第一个区不该跟命中区同色"
    assert ctrl.direct, "没进 Direct 模式"
    print("OK  L2 分区降级可用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
