"""Build custom fantasy rankings from Projections.csv and config.toml.

valuation.py calculates the value of each player (z-scores, replacement level, games played).
The playoff schedule does not change the value. The schedule columns are for information only.
Output: rankings.csv
"""
import pandas as pd

from common import DATA, OUT, ROOT, load_config, weeks
from identity import link_players
from playoffs import join_teams, playoff_schedule, read_schedule, schedule_columns, schedule_grid
from valuation import value_players

# Category name in config.toml -> column calculated from the projections
STATS = {
    "pts": lambda d: 2 * d.field_goals + d.threes + d.free_throws,
    "reb": lambda d: d.offensive_rebounds + d.defensive_rebounds,
    "ast": lambda d: d.assists,
    "threes": lambda d: d.threes,
    "stl": lambda d: d.steals,
    "blk": lambda d: d.blocks,
}


def load_players(cfg):
    df = pd.read_csv(ROOT / cfg["league"]["projections"])
    df = df[df.games > 0].copy()
    df["name"] = df.first_name + " " + df.last_name
    for cat, calc in STATS.items():
        df[cat] = calc(df) / df.games
    df["mpg"] = df.minutes / df.games

    links = link_players(df, pd.read_csv(DATA / "rosters.csv"), pd.read_csv(DATA / "yahoo_players.csv"),
                         pd.read_csv(DATA / "name_overrides.csv", dtype=str).fillna(""))
    return df.join(links)


def main():
    cfg = load_config()
    OUT.mkdir(exist_ok=True)
    df = load_players(cfg)

    teams, days = playoff_schedule(read_schedule(), cfg)
    schedule_grid(teams, days).to_csv(OUT / "playoff_schedule.csv", index_label="team")
    df = join_teams(df, teams, cfg)

    df = value_players(df, cfg)
    pool_size = cfg["league"]["teams"] * cfg["league"]["roster_spots"]
    df = df.sort_values("value", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    df["pg_rank"] = df.pg_value.rank(ascending=False).astype(int)
    cols = (["rank", "pg_rank", "name", "team", "pos", "games", "mpg", *STATS, *schedule_columns(cfg),
             "pg_value", "value"] + ["z_" + c for c in cfg["weights"]] + ["player_id"])
    df[cols].round(2).to_csv(OUT / "rankings.csv", index=False)

    top = df[df["rank"] <= pool_size + 50]
    for col, message in [("team", "No team found (add espn_name or team to data/name_overrides.csv):"),
                         ("yahoo_id", "No Yahoo data found (add yahoo_name to data/name_overrides.csv):")]:
        missing = top[top[col].isna()]
        if len(missing):
            print(message)
            print(missing[["player_id", "name", "rank"]].to_string(index=False), "\n")
    print(df[["rank", "pg_rank", "name", "team", "pos", "games", *weeks(cfg), "quality_games", "sched_score", "value"]].head(30).round(2).to_string(index=False))
    print(f"\nWrote {len(df)} players to rankings.csv")


if __name__ == "__main__":
    main()
