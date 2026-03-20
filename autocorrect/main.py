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
import threading
from pathlib import Path
from symspellpy.symspellpy import SymSpell, Verbosity

_GRAMMAR = {
    "aint": "ain't", "arent": "aren't", "cant": "can't", "cnat": "can't",
    "cmon": "c'mon", "collegue": "colleague", "coudlnt": "couldn't", "coulndt": "couldn't",
    "coudn": "couldn't", "coudln": "couldn't", "couldnt": "couldn't",
    "couldve": "could've", "didnt": "didn't", "didint": "didn't",
    "doesnt": "doesn't", "dosen": "doesn't", "doens": "doesn't",
    "dosn": "doesn't", "dont": "don't", "odnt": "don't",
    "hadnt": "hadn't", "hasnt": "hasn't", "havent": "haven't",
    "hed": "he'd", "heres": "here's", "hes": "he's", "howd": "how'd",
    "hows": "how's", "i": "I", "id": "I'd", "ill": "I'll", "im": "I'm",
    "isnt": "isn't", "itll": "it'll", "ive": "I've", "mispell": "misspell",
    "mightnt": "mightn't", "mightve": "might've", "mustnt": "mustn't",
    "oughtnt": "oughtn't", "shant": "shan't", "shes": "she's",
    "sholdnt": "shouldn't", "shoudlnt": "shouldn't", "shouldnt": "shouldn't",
    "shouldent": "shouldn't", "shouldve": "should've", "thats": "that's",
    "thtas": "that's", "thast": "that's", "theres": "there's",
    "theyd": "they'd", "theyll": "they'll", "theyre": "they're",
    "theyve": "they've", "tisn": "it's", "wasnt": "wasn't",
    "weere": "we're", "werent": "weren't", "weve": "we've",
    "whats": "what's", "whos": "who's", "whyd": "why'd", "wont": "won't",
    "woudlnt": "wouldn't", "wouldnt": "wouldn't", "wouldve": "would've",
    "yall": "y'all", "youd": "you'd", "youll": "you'll",
    "youre": "you're", "youve": "you've", "wed": "we'd",
}

PUNCT = set(",.!?:;")
FREQ_TRUSTED = 5000  # above this, exact match is definitely a real word
FREQ_FLOOR = 500     # candidates below this are junk


def _is_subseq(small, big):
    it = iter(big)
    return all(c in it for c in small)


class Corrector:
    def __init__(self, dict_path: Path, personal_path: Path, cache_path: Path):
        self._spell = SymSpell(max_dictionary_edit_distance=3, prefix_length=7)
        self._buf: list[str] = []
        self._injecting = False

        if cache_path.exists():
            self._spell.load_pickle(str(cache_path))
        else:
            if not dict_path.exists() or dict_path.stat().st_size == 0:
                raise RuntimeError(f"empty dictionary: {dict_path}")
            self._spell.load_dictionary(str(dict_path), 0, 1)
            self._spell.save_pickle(str(cache_path))

        if personal_path.exists():
            self._spell.load_dictionary(str(personal_path), 0, 1)

    def _transfer_case(self, src, tgt):
        if src == src.lower():
            return tgt.lower()
        if src == src.upper():
            return tgt.upper()
        out = []
        for i, ch in enumerate(tgt):
            if i < len(src) and src[i].isupper():
                out.append(ch.upper())
            else:
                out.append(ch.lower())
        return "".join(out)

    def _score(self, typed, hit):
        # hard reject: first letter must match (iOS-style)
        if hit.term[0] != typed[0]:
            return -1

        # exponential distance penalty — dist 1 massively preferred over dist 2
        dist_w = {1: 1.0, 2: 0.02, 3: 0.001}[hit.distance]

        # mild length preference
        len_diff = abs(len(hit.term) - len(typed))
        len_w = 1.0 / (1 + len_diff * 0.5)

        # if typed letters appear in order in the candidate, it's likely
        # a dropped-letter typo (e.g. "helo" → "hello")
        subseq_w = 3.0 if _is_subseq(typed, hit.term) else 1.0

        return hit.count * dist_w * len_w * subseq_w

    def _lookup(self, word):
        low = word.lower()

        gram = _GRAMMAR.get(low)
        if gram:
            return gram

        if len(word) < 2:
            return None

        max_dist = 1 if len(word) <= 4 else 2 if len(word) <= 7 else 3
        hits = self._spell.lookup(low, Verbosity.ALL, max_edit_distance=max_dist)
        if not hits:
            return None

        if hits[0].distance == 0 and hits[0].count >= FREQ_TRUSTED:
            return None

        exact_freq = hits[0].count if hits[0].distance == 0 else 0

        pool = [h for h in hits if h.distance > 0 and h.count >= FREQ_FLOOR]
        if not pool:
            return None

        best, best_score = None, -1
        for h in pool:
            sc = self._score(low, h)
            if sc > best_score:
                best_score = sc
                best = h

        if not best:
            return None

        # if exact match exists, candidate must be overwhelmingly more common
        if exact_freq > 0 and best.count < exact_freq * 5:
            return None

        return self._transfer_case(word, best.term)

    def _inject(self, n_bs, text):
        self._injecting = True

        def go():
            try:
                for _ in range(n_bs):
                    keyboard.send("backspace")
                for ch in text:
                    try:
                        keyboard.write(ch)
                    except Exception:
                        pass
            finally:
                self._buf.clear()
                self._injecting = False

        threading.Thread(target=go, daemon=True).start()

    def _commit(self, suffix):
        if not self._buf:
            return
        raw = "".join(self._buf)
        clean = "".join(c for c in raw if c.isalpha() or c == "'")
        if not clean:
            self._buf.clear()
            return

        fix = self._lookup(clean)
        if fix and fix != clean:
            self._inject(len(raw) + 1, fix + suffix)
        elif clean != raw:
            self._inject(len(raw) + 1, clean + suffix)
        self._buf.clear()

    def __call__(self, event):
        if event.event_type == "up":
            return
        if self._injecting:
            return

        k = event.name

        if len(k) == 1 and (k.isalpha() or k == "'" or k == ";"):
            self._buf.append(k)
            return

        if len(k) == 1 and k in PUNCT:
            self._commit(k)
            return

        if k in ("space", "enter", "tab"):
            suffix = {"enter": "\n", "tab": "\t"}.get(k, " ")
            self._commit(suffix)
            return

        if k == "backspace":
            if self._buf:
                self._buf.pop()
            return

        self._buf.clear()

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
