#!/usr/bin/env python3
import importlib.util
import os
import subprocess
import sys


def _bootstrap():
    missing = [pkg for pkg, mod in [("keyboard", "keyboard"), ("symspellpy", "symspellpy")]
               if importlib.util.find_spec(mod) is None]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        os.execv(sys.executable, [sys.executable] + sys.argv)


_bootstrap()

import keyboard
from pathlib import Path
from symspellpy.symspellpy import SymSpell, Verbosity


_FREQ_RATIO = 1000  # second suggestion wins only if it's way more common


class Corrector:
    def __init__(self, dict_path: Path, personal_path: Path, cache_path: Path):
        self._spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        self._buf: list[str] = []
        self._swapping = False

        if cache_path.exists():
            self._spell.load_pickle(str(cache_path))
        else:
            lines = sum(1 for _ in dict_path.open("rb"))
            if not lines:
                raise RuntimeError(f"empty dictionary: {dict_path}")
            self._spell.load_dictionary(str(dict_path), 0, 1)
            self._spell.save_pickle(str(cache_path))

        if personal_path.exists():
            self._spell.load_dictionary(str(personal_path), 0, 1)

    def _lookup(self, word: str) -> str | None:
        hits = self._spell.lookup(word, Verbosity.ALL, max_edit_distance=2)
        if not hits:
            return None
        if hits[0].distance > 0:
            return hits[0].term
        if len(hits) > 1 and hits[1].count / max(hits[0].count, 1) >= _FREQ_RATIO:
            return hits[1].term
        return None

    def _apply(self, corrected: str):
        # nuke the word mid-type and drop the fix in its place
        self._swapping = True
        keyboard.send("backspace")
        keyboard.send("ctrl+backspace")
        keyboard.write(corrected + " ")
        self._swapping = False

    def __call__(self, event):
        if self._swapping or event.event_type == "up":
            return
        k = event.name
        if len(k) == 1 and k.isalpha():
            self._buf.append(k)
        elif k in ("space", "enter", "tab"):
            if len(self._buf) > 1:
                fix = self._lookup("".join(self._buf))
                if fix:
                    self._apply(fix)
            self._buf.clear()
        elif k == "backspace" and self._buf:
            self._buf.pop()

    def run(self):
        keyboard.hook(self)
        keyboard.wait()


if __name__ == "__main__":
    base = Path(__file__).parent
    Corrector(
        dict_path=base / "dict.txt",
        personal_path=base / "personal.txt",
        cache_path=base / "cache.pkl",
    ).run()
