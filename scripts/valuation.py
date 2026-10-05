"""Player value from per-game category stats and config.toml.

  1. Per-game z-score for each category, multiplied by its weight -> pg_value.
     The mean and the standard deviation come from the player pool (teams x roster_spots).
  2. pg_value minus replacement level -> pg_var (value above a waiver player).
  3. Final value: pg_var x (games / full_season) ^ power.
The first pool is the players with the most minutes. Each later pass uses the players with the most value.
"""
import numpy as np
import pandas as pd

PASSES = 5


def value_players(players, cfg):
    """Return a copy of players with pg_value, z_<cat>, pg_var and value added.

    players needs player_id, minutes, games and one per-game column for each category in cfg["weights"].
    """
    df = players.copy()
    pool_size = cfg["league"]["teams"] * cfg["league"]["roster_spots"]
    pool_ids = df.nlargest(pool_size, "minutes").player_id
    for n in range(PASSES):
        _score(df, cfg, pool_ids, rank_by="pg_value" if n == 0 else "value")
        pool_ids = df.nlargest(pool_size, "value").player_id
    return df


def _score(df, cfg, pool_ids, rank_by):
    """One pass. Changes df. rank_by="value" uses the value from the pass before to find the waiver tier."""
    weights = pd.Series(cfg["weights"])
    pool = df[df.player_id.isin(pool_ids)]
    z = (df[weights.index] - pool[weights.index].mean()) / pool[weights.index].std()
    df["pg_value"] = (z * weights).sum(axis=1)
    for cat in weights.index:
        df["z_" + cat] = z[cat]

    # Replacement level: average player in the first waiver tier
    pool_size = len(pool_ids)
    tier = df.sort_values(rank_by, ascending=False).iloc[pool_size : pool_size + cfg["league"]["teams"]]
    df["pg_var"] = df.pg_value - tier.pg_value.mean()

    g = cfg["games"]
    played = (df.games / g["full_season"]).clip(upper=1)
    value = df.pg_var * played ** g["power"]
    # Do not reward a player below replacement for missing games
    df["value"] = np.where(df.pg_var < 0, df.pg_var, value)
