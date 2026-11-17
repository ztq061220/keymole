"""真机试验：往迈从键盘推一帧逐键颜色，让人肉眼看。

用法：python -m keymole.mchose_test [--seconds 10] [--pattern bars|single]
"""
from __future__ import annotations

import argparse
import time

from .display.vendor import mchose
from .core.layout import HOLE_ROWS

BAR = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 160, 0), (200, 0, 255)]


def make_frame(pattern: str, step: int):
    frame = {}
    for row_i, row in enumerate(HOLE_ROWS):
        for col_i, code in enumerate(row):
            if pattern == "single":
                on = (col_i == step % len(row)) and (row_i == (step // len(row)) % 3)
                frame[code] = BAR[row_i] if on else (0, 0, 0)
            else:
                frame[code] = BAR[(col_i + step) % len(BAR)]
    return frame


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--pattern", choices=("bars", "single"), default="bars")
    args = ap.parse_args(argv)

    ok, detail = mchose.probe()
    print("探测：%s %s" % ("[OK]" if ok else "[--]", detail))
    if not ok:
        return 1
    disp = mchose.MchoseDisplay()
    disp.open()
    print("接口：%s" % disp.device_label)
    start = time.time()
    step = 0
    while time.time() - start < args.seconds:
        disp.flush(make_frame(args.pattern, step))
        step += 1
        time.sleep(0.35)
    disp.close()
    print("共提交 %d 帧，收到 %d 个回包" % (disp.sent, disp.acked))
    if disp.last_error:
        print("问题：%s" % disp.last_error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
