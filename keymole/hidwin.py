"""Windows HID 底层（ctypes，不装 hidapi）：枚举接口 / 读 caps / 读写报文。"""
from __future__ import annotations

import ctypes
from typing import List, Optional
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
    # cbSize 按 MSDN：x64=8, x86=6 ---- 不是 sizeof(结构体)
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
hid.HidD_GetProductString.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.ULONG]
hid.HidD_GetProductString.restype = w.BOOL
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                            w.DWORD, w.DWORD, ctypes.c_void_p]
k32.CreateFileW.restype = ctypes.c_void_p
k32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD,
                          ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD,
                         ctypes.POINTER(w.DWORD), ctypes.c_void_p]
k32.CloseHandle.argtypes = [ctypes.c_void_p]


def list_paths() -> List[str]:
    """所有 HID 设备接口路径（本机通常一百多个）。"""
    flags = 0x00000010 | 0x00000008      # PRESENT | DEVICEINTERFACE
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(GUID_DEVINTERFACE_HID), None, None, flags)
    if not hdev or hdev == INVALID_HANDLE_VALUE:
        return []
    out: List[str] = []
    i = 0
    while True:
        did = SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(did)
        if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None,
                                                    ctypes.byref(GUID_DEVINTERFACE_HID),
                                                    i, ctypes.byref(did)):
            break
        need = w.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), None, 0,
                                                  ctypes.byref(need), None)
        buf = ctypes.create_string_buffer(need.value)
        detail = ctypes.cast(buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
        detail.contents.cbSize = DETAIL_CBSIZE
        if setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), detail,
                                                     need.value, None, None):
            out.append(detail.contents.DevicePath)
        i += 1
    setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def open_hid(path: str, write: bool = True):
    access = (GENERIC_READ | GENERIC_WRITE) if write else 0
    h = k32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        None, OPEN_EXISTING, 0, None)
    if not h or h == INVALID_HANDLE_VALUE:
        return None
    return h


def close_hid(h) -> None:
    k32.CloseHandle(ctypes.c_void_p(h))


def caps_of(h) -> Optional[HIDP_CAPS]:
    prep = ctypes.c_void_p()
    if not hid.HidD_GetPreparsedData(ctypes.c_void_p(h), ctypes.byref(prep)):
        return None
    caps = HIDP_CAPS()
    ok = hid.HidP_GetCaps(prep, ctypes.byref(caps))
    hid.HidD_FreePreparsedData(prep)
    return caps if ok else None


def attrs_of(h) -> Optional[HIDD_ATTRIBUTES]:
    a = HIDD_ATTRIBUTES()
    a.Size = ctypes.sizeof(a)
    return a if hid.HidD_GetAttributes(ctypes.c_void_p(h), ctypes.byref(a)) else None


def product_string(h) -> str:
    buf = ctypes.create_unicode_buffer(256)
    if hid.HidD_GetProductString(ctypes.c_void_p(h), buf, ctypes.sizeof(buf)):
        return buf.value.strip()
    return ""


def send_report(h, payload: bytes, size: int) -> bool:
    buf = (ctypes.c_ubyte * size)()
    for i, b in enumerate(payload[:size]):
        buf[i] = b
    written = w.DWORD(0)
    return bool(k32.WriteFile(ctypes.c_void_p(h), buf, size, ctypes.byref(written), None))


def read_report(h, size: int) -> bytes:
    buf = (ctypes.c_ubyte * size)()
    got = w.DWORD(0)
    if k32.ReadFile(ctypes.c_void_p(h), buf, size, ctypes.byref(got), None):
        return bytes(buf[:got.value])
    return b""


hid.HidD_SetFeature.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.ULONG]
hid.HidD_SetFeature.restype = w.BOOL
hid.HidD_GetFeature.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.ULONG]
hid.HidD_GetFeature.restype = w.BOOL


def send_feature(h, payload: bytes) -> bool:
    """payload[0] 是 report id，整体不能超过 FeatureReportByteLength。"""
    size = len(payload)
    buf = (ctypes.c_ubyte * size)(*payload)
    return bool(hid.HidD_SetFeature(ctypes.c_void_p(h), buf, size))


def get_feature(h, size: int) -> bytes:
    buf = (ctypes.c_ubyte * size)()
    if not hid.HidD_GetFeature(ctypes.c_void_p(h), buf, size):
        return b""
    return bytes(buf)


FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", w.DWORD), ("OffsetHigh", w.DWORD),
                ("hEvent", ctypes.c_void_p)]


