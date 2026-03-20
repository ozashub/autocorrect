#!/usr/bin/env python3
import ctypes
import ctypes.wintypes as w
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

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LLKHF_INJECTED = 0x10
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 4
KEYEVENTF_KEYUP = 2
VK_BACK = 0x08
VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_CAPITAL = 0x14

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, w.WPARAM, w.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", w.DWORD), ("scanCode", w.DWORD),
        ("flags", w.DWORD), ("time", w.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD), ("wScan", w.WORD),
        ("dwFlags", w.DWORD), ("time", w.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    _fields_ = [("type", w.DWORD), ("u", _U)]


def _send(inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _backspaces(n):
    out = []
    for _ in range(n):
        d = INPUT(type=INPUT_KEYBOARD)
        d.u.ki.wVk = VK_BACK
        out.append(d)
        u = INPUT(type=INPUT_KEYBOARD)
        u.u.ki.wVk = VK_BACK
        u.u.ki.dwFlags = KEYEVENTF_KEYUP
        out.append(u)
    return out


def _typed(text):
    out = []
    for ch in text:
        c = ord(ch)
        d = INPUT(type=INPUT_KEYBOARD)
        d.u.ki.wScan = c
        d.u.ki.dwFlags = KEYEVENTF_UNICODE
        out.append(d)
        u = INPUT(type=INPUT_KEYBOARD)
        u.u.ki.wScan = c
        u.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        out.append(u)
    return out


def _vk_to_char(vk, scan):
    if 0x41 <= vk <= 0x5A:
        shifted = bool(user32.GetKeyState(VK_SHIFT) & 0x8000)
        caps = bool(user32.GetKeyState(VK_CAPITAL) & 1)
        return chr(vk) if (shifted ^ caps) else chr(vk + 32)
    state = (ctypes.c_ubyte * 256)()
    user32.GetKeyboardState(state)
    buf = (w.WCHAR * 4)()
    ret = user32.ToUnicode(vk, scan, state, buf, 4, 0)
    if ret >= 1:
        return buf[0]
    if ret == -1:
        user32.ToUnicode(vk, scan, state, buf, 4, 0)
    return None


GRAMMAR = {
    "aint": "ain't", "arent": "aren't", "cant": "can't", "cnat": "can't",
    "cmon": "c'mon", "coudlnt": "couldn't", "coulndt": "couldn't",
    "coudn": "couldn't", "coudln": "couldn't", "couldnt": "couldn't",
    "couldve": "could've", "didnt": "didn't", "didint": "didn't",
    "doesnt": "doesn't", "dosen": "doesn't", "doens": "doesn't",
    "dosn": "doesn't", "dont": "don't", "odnt": "don't",
    "hadnt": "hadn't", "hasnt": "hasn't", "havent": "haven't",
    "hed": "he'd", "heres": "here's", "hes": "he's",
    "howd": "how'd", "hows": "how's",
    "i": "I", "id": "I'd", "ill": "I'll", "im": "I'm",
    "isnt": "isn't", "itll": "it'll", "ive": "I've",
    "mightnt": "mightn't", "mightve": "might've", "mustnt": "mustn't",
    "oughtnt": "oughtn't", "shant": "shan't", "shes": "she's",
    "sholdnt": "shouldn't", "shoudlnt": "shouldn't",
    "shouldnt": "shouldn't", "shouldent": "shouldn't",
    "shouldve": "should've", "thats": "that's", "thtas": "that's",
    "thast": "that's", "theres": "there's", "theyd": "they'd",
    "theyll": "they'll", "theyre": "they're", "theyve": "they've",
    "tisn": "it's", "wasnt": "wasn't", "weere": "we're",
    "werent": "weren't", "weve": "we've", "whats": "what's",
    "whos": "who's", "whyd": "why'd", "wont": "won't",
    "woudlnt": "wouldn't", "wouldnt": "wouldn't", "wouldve": "would've",
    "yall": "y'all", "youd": "you'd", "youll": "you'll",
    "youre": "you're", "youve": "you've", "wed": "we'd",
}

WORD_BREAKS = set(";,.!?:")


class Corrector:
    def __init__(self, dict_path: Path, personal_path: Path, cache_path: Path):
        self._spell = SymSpell(max_dictionary_edit_distance=3, prefix_length=7)

        if cache_path.exists():
            self._spell.load_pickle(str(cache_path))
        else:
            if not dict_path.exists() or dict_path.stat().st_size == 0:
                raise RuntimeError(f"empty dictionary: {dict_path}")
            self._spell.load_dictionary(str(dict_path), 0, 1)
            self._spell.save_pickle(str(cache_path))

        if personal_path.exists():
            self._spell.load_dictionary(str(personal_path), 0, 1)

        self._buf: list[str] = []
        self._hook_id = None
        self._proc = HOOKPROC(self._on_key)

    def _match_case(self, src, tgt):
        if src.isupper():
            return tgt.upper()
        if src[0].isupper():
            return tgt[0].upper() + tgt[1:]
        return tgt

    def _lookup(self, word):
        low = word.lower()

        gram = GRAMMAR.get(low)
        if gram:
            return self._match_case(word, gram)

        if len(low) < 2:
            return None

        max_dist = 1 if len(low) <= 4 else 2 if len(low) <= 7 else 3
        hits = self._spell.lookup(low, Verbosity.ALL, max_edit_distance=max_dist)
        if not hits:
            return None

        exact = hits[0] if hits[0].distance == 0 else None
        if exact and exact.count >= 5000:
            return None

        # typos rarely get the first letter wrong
        candidates = [
            h for h in hits
            if h.distance > 0 and h.count >= 800 and h.term[0] == low[0]
        ]
        if not candidates:
            candidates = [
                h for h in hits
                if h.distance > 0 and h.count >= 5000
            ]
        if not candidates:
            return None

        best = min(candidates, key=lambda h: (h.distance, -h.count))

        if exact and best.count < exact.count * 10:
            return None

        return self._match_case(word, best.term)

    def _commit(self, suffix):
        if not self._buf:
            return False
        raw = "".join(self._buf)
        self._buf.clear()
        fix = self._lookup(raw)
        if not fix or fix == raw:
            return False
        _send(_backspaces(len(raw)) + _typed(fix + suffix))
        return True

    def _on_key(self, code, wparam, lparam):
        fwd = lambda: user32.CallNextHookEx(self._hook_id, code, wparam, lparam)

        if code != 0:
            return fwd()

        kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents

        if kb.flags & LLKHF_INJECTED:
            return fwd()

        if wparam != WM_KEYDOWN:
            if wparam == WM_SYSKEYDOWN:
                self._buf.clear()
            return fwd()

        if user32.GetKeyState(VK_CONTROL) & 0x8000 or user32.GetKeyState(VK_MENU) & 0x8000:
            self._buf.clear()
            return fwd()

        vk = kb.vkCode

        if vk == VK_BACK:
            if self._buf:
                self._buf.pop()
            return fwd()

        if vk in (VK_SPACE, VK_RETURN, VK_TAB):
            suffix = {VK_RETURN: "\n", VK_TAB: "\t"}.get(vk, " ")
            if self._commit(suffix):
                return 1
            return fwd()

        ch = _vk_to_char(vk, kb.scanCode)
        if not ch:
            self._buf.clear()
            return fwd()

        if ch.isalpha() or ch == "'":
            self._buf.append(ch)
            return fwd()

        if ch in WORD_BREAKS:
            if self._commit(ch):
                return 1
            return fwd()

        self._buf.clear()
        return fwd()

    def run(self):
        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc,
            kernel32.GetModuleHandleW(None), 0,
        )
        if not self._hook_id:
            raise RuntimeError("failed to install keyboard hook")

        print("autocorrect active")
        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnhookWindowsHookEx(self._hook_id)


if __name__ == "__main__":
    base = Path(__file__).parent
    Corrector(
        dict_path=base / "dict.txt",
        personal_path=base / "personal.txt",
        cache_path=base / "cache.pkl",
    ).run()
