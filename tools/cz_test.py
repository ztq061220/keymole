
"""CZ（磁轴/新固件）灯效写入试验：rid 0x4D + 7 字节头 + 控件字节 + 逐键 RGB。"""
import sys, time, argparse
from keymole import hidwin

REPORT_ID = 0x4D
CMD_LIGHT = 772          # 0x0304
MAX_DATA = 23            # 31 - 7 - 1

GRID = {"q": (2, 2), "w": (2, 3), "e": (2, 4), "r": (2, 5), "t": (2, 6),
        "a": (3, 2), "s": (3, 3), "d": (3, 4), "f": (3, 5), "g": (3, 6),
        "z": (4, 2), "x": (4, 3), "c": (4, 4), "v": (4, 5), "b": (4, 6)}


def rc_byte(row, col):
    return (row & 7) | ((col & 31) << 3)


def control(packet_type, count):
    return (packet_type & 3) | ((count & 63) << 2)


def frame(seq, cmd, data):
    payload = bytearray([1, 3, len(data), cmd & 0xFF, (cmd >> 8) & 0xFF, 0, seq & 0xFF])
    payload += bytes(data)
    chk = 0
    for b in payload[1:]:
        chk ^= b
    payload.append(chk)
    return bytes(payload)


def light_packets(colors, page=0, per_packet=5):
    """colors: list of (row, col, r, g, b)"""
    out = []
    for i in range(0, len(colors), per_packet):
        chunk = colors[i:i + per_packet]
        body = bytearray([page, 0])
        for row, col, r, g, b in chunk:
            body += bytes([rc_byte(row, col), r, g, b])
        first = i == 0
        last = i + per_packet >= len(colors)
        ptype = 3 if (first and last) else (1 if first else (2 if last else 0))
        body[1] = control(ptype, len(chunk))
        out.append(bytes(body))
    return out


def find(vid, pid):
    for path in hidwin.list_paths():
        h = hidwin.open_hid(path, write=True)
        if not h:
            continue
        try:
            a = hidwin.attrs_of(h)
            c = hidwin.caps_of(h)
        except Exception:
            hidwin.close_hid(h)
            continue
        if a.VendorID == vid and a.ProductID == pid and c.OutputReportByteLength >= 32:
            return h, c, path
        hidwin.close_hid(h)
    return None, None, None


def send(h, caps, payload, rid):
    size = caps.OutputReportByteLength
    buf = bytearray(size)
    buf[0] = rid
    buf[1:1 + len(payload)] = payload
    return hidwin.send_report(h, bytes(buf), size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vid", type=lambda s: int(s, 0), default=0x41E4)
    ap.add_argument("--pid", type=lambda s: int(s, 0), default=0x2116)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--all-keys", action="store_true")
    ap.add_argument("--rid", type=lambda x: int(x, 0), default=REPORT_ID)
    a = ap.parse_args()
    h, caps, path = find(a.vid, a.pid)
    if not h:
        print("没找到设备 %04X:%04X" % (a.vid, a.pid))
        return 1
    print("接口: %s" % path.split("#")[-1][:40])
    print("caps out=%d in=%d" % (caps.OutputReportByteLength, caps.InputReportByteLength))
    keys = []
    for i in range(6):
        for j in range(18):
            keys.append((i, j))
    if not a.all_keys:
        keys = [(2, 2), (2, 3), (2, 4), (2, 5), (2, 6), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6),
                (4, 2), (4, 3), (4, 4), (4, 5), (4, 6)]
    plans = [((255, 0, 0), "红"), ((0, 0, 0), "灭"), ((0, 255, 0), "绿")]
    seq = 0
    for color, name in plans:
        entries = [(r, c, color[0], color[1], color[2]) for (r, c) in keys]
        total = 0
        ok = 0
        for body in light_packets(entries):
            pkt = frame(seq, CMD_LIGHT, body)
            seq = (seq + 1) & 0xFF
            total += 1
            if send(h, caps, pkt, a.rid):
                ok += 1
            time.sleep(0.01)
        print("%s: %d/%d 包写入成功（%d 键）" % (name, ok, total, len(keys)))
        time.sleep(a.seconds)
    hidwin.close_hid(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
