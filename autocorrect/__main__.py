import importlib.util
import os
import subprocess
import sys
from pathlib import Path

if importlib.util.find_spec("symspellpy") is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "symspellpy"])
    os.execv(sys.executable, [sys.executable, "-m", "autocorrect"] + sys.argv[1:])

from .corrector import Corrector
from .listener import run

data = Path(__file__).parent / "data"
c = Corrector(data / "dict.txt", data / "personal.txt", data / "cache.pkl")
try:
    run(c)
except KeyboardInterrupt:
    pass
