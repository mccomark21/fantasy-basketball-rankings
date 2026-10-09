"""Playoff schedule: games, quality games and schedule score for each NBA team in the fantasy playoffs.

The playoff-week rules are here: the week value table, quality (low-volume) days, short weeks and the score.
The settings are [playoffs], [quality_games] and avoid_week_games in [flags]. The callers write the files.
"""
import pandas as pd

from common import DATA, weeks

NO_TEAM = ""  # join key for a player with no team or a team that is not in the schedule


def read_schedule():
    """data/schedule.csv: one row for each team in each game."""
    return pd.read_csv(DATA / "schedule.csv", parse_dates=["date"])


def _q_cols(cfg):
    """Quality-game column for each playoff week, for example "q_wk19"."""
    return ["q_" + w for w in weeks(cfg)]


def _week_value(games, cfg):
    """Value of one playoff week with this number of games. A game count not in the table is linear."""
    return cfg["playoffs"]["week_value"].get(str(games), games / 3)


def schedule_columns(cfg):
    """Schedule columns in rankings.csv, in order."""
    return [*weeks(cfg), "playoff_games", *_q_cols(cfg), "quality_games", "q_season", "sched_score", "sched_rank"]


def _summarize(counts, cfg):
    """Add the totals, the week strings ("4-3-4"), week_score and short_weeks to a table of game counts."""
    week_names, q_names = weeks(cfg), _q_cols(cfg)
    out = counts.copy()
    out["playoff_games"] = out[week_names].sum(axis=1)
    out["quality_games"] = out[q_names].sum(axis=1)
    out["games_wk"] = out[week_names].astype(str).agg("-".join, axis=1)
    out["quality_wk"] = out[q_names].astype(str).agg("-".join, axis=1)
    out["finals_quality"] = out[q_names[-1]]
    # Average week value with no quality bonus (a 2-game week costs more than 1 game)
    out["week_score"] = out[week_names].apply(lambda col: col.map(lambda g: _week_value(g, cfg))).mean(axis=1)
    short = out[week_names].le(cfg["flags"]["avoid_week_games"])
    out["short_weeks"] = [", ".join(f"{out.at[i, w]}-game {w}" for w in week_names if row[w]) for i, row in short.iterrows()]
    return out


def playoff_schedule(sched, cfg):
    """(teams, days) from a schedule with one row for each team in each game (columns date and team).

    teams: one row for each team, with these columns:
    - games and quality games for each playoff week, and their totals playoff_games and quality_games
    - q_season: quality games in the full season
    - games_wk and quality_wk: the counts for each week, for example "4-3-4"
    - finals_quality: quality games in the last playoff week
    - week_score: average week value with no quality bonus
    - sched_score (1.00 = league average) and sched_rank
    - short_weeks: for example "2-game wk20", or "" if the team has no short week
    days: one row for each playoff day. date, week, nba_games, quality (a low-volume day), teams (a list) and
          b2b (the teams on the second night of a back-to-back, a list).
    """
    day_games = sched.groupby("date").size() // 2
    sched = sched.sort_values(["team", "date"])
    sched = sched.assign(quality=sched.date.map(day_games) <= cfg["quality_games"]["max_games_per_day"],
                         b2b=sched.groupby("team").date.diff().eq(pd.Timedelta(days=1)))

    counts, days = {"q_season": sched.groupby("team").quality.sum()}, []
    for week, q_name in zip(cfg["playoffs"]["weeks"], _q_cols(cfg)):
        name = week["name"]
        in_week = sched[(sched.date >= pd.Timestamp(week["start"])) & (sched.date <= pd.Timestamp(week["end"]))]
        counts[name] = in_week.groupby("team").size()
        counts[q_name] = in_week.groupby("team").quality.sum()
        days += [{"date": date, "week": name, "nba_games": day_games[date], "quality": games.quality.iloc[0],
                  "teams": games.team.tolist(), "b2b": games.team[games.b2b].tolist()}
                  for date, games in in_week.groupby("date")]
    teams = _summarize(pd.DataFrame(counts).fillna(0).astype(int), cfg)

    # Schedule score: average playoff week value with the quality bonus, divided by the league average.
    # 1.00 = an average playoff schedule. The score is for information only. It does not change the value.
    week_names, bonus = weeks(cfg), cfg["quality_games"]["bonus"]
    raw = teams.week_score + bonus * teams.quality_games / len(week_names)
    teams["sched_score"] = raw / raw.mean()
    teams["sched_rank"] = teams.sched_score.rank(ascending=False, method="min").astype(int)
    return teams, pd.DataFrame(days)


def join_teams(players, teams, cfg):
    """Add the team schedule to each player. A player with no team gets 0 games, score 0, rank 0 and no short weeks."""
    count_cols = ["q_season", *weeks(cfg), *_q_cols(cfg)]
    empty = _summarize(pd.DataFrame(0, index=[NO_TEAM], columns=count_cols), cfg)
    empty = empty.assign(sched_score=0.0, sched_rank=0, short_weeks="")
    key = players.team.where(players.team.isin(teams.index), NO_TEAM)
    return players.join(pd.concat([teams, empty]).loc[key].set_index(players.index))


def schedule_grid(teams, days):
    """One row for each team, one column for each playoff day, sorted by sched_rank (playoff_schedule.csv).

    The column name has the number of NBA games that day. Q = quality game, x = other game.
    """
    grid = {f"{d.week} {d.date:%a %m-%d} ({d.nba_games})": pd.Series("Q" if d.quality else "x", index=d.teams)
            for d in days.itertuples()}
    out = pd.DataFrame(grid).fillna("")
    out["games"] = teams.playoff_games
    out["quality"] = teams.quality_games
    out["sched_score"] = teams.sched_score.round(3)
    out["sched_rank"] = teams.sched_rank
    return out.sort_values("sched_rank")
