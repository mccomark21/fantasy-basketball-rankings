"""Paths, config, playoff-week and position helpers that more than one script uses."""
import re
import unicodedata
from pathlib import Path

import pandas as pd
import tomllib

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


def positions(df):
    """Yahoo positions for each player, for example "PG/SG". A player not in the Yahoo data gets "—".

    df needs the columns name and player_id.
    data/yahoo_names.csv gives the Yahoo name for a player whose name is different on Yahoo.
    """
    yahoo = pd.read_csv(DATA / "yahoo_players.csv", dtype=str)
    pos = dict(zip(yahoo.name.map(name_key), yahoo.positions.str.replace(",", "/")))
    fixes = pd.read_csv(DATA / "yahoo_names.csv", dtype=str)
    names = df.player_id.astype(str).map(dict(zip(fixes.player_id, fixes.yahoo_name))).fillna(df.name)
    return names.map(name_key).map(pos).fillna("—")
