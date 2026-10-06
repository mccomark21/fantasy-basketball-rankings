"""Link each projection player to its ESPN team and its Yahoo row.

Names match after name_key() (no accents, punctuation or suffixes).
data/name_overrides.csv gives the ESPN name, the Yahoo name or the team for a player that does not match.
"""
import pandas as pd

from common import name_key

# Columns from data/yahoo_players.csv. pos is the positions column with "/" in place of ",".
YAHOO_COLS = ["yahoo_id", "pos", "status", "yahoo_rank", "pct_drafted", "yahoo_cost", "yahoo_value", "adp"]


def link_players(players, rosters, yahoo, overrides):
    """ESPN team and Yahoo data for each player, with the same index as players.

    players needs the columns name and player_id.
    rosters is data/rosters.csv. yahoo is data/yahoo_players.csv.
    overrides is data/name_overrides.csv, read with dtype=str and fillna(""). A blank cell has no effect.
    A player with no ESPN match gets team NaN. A player with no Yahoo match gets yahoo_id NaN and pos "—".
    """
    fixes = overrides.set_index("player_id")
    ids = players.player_id.astype(str)

    def fixed(col):
        """Override value for each player. NaN when the cell is blank or the player has no row."""
        return ids.map(fixes[col][fixes[col] != ""])

    def keys(col):
        return fixed(col).fillna(players.name).map(name_key)

    teams = dict(zip(rosters.espn_name.map(name_key), rosters.team))
    out = pd.DataFrame({"team": fixed("team").fillna(keys("espn_name").map(teams))}, index=players.index)

    # If two Yahoo rows have the same key, the last row is used
    rows = yahoo.assign(pos=yahoo.positions.str.replace(",", "/"), key=yahoo.name.map(name_key))
    rows = rows.drop_duplicates("key", keep="last").set_index("key")[YAHOO_COLS]
    linked = rows.reindex(keys("yahoo_name"))
    linked.index = players.index
    linked["pos"] = linked.pos.fillna("—")
    return out.join(linked)
