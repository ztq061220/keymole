"""列出当前插着的所有 HID 设备：VID/PID、产品名、usage page —— 判断谁能点灯。

    python -m tools.inventory
"""
from __future__ import annotations

import ctypes
from collections import defaultdict

from .probe_via import attrs_of, caps_of, k32, list_paths, open_hid

hid = ctypes.WinDLL("hid.dll")


def product_string(h) -> str:
    buf = ctypes.create_unicode_buffer(256)
    if hid.HidD_GetProductString(ctypes.c_void_p(h), buf, ctypes.sizeof(buf)):
        return buf.value.strip()
    return ""


def main() -> int:
    rows = []
    for path in list_paths():
        h = open_hid(path)
        if not h:
            continue
        try:
            a = attrs_of(h)
            c = caps_of(h)
            if not a or not c:
                continue
            rows.append({
                "vid": a.VendorID, "pid": a.ProductID,
                "page": c.UsagePage, "usage": c.Usage,
                "product": product_string(h),
                "path": path,
            })
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))

    groups = defaultdict(list)
    for r in rows:
        groups[(r["vid"], r["pid"], r["product"])].append(r)

    print("当前 HID 设备（%d 个接口 / %d 个设备）" % (len(rows), len(groups)))
    print("=" * 78)
    for (vid, pid, name), items in sorted(groups.items()):
        pages = sorted({i["page"] for i in items})
        flags = []
        if any(p == 0x59 for p in pages):
            flags.append("LampArray(动态光效)")
        if any(0xFF00 <= p <= 0xFFFF for p in pages):
            flags.append("厂商私有页")
        if pages == [0x01]:
            flags.append("纯键盘")
        print("VID_%04X PID_%04X  %-28s 页=%s  %s"
              % (vid, pid, (name or "(无产品名)")[:28],
                 ",".join("0x%02X" % p for p in pages), " ".join(flags)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
