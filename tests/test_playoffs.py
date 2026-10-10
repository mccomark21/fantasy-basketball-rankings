import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from playoffs import join_teams, playoff_schedule  # noqa: E402

# One playoff week. A day with 1 NBA game is a low-volume (quality) day. 4 teams, so a day can have 2 games.
CFG = {
    "playoffs": {"weeks": [{"name": "wk1", "start": "2027-03-01", "end": "2027-03-07"}],
                 "week_value": {"2": 0.5, "3": 1.0, "4": 1.4}},
    "quality_games": {"max_games_per_day": 1, "bonus": 0.1},
    "flags": {"avoid_week_games": 2},
}
GAMES = [
    ("2027-02-28", "A", "B"),  # before the playoffs: counts only in q_season
    ("2027-03-01", "A", "B"), ("2027-03-01", "C", "D"),  # 2 games: not a quality day
    ("2027-03-02", "A", "C"),
    ("2027-03-03", "A", "B"),
    ("2027-03-04", "B", "D"),
    ("2027-03-05", "A", "D"),
]


def schedule():
    """Two rows for each game, one for each team, as in data/schedule.csv."""
    rows = [(d, t, o) for d, h, a in GAMES for t, o in ((h, a), (a, h))]
    return pd.DataFrame(rows, columns=["date", "team", "opponent"]).assign(date=lambda s: pd.to_datetime(s.date))


@pytest.fixture
def result():
    return playoff_schedule(schedule(), CFG)


def test_games_and_quality_games_for_each_team(result):
    teams, _ = result
    assert teams.wk1.to_dict() == {"A": 4, "B": 3, "C": 2, "D": 3}
    assert teams.quality_games.to_dict() == {"A": 3, "B": 2, "C": 1, "D": 2}
    assert teams.q_season.to_dict() == {"A": 4, "B": 3, "C": 1, "D": 2}
    assert teams.games_wk["A"] == "4" and teams.quality_wk["A"] == "3"


def test_day_table_has_one_row_for_each_playoff_day(result):
    _, days = result
    assert days.date.dt.day.tolist() == [1, 2, 3, 4, 5]
    assert days.week.unique().tolist() == ["wk1"]
    assert days.nba_games.tolist() == [2, 1, 1, 1, 1]
    assert days.quality.tolist() == [False, True, True, True, True]
    assert sorted(days.teams[0]) == ["A", "B", "C", "D"]


def test_day_table_marks_the_second_night_of_a_back_to_back(result):
    # A plays on Feb 28, Mar 1, 2 and 3: the second nights are Mar 1 (the day before is not a playoff day), 2 and 3.
    # B plays Feb 28, Mar 1, 3 and 4. C plays Mar 1 and 2. D plays Mar 1, 4 and 5.
    _, days = result
    assert [sorted(b) for b in days.b2b] == [["A", "B"], ["A", "C"], ["A"], ["B"], ["D"]]


def test_short_week_is_at_or_below_avoid_week_games(result):
    teams, _ = result
    assert teams.short_weeks.to_dict() == {"A": "", "B": "", "C": "2-game wk1", "D": ""}


def test_schedule_score_is_relative_to_the_league_average(result):
    teams, _ = result
    # Week value without the quality bonus
    assert teams.week_score.to_dict() == pytest.approx({"A": 1.4, "B": 1.0, "C": 0.5, "D": 1.0})
    # With the bonus: A 1.7, B 1.2, C 0.6, D 1.2. League average 1.175.
    assert teams.sched_score.mean() == pytest.approx(1.0)
    assert teams.sched_score["A"] == pytest.approx(1.7 / 1.175)
    assert teams.sched_rank.to_dict() == {"A": 1, "B": 2, "C": 4, "D": 2}


def test_player_with_no_team_gets_an_empty_schedule(result):
    teams, _ = result
    players = pd.DataFrame({"name": ["a", "none"], "team": ["A", None]})
    out = join_teams(players, teams, CFG)
    assert out.loc[0, "wk1"] == 4 and out.loc[0, "sched_rank"] == 1
    none = out.loc[1]
    assert (none.wk1, none.quality_games, none.sched_rank, none.sched_score, none.week_score) == (0, 0, 0, 0, 0)
    assert (none.games_wk, none.short_weeks) == ("0", "")


def test_player_who_rests_on_back_to_backs_loses_the_second_nights(result):
    # A plays 4 games in wk1. 3 are second nights (Mar 1, 2 and 3), and 2 of them are quality days (Mar 2 and 3).
    teams, _ = result
    players = pd.DataFrame({"name": ["plays", "rests"], "team": ["A", "A"], "rests_b2b": [0, 1]})
    out = join_teams(players, teams, CFG).set_index("name")
    assert (out.at["plays", "wk1"], out.at["plays", "quality_games"]) == (4, 3)
    rests = out.loc["rests"]
    assert (rests.wk1, rests.playoff_games, rests.quality_games, rests.games_wk) == (1, 1, 1, "1")
    assert rests.short_weeks == "1-game wk1"
    assert rests.q_season == 4  # the full season does not change
    # 1 game is 1/3 of a 3-game week (linear). With the bonus: 1/3 + 0.1. League average of the teams: 1.175.
    assert rests.sched_score == pytest.approx((1 / 3 + 0.1) / 1.175)
    assert rests.sched_rank == 5  # below all 4 team schedules
