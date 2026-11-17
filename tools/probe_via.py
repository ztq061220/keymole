"""探测键盘是否说 VIA / QMK raw HID（usage page 0xFF60 / usage 0x61）。

只做最安全的一件事：发一个 `id_get_protocol_version`(0x01) 空包，看它回不回。
回了就说明这块键盘的固件开放了 raw HID 通道 —— 那么逐键点灯、甚至改键都有了入口。

    python -m tools.probe_via
    python -m tools.probe_via --any      # 连厂商自定义页(0xFF00-0xFFFF)的也试
"""
from __future__ import annotations

import argparse
import ctypes
import threading
from ctypes import wintypes as w

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

hid = ctypes.WinDLL("hid.dll")
setupapi = ctypes.WinDLL("setupapi.dll")
k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", w.DWORD), ("Reserved", ctypes.c_void_p)]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    # cbSize 按 MSDN：x64=8, x86=6 —— 不是 sizeof(结构体)
    _fields_ = [("cbSize", w.DWORD), ("DevicePath", ctypes.c_wchar * 1024)]


DETAIL_CBSIZE = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", w.ULONG), ("VendorID", w.USHORT), ("ProductID", w.USHORT),
                ("VersionNumber", w.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", w.USHORT), ("UsagePage", w.USHORT),
        ("InputReportByteLength", w.USHORT), ("OutputReportByteLength", w.USHORT),
        ("FeatureReportByteLength", w.USHORT),
        ("Reserved", w.USHORT * 17),
        ("NumberLinkCollectionNodes", w.ULONG),
        ("NumberInputButtonCaps", w.ULONG), ("NumberInputValueCaps", w.ULONG),
        ("NumberInputDataIndices", w.ULONG),
        ("NumberOutputButtonCaps", w.ULONG), ("NumberOutputValueCaps", w.ULONG),
        ("NumberOutputDataIndices", w.ULONG),
        ("NumberFeatureButtonCaps", w.ULONG), ("NumberFeatureValueCaps", w.ULONG),
        ("NumberFeatureDataIndices", w.ULONG),
    ]


GUID_DEVINTERFACE_HID = GUID(0x4D1E55B2, 0xF16F, 0x11CF,
                             (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30))


setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), ctypes.c_wchar_p,
                                          ctypes.c_void_p, w.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.restype = w.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), w.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = w.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
hid.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = w.BOOL
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = w.BOOL
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_GetAttributes.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = w.BOOL
k32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD,
                          ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD,
                         ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.CloseHandle.argtypes = [ctypes.c_void_p]
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                            w.DWORD, w.DWORD, ctypes.c_void_p]
k32.CreateFileW.restype = ctypes.c_void_p


def list_paths() -> list[str]:
    flags = 0x00000010 | 0x00000008      # PRESENT | DEVICEINTERFACE
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(GUID_DEVINTERFACE_HID), None, None, flags)
    if not hdev or hdev == INVALID_HANDLE_VALUE:
        return []
    out = []
    i = 0
    while True:
        did = SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(did)
        if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(GUID_DEVINTERFACE_HID), i,
                                                    ctypes.byref(did)):
            break
        need = w.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), None, 0,
                                                  ctypes.byref(need), None)
        buf = ctypes.create_string_buffer(need.value)
        detail = ctypes.cast(buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
        detail.contents.cbSize = DETAIL_CBSIZE
        if setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), detail, need.value,
                                                     None, None):
            out.append(detail.contents.DevicePath)
        i += 1
    setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def open_hid(path: str):
    h = k32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        None, OPEN_EXISTING, 0, None)
    if h in (0, INVALID_HANDLE_VALUE):
        return None
    return h


def caps_of(h) -> HIDP_CAPS | None:
    prep = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(ctypes.c_void_p(h), ctypes.byref(prep)):
        return None
    caps = HIDP_CAPS()
    ok = hid.HidP_GetCaps(prep, ctypes.byref(caps))
    hid.HidD_FreePreparsedData(prep)
    return caps if ok else None


def attrs_of(h) -> HIDD_ATTRIBUTES | None:
    a = HIDD_ATTRIBUTES()
    a.Size = ctypes.sizeof(a)
    return a if hid.HidD_GetAttributes(ctypes.c_void_p(h), ctypes.byref(a)) else None


def via_handshake(h, caps: HIDP_CAPS, timeout: float = 1.5) -> bytes | None:
    """发 [report_id=0, 0x01]（id_get_protocol_version），等 32 字节回包。"""
    out_len = max(caps.OutputReportByteLength, 33)
    buf = (ctypes.c_ubyte * out_len)()
    buf[0] = 0x00
    buf[1] = 0x01
    written = w.DWORD(0)
    if not k32.WriteFile(ctypes.c_void_p(h), buf, out_len, ctypes.byref(written), None):
        return None

    result: dict[str, bytes] = {}

    def reader() -> None:
        in_len = max(caps.InputReportByteLength, 33)
        rbuf = (ctypes.c_ubyte * in_len)()
        got = w.DWORD(0)
        if k32.ReadFile(ctypes.c_void_p(h), rbuf, in_len, ctypes.byref(got), None):
            result["data"] = bytes(rbuf[:got.value])

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout)
    return result.get("data")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--any", action="store_true", help="也尝试其它厂商自定义 usage page")
    args = ap.parse_args()

    paths = list_paths()
    print("找到 %d 个 HID 接口" % len(paths))
    hits = 0
    for path in paths:
        h = open_hid(path)
        if h is None:
            continue
        try:
            caps = caps_of(h)
            attrs = attrs_of(h)
            if not caps or not attrs:
                continue
            vendor_page = 0xFF00 <= caps.UsagePage <= 0xFFFF
            is_via = caps.UsagePage == 0xFF60 and caps.Usage == 0x61
            if not (is_via or (args.any and vendor_page)):
                continue
            tag = "VIA" if is_via else "vendor"
            short = path.split("hid#")[-1][:46]
            print("\n[%s] VID_%04X PID_%04X  page=0x%04X usage=0x%04X  in/out=%d/%d\n       %s"
                  % (tag, attrs.VendorID, attrs.ProductID, caps.UsagePage, caps.Usage,
                     caps.InputReportByteLength, caps.OutputReportByteLength, short))
            reply = via_handshake(h, caps)
            if reply:
                print("       回包：%s" % reply[:8].hex(" "))
                if reply[:1] == b"\x01":
                    print("       >>> 这是 VIA 协议！固件支持 raw HID 控制（逐键 RGB 有望）")
                    hits += 1
            else:
                print("       无回包（不是 VIA，或需要在有线模式下）")
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    print("\nVIA 命中：%d" % hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
