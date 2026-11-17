"""整键盘闪烁测试：把所有可写的迈从厂商接口挨个试一遍，全绿 / 全灭。

用法：python -m keymole.mchose_blink [--rounds 3]
每个接口之间停 1 秒，方便你盯着键盘看是哪一个在响应。
"""
from __future__ import annotations

import argparse
import time

import keymole.hidwin as hw
from keymole.display.vendor import mchose

VIDS = (0x1015, 0x1014, 0x1012)


def candidates():
    out = []
    for pid in VIDS:
        for path in hw.list_paths():
            if "vid_3837&pid_%04x" % pid not in path:
                continue
            h = hw.open_hid_overlapped(path, write=True)
            if not h:
                continue
            caps = hw.caps_of(h)
            if caps.OutputReportByteLength >= 20:
                out.append((pid, path, h, caps))
            else:
                hw.close_hid(h)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args(argv)

    keys = list(mchose.KEY_INDEX)
    green = {k: (0, 255, 0) for k in keys}
    off = {k: (0, 0, 0) for k in keys}

    found = candidates()
    print("可写接口 %d 个" % len(found))
    for pid, path, h, caps in found:
        tag = path.split("#")[1] if path.count("#") > 1 else path
        print("")
        print(">>> 现在测 %04X  %s  (out=%d in=%d feat=%d)"
              % (pid, tag, caps.OutputReportByteLength, caps.InputReportByteLength,
                 caps.FeatureReportByteLength))
        sent = 0
        for i in range(args.rounds):
            frame = green if i % 2 == 0 else off
            payload = mchose.build_payload(frame)
            for pkt in mchose.split_frames(payload):
                if hw.send_report_timeout(h, pkt, caps.OutputReportByteLength, 150):
                    sent += 1
            print("    第 %d 轮 %s" % (i + 1, "全绿" if i % 2 == 0 else "全灭"))
            time.sleep(1.2)
        rep = hw.read_report_timeout(h, max(caps.InputReportByteLength, 2), 200)
        print("    写入 %d 片，回包：%s" % (sent, rep[:12].hex() if rep else "无"))
        hw.close_hid(h)
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
