"""Paths, config, playoff week names and name helpers that more than one script uses."""
import re
import tomllib
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"


def load_config():
    return tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))


def weeks(cfg):
    """Names of the playoff weeks, for example ["wk19", "wk20", "wk21"]. Each name is a column in rankings.csv."""
    return [w["name"] for w in cfg["playoffs"]["weeks"]]


def name_key(name):
    """Name for matching across sources: no accents, punctuation or suffixes (Jr., III)."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z ]", "", text.replace("-", " "))
    return " ".join(w for w in text.split() if w not in {"jr", "sr", "ii", "iii", "iv"})

