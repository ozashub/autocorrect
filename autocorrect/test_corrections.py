#!/usr/bin/env python3
import sys
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

FREQ_TRUSTED = 5000
FREQ_FLOOR = 500


def _is_subseq(small, big):
    it = iter(big)
    return all(c in it for c in small)


TESTS = [
    ("helo", "hello"),
    ("becuase", "because"),
    ("becasue", "because"),
    ("beacuse", "because"),
    ("teh", "the"),
    ("taht", "that"),
    ("wiht", "with"),
    ("waht", "what"),
    ("recieve", "receive"),
    ("acheive", "achieve"),
    ("occured", "occurred"),
    ("seperate", "separate"),
    ("definately", "definitely"),
    ("occassion", "occasion"),
    ("accomodate", "accommodate"),
    ("arguement", "argument"),
    ("beleive", "believe"),
    ("calender", "calendar"),
    ("collegue", "colleague"),
    ("concious", "conscious"),
    ("enviroment", "environment"),
    ("existance", "existence"),
    ("foriegn", "foreign"),
    ("goverment", "government"),
    ("guarentee", "guarantee"),
    ("happend", "happened"),
    ("immediatly", "immediately"),
    ("knowlege", "knowledge"),
    ("libary", "library"),
    ("mispell", "misspell"),
    ("neccessary", "necessary"),
    ("noticable", "noticeable"),
    ("occurence", "occurrence"),
    ("persue", "pursue"),
    ("posession", "possession"),
    ("prefered", "preferred"),
    ("publically", "publicly"),
    ("realy", "really"),
    ("refered", "referred"),
    ("relevent", "relevant"),
    ("remeber", "remember"),
    ("rythm", "rhythm"),
    ("succesful", "successful"),
    ("suprise", "surprise"),
    ("tommorow", "tomorrow"),
    ("untill", "until"),
    ("wierd", "weird"),
    ("writting", "writing"),
    ("dont", "don't"),
    ("cant", "can't"),
    ("im", "I'm"),
    ("youre", "you're"),
    ("theyre", "they're"),
    ("shouldnt", "shouldn't"),
    ("wouldnt", "wouldn't"),
    ("its", None),
    ("the", None),
    ("hello", None),
    ("world", None),
    ("python", None),
    ("computer", None),
]


def load_spell(base):
    spell = SymSpell(max_dictionary_edit_distance=3, prefix_length=7)
    cache = base / "cache.pkl"
    dictf = base / "dict.txt"
    personal = base / "personal.txt"

    if cache.exists():
        spell.load_pickle(str(cache))
    else:
        spell.load_dictionary(str(dictf), 0, 1)
        spell.save_pickle(str(cache))

    if personal.exists():
        spell.load_dictionary(str(personal), 0, 1)
    return spell


def transfer_case(src, tgt):
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


def score(typed, hit):
    if hit.term[0] != typed[0]:
        return -1
    dist_w = {1: 1.0, 2: 0.02, 3: 0.001}[hit.distance]
    len_diff = abs(len(hit.term) - len(typed))
    len_w = 1.0 / (1 + len_diff * 0.5)
    subseq_w = 3.0 if _is_subseq(typed, hit.term) else 1.0
    return hit.count * dist_w * len_w * subseq_w


def lookup(spell, word):
    low = word.lower()

    gram = _GRAMMAR.get(low)
    if gram:
        return gram

    if len(word) < 2:
        return None

    max_dist = 1 if len(word) <= 4 else 2 if len(word) <= 7 else 3
    hits = spell.lookup(low, Verbosity.ALL, max_edit_distance=max_dist)
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
        sc = score(low, h)
        if sc > best_score:
            best_score = sc
            best = h

    if not best:
        return None

    if exact_freq > 0 and best.count < exact_freq * 5:
        return None

    return transfer_case(word, best.term)


def dump_candidates(spell, word):
    low = word.lower()
    max_dist = 1 if len(word) <= 4 else 2 if len(word) <= 7 else 3
    hits = spell.lookup(low, Verbosity.ALL, max_edit_distance=max_dist)
    if not hits:
        print(f"    no candidates (max_dist={max_dist})")
        return
    for h in hits[:10]:
        tag = " <-- exact" if h.distance == 0 else ""
        freq_ok = "ok" if h.count >= FREQ_FLOOR else "LOW"
        sc = score(low, h) if h.distance > 0 else 0
        print(f"    {h.term:20s}  dist={h.distance}  freq={h.count:>10,}  [{freq_ok}]  score={sc:>14,.1f}{tag}")


def main():
    base = Path(__file__).parent
    spell = load_spell(base)
    print(f"Testing {len(TESTS)} words...\n")

    passed, failed = 0, 0
    failures = []

    for typo, expected in TESTS:
        got = lookup(spell, typo)
        if expected is None:
            ok = got is None
            display_expected = "(no correction)"
        else:
            ok = got == expected
            display_expected = expected

        if ok:
            passed += 1
            print(f"  PASS  {typo:20s} -> {got or '(none)':20s}")
        else:
            failed += 1
            print(f"  FAIL  {typo:20s} -> {(got or '(none)'):20s}  expected: {display_expected}")
            failures.append((typo, expected, got))

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TESTS)}")

    if failures:
        print(f"\nFailed words:")
        for typo, expected, got in failures:
            print(f"\n  '{typo}' -> got '{got}', expected '{expected}'")
            dump_candidates(spell, typo)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
