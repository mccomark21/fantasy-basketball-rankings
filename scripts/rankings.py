"""Build custom fantasy rankings from Projections.csv and config.toml.

valuation.py calculates the value of each player (z-scores, replacement level, games played).
The playoff schedule does not change the value. The schedule columns are for information only.
Output: rankings.csv
"""
import numpy as np
import pandas as pd

from common import DATA, OUT, ROOT, load_config, name_key, positions, q_cols, week_value, weeks
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

    rosters = pd.read_csv(DATA / "rosters.csv")
    teams = dict(zip(rosters.espn_name.map(name_key), rosters.team))
    df["team"] = df.name.map(name_key).map(teams)

    # espn_name: the player has a different name on ESPN (the team updates on each fetch)
    # team: set the team directly (for example, a free agent who signs)
    overrides = pd.read_csv(DATA / "team_overrides.csv", dtype=str).fillna("")
    for row in overrides.itertuples():
        team = row.team or teams.get(name_key(row.espn_name))
        df.loc[df.player_id == int(row.player_id), "team"] = team
    return df


def team_schedule(cfg):
    """Games and quality games for each team. Also writes playoff_schedule.csv."""
    sched = pd.read_csv(DATA / "schedule.csv", parse_dates=["date"])
    day_games = sched.groupby("date").size() // 2
    sched["quality"] = sched.date.map(day_games) <= cfg["quality_games"]["max_games_per_day"]

    counts = {"q_season": sched.groupby("team").quality.sum()}
    grid = {}
    for week in cfg["playoffs"]["weeks"]:
        name = week["name"]
        in_week = sched[(sched.date >= pd.Timestamp(week["start"])) & (sched.date <= pd.Timestamp(week["end"]))]
        counts[name] = in_week.groupby("team").size()
        counts["q_" + name] = in_week.groupby("team").quality.sum()
        for date, games in in_week.groupby("date"):
            label = f"{name} {date:%a %m-%d} ({day_games[date]})"
            grid[label] = pd.Series(np.where(games.quality, "Q", "x"), index=games.team)
    teams = pd.DataFrame(counts).fillna(0).astype(int)

    # Schedule score: average playoff week value, divided by the league average.
    # 1.00 = an average playoff schedule. The score is for information only. It does not change the value.
    week_names, bonus = weeks(cfg), cfg["quality_games"]["bonus"]
    week_scores = [teams[w].map(lambda g: week_value(g, cfg)) + bonus * teams[q] for w, q in zip(week_names, q_cols(cfg))]
    raw = sum(week_scores) / len(week_names)
    teams["sched_score"] = raw / raw.mean()
    teams["sched_rank"] = teams.sched_score.rank(ascending=False, method="min").astype(int)

    # Grid: one row for each team, one column for each playoff day.
    # Column name has the number of NBA games that day. Q = quality game, x = other game.
    out = pd.DataFrame(grid).fillna("")
    out["games"] = teams[week_names].sum(axis=1)
    out["quality"] = teams[q_cols(cfg)].sum(axis=1)
    out["sched_score"] = teams.sched_score.round(3)
    out["sched_rank"] = teams.sched_rank
    out.sort_values("sched_rank").to_csv(OUT / "playoff_schedule.csv", index_label="team")
    return teams


def main():
    cfg = load_config()
    OUT.mkdir(exist_ok=True)
    df = load_players(cfg)

    teams = team_schedule(cfg)
    df = df.join(teams, on="team")
    week_cols, quality_cols = weeks(cfg), q_cols(cfg)
    # A player with no team has no playoff games
    count_cols = [*week_cols, *quality_cols, "q_season", "sched_rank"]
    df[count_cols] = df[count_cols].fillna(0).astype(int)
    df["sched_score"] = df.sched_score.fillna(0)
    df["playoff_games"] = df[week_cols].sum(axis=1)
    df["quality_games"] = df[quality_cols].sum(axis=1)

    df = value_players(df, cfg)
    pool_size = cfg["league"]["teams"] * cfg["league"]["roster_spots"]
    df = df.sort_values("value", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    df["pg_rank"] = df.pg_value.rank(ascending=False).astype(int)
    df["pos"] = positions(df)
    cols = (["rank", "pg_rank", "name", "team", "pos", "games", "mpg", *STATS, *week_cols, "playoff_games",
             *quality_cols, "quality_games", "q_season", "sched_score", "sched_rank", "pg_value", "value"] + ["z_" + c for c in cfg["weights"]] + ["player_id"])
    df[cols].round(2).to_csv(OUT / "rankings.csv", index=False)

    missing = df[df.team.isna() & (df["rank"] <= pool_size + 50)]
    if len(missing):
        print("No team found (add to data/team_overrides.csv):")
        print(missing[["player_id", "name", "rank"]].to_string(index=False), "\n")
    print(df[["rank", "pg_rank", "name", "team", "pos", "games", *week_cols, "quality_games", "sched_score", "value"]].head(30).round(2).to_string(index=False))
    print(f"\nWrote {len(df)} players to rankings.csv")


if __name__ == "__main__":
    main()
