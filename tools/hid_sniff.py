"""只读监听：把迈从设备各接口收到的 HID 输入报文写进日志。

用于「让官方 HUB 去点灯，我这边只听它回什么」——不写入、不改任何设备状态。

用法：python -m tools.hid_sniff [--seconds 60] [--vid 3837] [--log hid_sniff.log]
"""
from __future__ import annotations

import argparse
import time

import keymole.hidwin as hw


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--vid", default="3837")
    ap.add_argument("--log", default="hid_sniff.log")
    args = ap.parse_args(argv)

    handles = []
    for path in hw.list_paths():
        if "vid_%s" % args.vid not in path:
            continue
        h = hw.open_hid(path, write=False)
        if not h:
            continue
        caps = hw.caps_of(h)
        if caps.InputReportByteLength < 16:
            hw.close_hid(h)
            continue
        tag = path.split("#")[1] if path.count("#") > 1 else path
        handles.append((tag, h, caps))

    with open(args.log, "w", encoding="utf-8") as f:
        f.write("# 监听 %d 个接口，%.0f 秒\n" % (len(handles), args.seconds))
        for tag, _, caps in handles:
            f.write("# %s in=%d\n" % (tag, caps.InputReportByteLength))
        f.flush()
        t0 = time.time()
        while time.time() - t0 < args.seconds:
            for tag, h, caps in handles:
                rep = hw.read_report_timeout(h, caps.InputReportByteLength, 5)
                if rep:
                    f.write("%7.3f %s %s\n" % (time.time() - t0, tag, rep.hex()))
                    f.flush()
    for _, h, _ in handles:
        hw.close_hid(h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
