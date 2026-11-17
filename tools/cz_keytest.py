"""逐个点亮 15 个洞位，确认键位映射对不对（肉眼校对用）。

用法：python -m tools.cz_keytest [--hold 1.2]
"""

from __future__ import annotations

import argparse
import sys
import time

from keymole import hidwin
from keymole.display.vendor import ace68

GRID = {
    "q": "第 1 行第 1 个洞（最左上）", "w": "第 1 行第 2 个", "e": "第 1 行第 3 个",
    "r": "第 1 行第 4 个", "t": "第 1 行第 5 个",
    "a": "第 2 行第 1 个（左中）", "s": "第 2 行第 2 个", "d": "第 2 行第 3 个（正中）",
    "f": "第 2 行第 4 个", "g": "第 2 行第 5 个",
    "z": "第 3 行第 1 个（左下）", "x": "第 3 行第 2 个", "c": "第 3 行第 3 个",
    "v": "第 3 行第 4 个", "b": "第 3 行第 5 个",
}

AMBER = (255, 176, 32)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=float, default=1.2)
    ap.add_argument("--key", default="", help="只点亮这一个键，例如 d")
    args = ap.parse_args(argv)

    handle, caps, name = ace68.find_interface()
    if not handle:
        print("没找到 Ace 68 的可写接口")
        return 1
    print("接口：%s  输出报文 %d 字节" % (name, caps.OutputReportByteLength))

    codes = [args.key.lower()] if args.key else list(ace68.HOLE_CODES)
    try:
        for code in codes:
            led = ace68.key_led(code)
            colors = [0] * (ace68.LED_COUNT * 3)
            if led is not None:
                colors[led * 3:led * 3 + 3] = list(AMBER)
            ok = 0
            for frame in ace68.build_frames(bytes(colors)):
                payload = bytes([ace68.REPORT_ID]) + frame
                if hidwin.send_report_timeout(handle, payload, len(payload), 400):
                    ok += 1
            print("  %-2s → LED %3s  %s   (%d/%d 包)" % (
                code.upper(), led, GRID.get(code, ""), ok, len(ace68.build_frames(bytes(colors)))))
            time.sleep(args.hold)
        colors = [0] * (ace68.LED_COUNT * 3)
        for frame in ace68.build_frames(bytes(colors)):
            hidwin.send_report_timeout(handle, bytes([ace68.REPORT_ID]) + frame, 65, 400)
        print("完成：%s" % ("只点亮了 %s" % args.key.upper() if args.key else "15 个洞位已逐个点亮过一遍"))
    finally:
        hidwin.close_hid(handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