k32.CreateEventW.restype = ctypes.c_void_p
k32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, ctypes.c_wchar_p]
k32.WaitForSingleObject.restype = w.DWORD
k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, w.DWORD]
k32.GetOverlappedResult.restype = w.BOOL
k32.GetOverlappedResult.argtypes = [ctypes.c_void_p, ctypes.POINTER(OVERLAPPED),
                                    ctypes.POINTER(w.DWORD), w.BOOL]
k32.CancelIo.argtypes = [ctypes.c_void_p]
k32.ResetEvent.argtypes = [ctypes.c_void_p]


def open_hid_overlapped(path: str, write: bool = True):
    access = (GENERIC_READ | GENERIC_WRITE) if write else 0
    h = k32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if not h or h == INVALID_HANDLE_VALUE:
        return None
    return h


def read_report_timeout(h, size: int, ms: int = 300) -> bytes:
    """带超时的读；超时返回空串（不会卡住线程）。"""
    ov = OVERLAPPED()
    ov.hEvent = k32.CreateEventW(None, True, False, None)
    buf = (ctypes.c_ubyte * size)()
    got = w.DWORD(0)
    ok = k32.ReadFile(ctypes.c_void_p(h), buf, size, ctypes.byref(got), ctypes.byref(ov))
    if not ok:
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            return b""
        rc = k32.WaitForSingleObject(ov.hEvent, ms)
        if rc != 0:
            k32.CancelIo(ctypes.c_void_p(h))
            k32.WaitForSingleObject(ov.hEvent, 100)
            return b""
        if not k32.GetOverlappedResult(ctypes.c_void_p(h), ctypes.byref(ov),
                                       ctypes.byref(got), False):
            return b""
    return bytes(buf[:got.value])


def send_report_timeout(h, payload: bytes, size: int, ms: int = 500) -> bool:
    ov = OVERLAPPED()
    ov.hEvent = k32.CreateEventW(None, True, False, None)
    buf = (ctypes.c_ubyte * size)()
    for i, b in enumerate(payload[:size]):
        buf[i] = b
    got = w.DWORD(0)
    ok = k32.WriteFile(ctypes.c_void_p(h), buf, size, ctypes.byref(got), ctypes.byref(ov))
    if not ok:
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            return False
        if k32.WaitForSingleObject(ov.hEvent, ms) != 0:
            k32.CancelIo(ctypes.c_void_p(h))
            return False
        if not k32.GetOverlappedResult(ctypes.c_void_p(h), ctypes.byref(ov),
                                      ctypes.byref(got), False):
            return False
    return True

k32.WaitForMultipleObjects.argtypes = [w.DWORD, ctypes.POINTER(w.HANDLE), w.BOOL, w.DWORD]
k32.WaitForMultipleObjects.restype = w.DWORD
k32.GetOverlappedResult.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED),
                                    ctypes.POINTER(w.DWORD), w.BOOL]
k32.GetOverlappedResult.restype = w.BOOL


def send_reports(handle, payloads, timeout_ms: int = 80):
    """把多包一次性发出去（异步 + 一起等），比逐包串行快 3~4 倍。

    WriteFile 用 OVERLAPPED 发起后立刻发下一包，最后统一等；
    串行发送时每包都要等设备一个轮询周期（实测 ~8ms），4 包就是 32ms。
    """
    payloads = [bytes(p) for p in payloads]
    n = len(payloads)
    if not n:
        return 0
    events = (w.HANDLE * n)()
    keep = []
    pending = [False] * n
    ok = 0
    written = w.DWORD(0)
    for i, data in enumerate(payloads):
        buf = ctypes.create_string_buffer(data, len(data))
        ov = OVERLAPPED()
        ev = k32.CreateEventW(None, True, False, None)
        ov.hEvent = ev
        events[i] = ev
        keep.append((buf, ov))
        if k32.WriteFile(handle, buf, len(data), ctypes.byref(written), ctypes.byref(ov)):
            ok += 1
        elif ctypes.get_last_error() == ERROR_IO_PENDING:
            pending[i] = True
    if any(pending):
        k32.WaitForMultipleObjects(n, events, False, timeout_ms)
        for i, flag in enumerate(pending):
            if not flag:
                continue
            got = w.DWORD(0)
            if k32.GetOverlappedResult(handle, ctypes.byref(keep[i][1]),
                                            ctypes.byref(got), False):
                ok += 1
    for i in range(n):
        if events[i]:
            k32.CloseHandle(events[i])
    return ok
