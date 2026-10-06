"""Paths, config, playoff-week and name helpers that more than one script uses."""
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


def q_cols(cfg):
    """Quality-game column for each playoff week in rankings.csv."""
    return ["q_" + w for w in weeks(cfg)]


def week_value(games, cfg):
    """Value of one playoff week with this number of games. A game count not in the table is linear."""
    return cfg["playoffs"]["week_value"].get(str(games), games / 3)


def name_key(name):
    """Name for matching across sources: no accents, punctuation or suffixes (Jr., III)."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z ]", "", text.replace("-", " "))
    return " ".join(w for w in text.split() if w not in {"jr", "sr", "ii", "iii", "iv"})

