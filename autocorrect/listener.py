import ctypes
import ctypes.wintypes as wt

from .corrector import Corrector
from .win32 import (
    RAWINPUTDEVICE, RAWINPUTHEADER, RAWKEYBOARD, WNDCLASSEXW, WNDPROC,
    WM_INPUT, RID_INPUT, RIM_TYPEKEYBOARD, RIDEV_INPUTSINK, RI_KEY_BREAK,
    SELF_TAG, user32, kernel32,
)


def run(corrector: Corrector):
    raw_buf = (ctypes.c_ubyte * 64)()
    hdr_sz = ctypes.sizeof(RAWINPUTHEADER)

    def wnd_proc(hwnd, msg, wp, lp):
        if msg == WM_INPUT:
            sz = ctypes.c_uint(64)
            user32.GetRawInputData(
                ctypes.c_void_p(lp), RID_INPUT,
                raw_buf, ctypes.byref(sz), hdr_sz,
            )
            hdr = RAWINPUTHEADER.from_buffer(raw_buf)
            if hdr.dwType == RIM_TYPEKEYBOARD:
                kb = RAWKEYBOARD.from_buffer(raw_buf, hdr_sz)
                if kb.ExtraInformation != SELF_TAG and not (kb.Flags & RI_KEY_BREAK):
                    corrector.feed(kb.VKey, kb.MakeCode)
            user32.DefWindowProcW(hwnd, msg, wp, lp)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    cb = WNDPROC(wnd_proc)
    hinst = kernel32.GetModuleHandleW(None)
    cls_name = "AcRawInput"

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = cb
    wc.hInstance = hinst
    wc.lpszClassName = cls_name
    if not user32.RegisterClassExW(ctypes.byref(wc)):
        raise RuntimeError(f"RegisterClassExW failed ({ctypes.GetLastError()})")

    # HWND_MESSAGE (-3) = message-only window, no visible UI
    hwnd = user32.CreateWindowExW(
        0, cls_name, None, 0, 0, 0, 0, 0,
        ctypes.c_void_p(-3), None, hinst, None,
    )
    if not hwnd:
        raise RuntimeError(f"CreateWindowExW failed ({ctypes.GetLastError()})")

    rid = RAWINPUTDEVICE()
    rid.usUsagePage = 0x01
    rid.usUsage = 0x06
    rid.dwFlags = RIDEV_INPUTSINK
    rid.hwndTarget = hwnd
    if not user32.RegisterRawInputDevices(
        ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)
    ):
        raise RuntimeError(f"RegisterRawInputDevices failed ({ctypes.GetLastError()})")

    print("autocorrect active")

    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
