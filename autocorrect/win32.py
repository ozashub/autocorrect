import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SELF_TAG = 0xDEADAC
INPUT_KBD = 1
KF_UNICODE = 0x0004
KF_KEYUP = 0x0002
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CTRL = 0x11
VK_ALT = 0x12
VK_CAPS = 0x14
VK_SPACE = 0x20

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100
RI_KEY_BREAK = 1


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wt.USHORT),
        ("usUsage", wt.USHORT),
        ("dwFlags", wt.DWORD),
        ("hwndTarget", ctypes.c_void_p),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wt.DWORD),
        ("dwSize", wt.DWORD),
        ("hDevice", ctypes.c_void_p),
        ("wParam", ctypes.c_size_t),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wt.USHORT),
        ("Flags", wt.USHORT),
        ("Reserved", wt.USHORT),
        ("VKey", wt.USHORT),
        ("Message", wt.UINT),
        ("ExtraInformation", wt.ULONG),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]
    _fields_ = [("type", wt.DWORD), ("u", _U)]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint,
    ctypes.c_size_t, ctypes.c_ssize_t,
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


user32.DefWindowProcW.argtypes = [
    ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.CreateWindowExW.restype = ctypes.c_void_p
user32.RegisterClassExW.restype = wt.ATOM
user32.GetRawInputData.restype = ctypes.c_uint
user32.SendInput.restype = wt.UINT
user32.ToUnicode.restype = ctypes.c_int
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetKeyState.restype = ctypes.c_short


def vkey_to_char(vk, scan):
    if user32.GetAsyncKeyState(VK_CTRL) & 0x8000:
        return None
    if user32.GetAsyncKeyState(VK_ALT) & 0x8000:
        return None
    state = (ctypes.c_ubyte * 256)()
    for k in (VK_SHIFT, 0xA0, 0xA1):
        if user32.GetAsyncKeyState(k) & 0x8000:
            state[k] = 0x80
    state[VK_CAPS] = user32.GetKeyState(VK_CAPS) & 0xFF
    buf = (ctypes.c_wchar * 4)()
    # flag 0x4 = don't mess with dead key state
    n = user32.ToUnicode(vk, scan, state, buf, 4, 0x4)
    if n >= 1:
        return buf[0]
    return None


def nuke_and_retype(n_back, text):
    evts = []
    for _ in range(n_back):
        for fl in (0, KF_KEYUP):
            e = _INPUT(type=INPUT_KBD)
            e.u.ki.wVk = VK_BACK
            e.u.ki.dwFlags = fl
            e.u.ki.dwExtraInfo = SELF_TAG
            evts.append(e)
    for ch in text:
        for fl in (KF_UNICODE, KF_UNICODE | KF_KEYUP):
            e = _INPUT(type=INPUT_KBD)
            e.u.ki.wScan = ord(ch)
            e.u.ki.dwFlags = fl
            e.u.ki.dwExtraInfo = SELF_TAG
            evts.append(e)
    arr = (_INPUT * len(evts))(*evts)
    user32.SendInput(len(evts), arr, ctypes.sizeof(_INPUT))
