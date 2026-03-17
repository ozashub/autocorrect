#!/usr/bin/env python3
import importlib.util
import os
import subprocess
import sys


def _bootstrap():
    missing = [
        pkg
        for pkg, mod in [("keyboard", "keyboard"), ("symspellpy", "symspellpy")]
        if importlib.util.find_spec(mod) is None
    ]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:])
        sys.exit(0)


_bootstrap()

import keyboard
import math
import threading
import time
from collections import Counter
from pathlib import Path
from symspellpy.symspellpy import SymSpell, Verbosity

QWERTY = {
    "q": (0, 0), "w": (1, 0), "e": (2, 0), "r": (3, 0), "t": (4, 0),
    "y": (5, 0), "u": (6, 0), "i": (7, 0), "o": (8, 0), "p": (9, 0),
    "a": (0.25, 1), "s": (1.25, 1), "d": (2.25, 1), "f": (3.25, 1),
    "g": (4.25, 1), "h": (5.25, 1), "j": (6.25, 1), "k": (7.25, 1),
    "l": (8.25, 1),
    "z": (0.75, 2), "x": (1.75, 2), "c": (2.75, 2), "v": (3.75, 2),
    "b": (4.75, 2), "n": (5.75, 2), "m": (6.75, 2),
}

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


def keys_adjacent(a, b):
    pa, pb = QWERTY.get(a), QWERTY.get(b)
    if not pa or not pb:
        return False
    return math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < 1.8


def is_swap(typed, cand):
    if len(typed) != len(cand):
        return False
    diffs = [i for i in range(len(typed)) if typed[i] != cand[i]]
    return (
        len(diffs) == 2
        and diffs[1] == diffs[0] + 1
        and typed[diffs[0]] == cand[diffs[1]]
        and typed[diffs[1]] == cand[diffs[0]]
    )


def is_fat_finger(typed, cand):
    # every mismatched char is next to the right key on the keyboard
    if len(typed) != len(cand):
        return False
    for a, b in zip(typed, cand):
        if a != b and not keys_adjacent(a, b):
            return False
    return True


