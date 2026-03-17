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
        os.execv(
            sys.executable,
            [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:],
        )


_bootstrap()

import keyboard
import threading
from pathlib import Path
from symspellpy.symspellpy import SymSpell, Verbosity

_GRAMMAR = {
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
        self._buf: list[str] = []
        self._hooked = False

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
        if src.isupper():
            return tgt.upper()
        if src[0].isupper():
            return tgt[0].upper() + tgt[1:]
        return tgt

    def _lookup(self, word):
        low = word.lower()

        gram = _GRAMMAR.get(low)
        if gram:
            return self._transfer_case(word, gram)

        if len(word) < 2:
            return None

        max_dist = 1 if len(word) <= 4 else 2 if len(word) <= 7 else 3
        hits = self._spell.lookup(low, Verbosity.ALL, max_edit_distance=max_dist)
        if not hits:
            return None

        if hits[0].distance == 0:
            # legit word — freq 5000+ means the user probably meant it
            if hits[0].count >= 5000:
                return None
            # junk entry — check if there's something way better at distance 1
            real = [h for h in hits if h.distance == 1 and h.count >= 5000]
            if not real:
                return None
            return self._transfer_case(word, real[0].term)

        best = hits[0]
        if best.count < 1000:
            return None

        return self._transfer_case(word, best.term)

    def _inject(self, n_bs, text):
        keyboard.unhook(self)
        self._hooked = False

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
                keyboard.hook(self)
                self._hooked = True

        threading.Thread(target=go, daemon=True).start()

    def _commit(self, suffix):
        if not self._buf:
            return
        raw = "".join(self._buf)
        fix = self._lookup(raw)
        if fix and fix != raw:
            self._inject(len(raw) + 1, fix + suffix)
        self._buf.clear()

    def __call__(self, event):
        if event.event_type == "up":
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
