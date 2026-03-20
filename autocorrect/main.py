#!/usr/bin/env python3
import importlib.util
import os
import subprocess
import sys
import threading
from pathlib import Path


def _bootstrap():
    missing = [
        pkg
        for pkg, mod in [("keyboard", "keyboard"), ("symspellpy", "symspellpy")]
        if importlib.util.find_spec(mod) is None
    ]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        os.execv(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:])


_bootstrap()

import keyboard
from symspellpy import SymSpell, Verbosity

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
        self._injecting = False

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

        # same length = substitution (hellp→hello), different length = insert/delete (hellp→help)
        best = min(candidates, key=lambda h: (h.distance, len(h.term) != len(low), -h.count))

        if exact and best.count < exact.count * 10:
            return None

        return self._match_case(word, best.term)

    def _inject(self, text):
        self._injecting = True

        def go():
            try:
                keyboard.send("ctrl+backspace")
                keyboard.write(text, delay=0)
            finally:
                self._buf.clear()
                self._injecting = False

        threading.Thread(target=go, daemon=True).start()

    def _commit(self, suffix):
        if not self._buf:
            return
        raw = "".join(self._buf)
        fix = self._lookup(raw)
        if fix and fix != raw:
            self._inject(fix + suffix)
        else:
            self._buf.clear()

    def __call__(self, event):
        if event.event_type == "up" or self._injecting:
            return

        k = event.name

        if len(k) == 1 and (k.isalpha() or k == "'"):
            self._buf.append(k)
            return

        if len(k) == 1 and k in WORD_BREAKS:
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