class Corrector:
    MIN_FREQ = 5000

    def __init__(self, dict_path: Path, personal_path: Path, cache_path: Path):
        self._spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        self._buf: list[str] = []
        self._skip = False
        self._last_fix = None
        self._hooked = False
        self._typed = Counter()
        self._rejections = Counter()
        self._suppressed: set[str] = set()
        self._learned: set[str] = set()
        self._personal = personal_path
        self._dirty = 0

        if cache_path.exists():
            self._spell.load_pickle(str(cache_path))
        else:
            if not dict_path.exists() or dict_path.stat().st_size == 0:
                raise RuntimeError(f"empty dictionary: {dict_path}")
            self._spell.load_dictionary(str(dict_path), 0, 1)
            self._spell.save_pickle(str(cache_path))

        if personal_path.exists():
            self._spell.load_dictionary(str(personal_path), 0, 1)
            for line in personal_path.read_text(encoding="utf-8").splitlines():
                tok = line.strip().split()
                if tok:
                    self._learned.add(tok[0].lower())

    def _transfer_case(self, src, tgt):
        if src.isupper():
            return tgt.upper()
        if src[0].isupper():
            return tgt[0].upper() + tgt[1:]
        return tgt

    def _known(self, word):
        hits = self._spell.lookup(word, Verbosity.CLOSEST, max_edit_distance=0)
        return hits and hits[0].count >= self.MIN_FREQ

    def _lookup(self, word):
        low = word.lower()

        gram = GRAMMAR.get(low)
        if gram:
            return self._transfer_case(word, gram)

        if len(word) < 3:
            return None
        if low in self._suppressed or low in self._learned:
            return None
        if self._known(low):
            return None

        max_dist = 1 if len(word) <= 5 else 2

        # ALL not CLOSEST — junk low-freq entries at distance 0 would hide real matches
        hits = self._spell.lookup(word, Verbosity.ALL, max_edit_distance=max_dist)
        if not hits:
            return None

        candidates = []
        for h in hits:
            if h.distance == 0:
                continue
            if h.count < self.MIN_FREQ:
                continue
            c = h.term.lower()
            if h.distance == 2 and low[0] != c[0]:
                continue
            if len(word) <= 4 and low[0] != c[0]:
                continue
            if h.distance == 2 and len(word) <= 6 and not is_swap(low, c):
                continue
            candidates.append(h)

        if not candidates:
            return None

        # swaps and fat-fingers float to the top, then sort by frequency
        def rank(h):
            c = h.term.lower()
            swap = is_swap(low, c)
            fat = is_fat_finger(low, c)
            return (swap, fat, h.count)

        candidates.sort(key=rank, reverse=True)
        return self._transfer_case(word, candidates[0].term)

    def _inject(self, n_backspace, text):
        keyboard.unhook(self)
        self._hooked = False

        def go():
            try:
                time.sleep(0.02)
                for _ in range(n_backspace):
                    keyboard.send("backspace")
                for ch in text:
                    try:
                        keyboard.write(ch)
                    except Exception:
                        pass
            finally:
                keyboard.hook(self)
                self._hooked = True

        threading.Thread(target=go, daemon=True).start()

    def _send_fix(self, original, corrected, trigger):
        suffix = {"enter": "\n", "tab": "\t"}.get(trigger, " ")
        self._inject(len(original) + 1, corrected + suffix)
        self._last_fix = (original, corrected, time.monotonic(), trigger)

    def _undo(self):
        if not self._last_fix:
            return False
        orig, corrected, ts, trigger = self._last_fix
        if time.monotonic() - ts > 3.0:
            self._last_fix = None
            return False

        self._last_fix = None
        suffix = {"enter": "\n", "tab": "\t"}.get(trigger, " ")
        self._inject(len(corrected), orig + suffix)

        key = f"{orig.lower()}->{corrected.lower()}"
        self._rejections[key] += 1
        if self._rejections[key] >= 2:
            self._suppressed.add(orig.lower())
        return True

    def _learn(self, word):
        low = word.lower()
        self._typed[low] += 1
        if self._typed[low] < 3 or low in self._learned:
            return
        self._learned.add(low)
        self._spell.create_dictionary_entry(low, self.MIN_FREQ + 1)
        self._dirty += 1
        if self._dirty >= 50:
            self._save_personal()

    def _save_personal(self):
        lines = [f"{w} 9999999" for w in sorted(self._learned)]
        self._personal.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._dirty = 0

    def __call__(self, event):
        if event.event_type == "up":
            return

        k = event.name

        if len(k) == 1 and (k.isalpha() or k == "'"):
            if self._last_fix:
                self._last_fix = None
            self._buf.append(k)
            return

        if len(k) == 1 and (k.isdigit() or k in "_-./\\@#$%"):
            self._skip = True
            self._buf.append(k)
            return

        if k in ("space", "enter", "tab"):
            if self._buf and not self._skip:
                raw = "".join(self._buf)
                fix = self._lookup(raw)
                if fix and fix != raw:
                    self._send_fix(raw, fix, k)
                else:
                    self._learn(raw)
            self._buf.clear()
            self._skip = False
            return

        if k == "backspace":
            if not self._buf and self._last_fix:
                self._undo()
                return
            if self._buf:
                self._buf.pop()
            return

        if len(k) == 1 and k in ".!?":
            self._buf.clear()
            self._skip = False
            return

        self._buf.clear()
        self._skip = False
        self._last_fix = None

    def run(self):
        keyboard.hook(self)
        self._hooked = True
        print("autocorrect active")
        keyboard.wait()


if __name__ == "__main__":
    base = Path(__file__).parent
    Corrector(
        dict_path=base / "dict.txt",
        personal_path=base / "personal.txt",
        cache_path=base / "cache.pkl",
    ).run()
