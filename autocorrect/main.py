#!/usr/bin/env python3
import importlib.util
import os
import subprocess
import sys


def _bootstrap():
    missing = [
        pkg
        for pkg, mod in [
            ("keyboard", "keyboard"),
            ("symspellpy", "symspellpy"),
            ("jellyfish", "jellyfish"),
        ]
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
import jellyfish
from collections import Counter
from pathlib import Path
from symspellpy.symspellpy import SymSpell, Verbosity


QWERTY = {
    "q": (0, 0),
    "w": (1, 0),
    "e": (2, 0),
    "r": (3, 0),
    "t": (4, 0),
    "y": (5, 0),
    "u": (6, 0),
    "i": (7, 0),
    "o": (8, 0),
    "p": (9, 0),
    "a": (0.25, 1),
    "s": (1.25, 1),
    "d": (2.25, 1),
    "f": (3.25, 1),
    "g": (4.25, 1),
    "h": (5.25, 1),
    "j": (6.25, 1),
    "k": (7.25, 1),
    "l": (8.25, 1),
    "z": (0.75, 2),
    "x": (1.75, 2),
    "c": (2.75, 2),
    "v": (3.75, 2),
    "b": (4.75, 2),
    "n": (5.75, 2),
    "m": (6.75, 2),
}

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

PHONETIC_SWAPS = {
    "ph": "f",
    "f": "ph",
    "k": "c",
    "c": "k",
    "kn": "n",
    "wr": "r",
    "gn": "n",
    "gh": "g",
    "wh": "w",
    "ck": "k",
    "ght": "t",
    "tch": "ch",
}


class Corrector:
    def __init__(self, dict_path: Path, personal_path: Path, cache_path: Path):
        self._spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        self._buf: list[str] = []
        self._swapping = False
        self._skip = False
        self._prev_word = None
        self._last_fix = None
        self._typed = Counter()
        self._rejections = Counter()
        self._suppressed: set[str] = set()
        self._learned: set[str] = set()
        self._personal = personal_path
        self._dirty = 0
        self._after_punct = True
        self._max_freq = math.log1p(28787591)

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

    def _key_dist(self, a: str, b: str) -> float:
        pa, pb = QWERTY.get(a), QWERTY.get(b)
        if not pa or not pb:
            return 3.2
        return math.hypot(pa[0] - pb[0], pa[1] - pb[1])

    def _kbd_score(self, typed: str, cand: str) -> float:
        dists = []
        for i in range(min(len(typed), len(cand))):
            if typed[i] != cand[i]:
                dists.append(self._key_dist(typed[i], cand[i]))
        if not dists:
            return 1.0
        return max(0.0, 1.0 - (sum(dists) / len(dists)) / 3.2)

    def _pattern_bonus(self, typed: str, cand: str) -> float:
        if len(typed) == len(cand):
            diffs = [i for i in range(len(typed)) if typed[i] != cand[i]]
            if (
                len(diffs) == 2
                and diffs[1] == diffs[0] + 1
                and typed[diffs[0]] == cand[diffs[1]]
                and typed[diffs[1]] == cand[diffs[0]]
            ):
                return 0.15

        if len(typed) == len(cand) + 1:
            for i in range(len(typed) - 1):
                if typed[i] == typed[i + 1] and typed[:i] + typed[i + 1 :] == cand:
                    return 0.10

        if len(cand) == len(typed) + 1:
            for i in range(len(cand)):
                if cand[:i] + cand[i + 1 :] == typed:
                    return 0.10

        return 0.0

    def _score(self, typed: str, hit) -> float:
        t, c = typed.lower(), hit.term.lower()
        freq = math.log1p(hit.count) / self._max_freq
        dist = 1.0 - hit.distance * 0.25
        kbd = self._kbd_score(t, c)
        first = 1.0 if t[0] == c[0] else 0.5

        try:
            phon = 1.0 if jellyfish.metaphone(t) == jellyfish.metaphone(c) else 0.0
        except Exception:
            phon = 0.0

        base = (
            0.35 * freq
            + 0.30 * dist
            + 0.10 * kbd
            + 0.10 * first
            + 0.10 * phon
        )
        return base + self._pattern_bonus(t, c)

    def _phonetic_fallback(self, word: str) -> str | None:
        low = word.lower()
        for old, new in PHONETIC_SWAPS.items():
            if old not in low:
                continue
            alt = low.replace(old, new, 1)
            hits = self._spell.lookup(alt, Verbosity.CLOSEST, max_edit_distance=1)
            if hits and hits[0].distance <= 1 and hits[0].count >= 5000:
                return self._transfer_case(word, hits[0].term)
        return None

    def _transfer_case(self, src: str, tgt: str) -> str:
        if src.isupper():
            return tgt.upper()
        if src[0].isupper():
            return tgt[0].upper() + tgt[1:]
        return tgt

    def _lookup(self, word: str) -> str | None:
        low = word.lower()

        gram = GRAMMAR.get(low)
        if gram:
            return self._transfer_case(word, gram)

        if len(word) < 2:
            return None
        if low in self._suppressed or low in self._learned:
            return None

        hits = self._spell.lookup(word, Verbosity.ALL, max_edit_distance=2)

        if hits and hits[0].distance == 0 and hits[0].count >= 5000:
            return None

        phon_hit = self._phonetic_fallback(word)

        candidates = [(self._score(word, h), h) for h in hits if h.distance > 0]

        if phon_hit:
            candidates = [
                (sc + 0.22 if h.term == phon_hit else sc, h)
                for sc, h in candidates
            ]
            found = any(h.term == phon_hit for _, h in candidates)
            if not found:
                phon_hits = self._spell.lookup(
                    phon_hit, Verbosity.CLOSEST, max_edit_distance=0
                )
                for ph in phon_hits:
                    candidates.append((self._score(word, ph) + 0.22, ph))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_sc, best = candidates[0]

        thresh = 0.70 if len(word) <= 3 else 0.60
        if best_sc < thresh:
            return None

        return self._transfer_case(word, best.term)

    def _type_text(self, text: str):
        for ch in text:
            try:
                keyboard.write(ch)
            except Exception:
                pass

    def _send_fix(self, original: str, corrected: str, trigger: str):
        self._swapping = True

        def _do():
            try:
                time.sleep(0.02)
                for _ in range(len(original) + 1):
                    keyboard.send("backspace")
                suffix = {"enter": "\n", "tab": "\t"}.get(trigger, " ")
                self._type_text(corrected + suffix)
                self._last_fix = (original, corrected, time.monotonic(), trigger)
            finally:
                time.sleep(0.05)
                self._swapping = False

        threading.Thread(target=_do, daemon=True).start()

    def _undo(self) -> bool:
        if not self._last_fix:
            return False
        orig, corrected, ts, _ = self._last_fix
        if time.monotonic() - ts > 3.0:
            self._last_fix = None
            return False

        self._swapping = True
        self._last_fix = None

        def _do():
            try:
                time.sleep(0.02)
                for _ in range(len(corrected)):
                    keyboard.send("backspace")
                self._type_text(orig)
            finally:
                time.sleep(0.05)
                self._swapping = False

        threading.Thread(target=_do, daemon=True).start()

        key = f"{orig.lower()}->{corrected.lower()}"
        self._rejections[key] += 1
        if self._rejections[key] >= 2:
            self._suppressed.add(orig.lower())

        return True

    def _learn(self, word: str):
        low = word.lower()
        self._typed[low] += 1
        if self._typed[low] < 3 or low in self._learned:
            return
        self._learned.add(low)
        self._spell.create_dictionary_entry(low, 5001)
        self._dirty += 1
        if self._dirty >= 50:
            self._save_personal()

    def _save_personal(self):
        lines = [f"{w} 9999999" for w in sorted(self._learned)]
        self._personal.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._dirty = 0

    def __call__(self, event):
        if self._swapping or event.event_type == "up":
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
                    if self._after_punct and raw[0].islower() and len(raw) > 1:
                        cap = raw[0].upper() + raw[1:]
                        hits = self._spell.lookup(
                            cap, Verbosity.CLOSEST, max_edit_distance=0
                        )
                        if not hits:
                            self._send_fix(raw, cap, k)
                self._prev_word = (fix or raw).lower()
            self._buf.clear()
            self._skip = False
            self._after_punct = k == "enter"
            return

        if k == "backspace":
            if not self._buf and self._last_fix:
                self._undo()
                return
            if self._buf:
                self._buf.pop()
            return

        if len(k) == 1 and k in ".!?":
            self._after_punct = True
            if self._buf:
                self._prev_word = "".join(self._buf).lower()
            self._buf.clear()
            self._skip = False
            return

        self._buf.clear()
        self._skip = False
        self._last_fix = None

    def run(self):
        keyboard.hook(self)
        print("autocorrect active")
        keyboard.wait()


if __name__ == "__main__":
    base = Path(__file__).parent
    Corrector(
        dict_path=base / "dict.txt",
        personal_path=base / "personal.txt",
        cache_path=base / "cache.pkl",
    ).run()
