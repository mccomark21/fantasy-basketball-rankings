"""Player value from per-game category stats and config.toml.

  1. Per-game z-score for each category, multiplied by its weight -> pg_value.
     The mean and the standard deviation come from the player pool (teams x roster_spots).
  2. pg_value minus replacement level -> pg_var (value above a waiver player).
  3. Final value: pg_var x (games / full_season) ^ power.
  4. Auction dollars: the teams buy the top teams x spots players by value. Each bought player gets min_bid.
     The rest of the money (teams x budget) goes to the bought players in proportion to value above
     replacement. Here, replacement is the first player who is not bought. That player and all players
     below get $0.
The first pool is the players with the most minutes. Each later pass uses the players with the most value.
"""
import numpy as np
import pandas as pd

PASSES = 5


def value_players(players, cfg):
    """Return a copy of players with pg_value, z_<cat>, pg_var, value and dollars added.

    players needs player_id, minutes, games and one per-game column for each category in cfg["weights"].
    """
    df = players.copy()
    pool_size = cfg["league"]["teams"] * cfg["league"]["roster_spots"]
    pool_ids = df.nlargest(pool_size, "minutes").player_id
    for n in range(PASSES):
        _score(df, cfg, pool_ids, rank_by="pg_value" if n == 0 else "value")
        pool_ids = df.nlargest(pool_size, "value").player_id
    df["dollars"] = _dollars(df.value, cfg)
    return df


def _dollars(value, cfg):
    """Auction dollars for each player. The dollars of the bought players add up to teams x budget."""
    teams, a = cfg["league"]["teams"], cfg["auction"]
    ranked = value.sort_values(ascending=False)
    n = teams * a["spots"]
    bought, replacement = ranked.index[:n], ranked.iloc[n]
    # The waiver tier in _score uses a different cutoff, so value can be below 0 for a bought player
    above = value[bought] - replacement
    spare = teams * a["budget"] - n * a["min_bid"]
    dollars = pd.Series(0.0, index=value.index)
    dollars[bought] = a["min_bid"] + spare * above / above.sum()
    return dollars


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
