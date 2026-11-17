"""Replay the Ace68 (Cizhou family) light protocol captured from MCHOSE HUB."""

import sys
import time

from keymole import hidwin

VID = 0x41E4
PID = 0x2116
MAGIC = 0x55
CMD_LIGHT = 0x0B
CONST = 0x38
CHUNK = 56
PAGE = 0


def build_frames(rgb_bytes, page=PAGE):
    frames = []
    addr = 0
    total = len(rgb_bytes)
    while addr < total:
        chunk = rgb_bytes[addr:addr + CHUNK]
        chunk = chunk + bytes(CHUNK - len(chunk))
        frame = bytearray(64)
        frame[0] = MAGIC
        frame[1] = CMD_LIGHT
        frame[2] = 0
        frame[4] = CONST
        frame[5] = addr & 0xFF
        frame[6] = (addr >> 8) & 0xFF
        frame[7] = page
        frame[8:8 + CHUNK] = chunk
        frame[3] = sum(frame[4:]) & 0xFF
        frames.append(bytes(frame))
        addr += CHUNK
    return frames


def find_device():
    for path in hidwin.list_paths():
        handle = hidwin.open_hid(path, write=True)
        if not handle:
            continue
        attrs = hidwin.attrs_of(handle)
        caps = hidwin.caps_of(handle)
        if (attrs and attrs.VendorID == VID and attrs.ProductID == PID
                and caps and caps.OutputReportByteLength >= 32):
            return path, handle, caps
        hidwin.close_hid(handle)
    return None, None, None


def solid(count, rgb):
    return bytes(rgb) * count


def bars(count):
    out = bytearray()
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    for i in range(count):
        out.extend(colors[(i // 64) % len(colors)])
    return bytes(out)


def main(argv):
    count = 384
    mode = "green"
    hold = 3.0
    for arg in argv:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
        elif arg.startswith("--leds="):
            count = int(arg.split("=", 1)[1])
        elif arg.startswith("--hold="):
            hold = float(arg.split("=", 1)[1])

    path, handle, caps = find_device()
    if not handle:
        print("没找到 Ace68 的可写接口")
        return 1
    print("接口:", path)
    print("caps out=%d in=%d" % (caps.OutputReportByteLength, caps.InputReportByteLength))

    if mode == "bars":
        data = bars(count)
    elif mode == "off":
        data = solid(count, (0, 0, 0))
    elif mode == "red":
        data = solid(count, (255, 0, 0))
    elif mode == "blue":
        data = solid(count, (0, 0, 255))
    else:
        data = solid(count, (0, 255, 0))

    frames = build_frames(data)
    print("载荷 %d 字节，%d 包" % (len(data), len(frames)))
    ok = 0
    for frame in frames:
        payload = bytes([0x00]) + frame
        if hidwin.send_report_timeout(handle, payload, len(payload), 400):
            ok += 1
    print("写入成功 %d/%d" % (ok, len(frames)))
    time.sleep(hold)
    hidwin.close_hid(handle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
