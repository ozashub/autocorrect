from pathlib import Path

from symspellpy import SymSpell, Verbosity

from .win32 import (
    VK_BACK, VK_RETURN, VK_SPACE, VK_TAB,
    nuke_and_retype, vkey_to_char,
)

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

        print(f"loaded: {len(self._spell.words)} words")

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

    def _try_correct(self, low: str) -> str | None:
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
        return best.term

    def _lookup(self, word: str) -> str | None:
        low = word.lower()

        gram = GRAMMAR.get(low)
        if gram:
            return self._match_case(word, gram)

        if len(low) < 3:
            return None
        if low in self._known:
            return None

        fix = self._try_correct(low)
        if fix:
            return self._match_case(word, fix)

        # key-mash salvage: user spazzed out mid-word, find the real word buried in the garbage
        if len(low) >= 7:
            for i in range(len(low) - 3, 3, -1):
                if low[:i] in self._known:
                    return self._match_case(word, low[:i])
        return None

    def _commit(self, suffix: str):
        if not self._buf:
            return
        raw = "".join(self._buf)
        self._buf.clear()
        fix = self._lookup(raw)
        if fix and fix != raw:
            print(f"  \u2713 {raw!r} \u2192 {fix!r}")
            nuke_and_retype(len(raw) + 1, fix + suffix)

    def feed(self, vk, scan):
        if vk == VK_BACK:
            if self._buf:
                self._buf.pop()
            return

        if vk in (VK_SPACE, VK_RETURN, VK_TAB):
            suffix = {VK_RETURN: "\n", VK_TAB: "\t"}.get(vk, " ")
            self._commit(suffix)
            return

        ch = vkey_to_char(vk, scan)
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
