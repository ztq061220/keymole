
"""持续闪烁：给肉眼确认用（红/绿/灭 循环）。"""
import sys, time
from tools import cz_test as cz
from keymole import hidwin

def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rid = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x4E
    h, caps, path = cz.find(0x41E4, 0x2116)
    if not h:
        print("no device"); return 1
    keys = [(r, c) for r in range(6) for c in range(18)]
    seq = 0
    plans = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    for i in range(cycles):
        color = plans[i % 3]
        entries = [(r, c, color[0], color[1], color[2]) for (r, c) in keys]
        for body in cz.light_packets(entries):
            pkt = cz.frame(seq, cz.CMD_LIGHT, body)
            seq = (seq + 1) & 0xFF
            cz.send(h, caps, pkt, rid)
        time.sleep(0.8)
    hidwin.close_hid(h)
    return 0

if __name__ == "__main__":
    sys.exit(main())
