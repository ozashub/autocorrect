#!/usr/bin/env python3
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

if importlib.util.find_spec("symspellpy") is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "symspellpy"])
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

from autocorrect.corrector import Corrector
from autocorrect.listener import run

if __name__ == "__main__":
    data = Path(__file__).parent / "autocorrect" / "data"
    c = Corrector(data / "dict.txt", data / "personal.txt", data / "cache.pkl")
    try:
        run(c)
    except KeyboardInterrupt:
        pass
