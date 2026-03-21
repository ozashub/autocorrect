#!/usr/bin/env python3
import ctypes
import ctypes.wintypes as wt
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def _bootstrap():
    if importlib.util.find_spec("symspellpy") is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "symspellpy"])
        os.execv(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:])


_bootstrap()

from symspellpy import SymSpell, Verbosity

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


def _vkey_to_char(vk, scan):
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


def _nuke_and_retype(n_back, text):
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


GRAMMAR = {
    "aint": "ain't",
    "arent": "aren't",
    "cant": "can't",
    "cnat": "can't",
    "cmon": "c'mon",
    "coudlnt": "couldn't",
    "coulndt": "couldn't",
    "coudn": "couldn't",
    "coudln": "couldn't",
    "couldnt": "couldn't",
    "couldve": "could've",
    "didnt": "didn't",
    "didint": "didn't",
    "doesnt": "doesn't",
    "dosen": "doesn't",
    "doens": "doesn't",
    "dosn": "doesn't",
    "dont": "don't",
    "odnt": "don't",
    "hadnt": "hadn't",
    "hasnt": "hasn't",
    "havent": "haven't",
    "hed": "he'd",
    "heres": "here's",
    "hes": "he's",
    "howd": "how'd",
    "hows": "how's",
    "i": "I",
    "id": "I'd",
    "ill": "I'll",
    "im": "I'm",
    "isnt": "isn't",
    "itll": "it'll",
    "ive": "I've",
    "mightnt": "mightn't",
    "mightve": "might've",
    "mustnt": "mustn't",
    "oughtnt": "oughtn't",
    "shant": "shan't",
    "shes": "she's",
    "sholdnt": "shouldn't",
    "shoudlnt": "shouldn't",
    "shouldnt": "shouldn't",
    "shouldent": "shouldn't",
    "shouldve": "should've",
    "thats": "that's",
    "thtas": "that's",
    "thast": "that's",
    "theres": "there's",
    "theyd": "they'd",
    "theyll": "they'll",
    "theyre": "they're",
    "theyve": "they've",
    "tisn": "it's",
    "wasnt": "wasn't",
    "weere": "we're",
    "werent": "weren't",
    "weve": "we've",
    "whats": "what's",
    "whos": "who's",
    "whyd": "why'd",
    "wont": "won't",
    "woudlnt": "wouldn't",
    "wouldnt": "wouldn't",
    "wouldve": "would've",
    "yall": "y'all",
    "youd": "you'd",
    "youll": "you'll",
    "youre": "you're",
    "youve": "you've",
    "wed": "we'd",
}

WORD_BREAKS = set(";,.!?:")


class Corrector:
    MIN_FREQ = 1_000

    def __init__(self, dict_path: Path, personal_path: Path, cache_path: Path):
        self._spell = SymSpell(max_dictionary_edit_distance=3, prefix_length=7)
        if cache_path.exists():
            self._spell.load_pickle(str(cache_path))
        else:
            if not dict_path.exists() or dict_path.stat().st_size == 0:
                raise RuntimeError(f"missing dictionary: {dict_path}")
            self._spell.load_dictionary(str(dict_path), 0, 1)
            self._spell.save_pickle(str(cache_path))
        if personal_path.exists():
            self._spell.load_dictionary(str(personal_path), 0, 1)

        self._known = {
            word for word, freq in self._spell.words.items()
            if freq >= self.MIN_FREQ
        }
        self._buf: list[str] = []

        print(f"  dict: {len(self._spell.words)} entries, "
              f"{len(self._known)} known (freq >= {self.MIN_FREQ})")

    @staticmethod
    def _match_case(src: str, tgt: str) -> str:
        if src.isupper():
            return tgt.upper()
        if src[0].isupper():
            return tgt[0].upper() + tgt[1:]
        return tgt

    @staticmethod
    def _score(hit, low: str) -> float:
        s = -hit.distance * 20.0
        if hit.term[0] == low[0]:
            s += 15
        diff = abs(len(hit.term) - len(low))
        if diff == 0:
            s += 8
        elif diff == 1:
            s += 4
        s += min(hit.count / 50_000, 6)
        return s

    def _lookup(self, word: str) -> str | None:
        low = word.lower()

        gram = GRAMMAR.get(low)
        if gram:
            return self._match_case(word, gram)

        if len(low) < 3:
            return None
        if low in self._known:
            return None

        if len(low) <= 4:
            max_dist = 1
        elif len(low) <= 7:
            max_dist = 2
        else:
            max_dist = 3

        hits = self._spell.lookup(low, Verbosity.ALL, max_edit_distance=max_dist)
        if not hits:
            return None
        if hits[0].distance == 0 and hits[0].count >= self.MIN_FREQ:
            return None

        scored = [
            (h, self._score(h, low))
            for h in hits
            if h.count >= self.MIN_FREQ and h.distance > 0
        ]
        if not scored:
            return None

        best, best_score = max(scored, key=lambda t: t[1])
        if best_score < 0:
            return None
        return self._match_case(word, best.term)

    def _commit(self, suffix: str):
        if not self._buf:
            return
        raw = "".join(self._buf)
        self._buf.clear()
        fix = self._lookup(raw)
        if fix and fix != raw:
            print(f"  \u2713 {raw!r} \u2192 {fix!r}")
            # nuke the typed word + the delimiter that already landed, retype corrected
            _nuke_and_retype(len(raw) + 1, fix + suffix)

    def feed(self, vk, scan):
        if vk == VK_BACK:
            if self._buf:
                self._buf.pop()
            return

        if vk in (VK_SPACE, VK_RETURN, VK_TAB):
            suffix = {VK_RETURN: "\n", VK_TAB: "\t"}.get(vk, " ")
            self._commit(suffix)
            return

        ch = _vkey_to_char(vk, scan)
        if not ch:
            self._buf.clear()
            return

        if ch.isalpha() or ch == "'":
            self._buf.append(ch)
            return

        if ch in WORD_BREAKS:
            self._commit(ch)
            return

        self._buf.clear()


def _run(corrector: Corrector):
    # raw input arrives here — 64 bytes covers keyboard + header with room to spare
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
    if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
        raise RuntimeError(f"RegisterRawInputDevices failed ({ctypes.GetLastError()})")

    print("autocorrect active (raw input)  \u2014  press Ctrl+C to quit")

    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    base = Path(__file__).parent
    c = Corrector(base / "dict.txt", base / "personal.txt", base / "cache.pkl")
    try:
        _run(c)
    except KeyboardInterrupt:
        pass
