import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from matchups import face_offs  # noqa: E402

WEEKS = ["wk19", "wk20", "wk21"]
CFG = {"league": {"playoff_teams": 4}, "playoffs": {"weeks": [{"name": w} for w in WEEKS]}}


def team(*week_levels):
    """Week totals with the same level in each of 3 categories. A big gap between levels beats the noise."""
    return pd.DataFrame({cat: list(week_levels) for cat in ["pts", "reb", "ast"]}, index=WEEKS, dtype=float)


def run(totals, season_values):
    return face_offs(totals, np.array(season_values, dtype=float), np.random.default_rng(0), CFG)


def test_the_best_team_wins_every_face_off_and_the_title():
    totals = [team(1000, 1000, 1000)] + [team(10, 10, 10)] * 5
    assert run(totals, [6, 5, 4, 3, 2, 1]) == {"made_playoffs": True, "rr_win_pct": 100.0, "title": True}


def test_a_team_below_the_playoff_teams_does_not_play():
    totals = [team(1000, 1000, 1000)] + [team(10, 10, 10)] * 5
    result = run(totals, [1, 6, 5, 4, 3, 2])
    assert result["made_playoffs"] is False
    assert result["title"] is False
    assert math.isnan(result["rr_win_pct"])


def test_the_round_robin_counts_each_week_and_the_bracket_ends_in_the_last_week():
    # With 4 playoff teams, the semifinals are in wk20 and the final is in wk21.
    # You beat the others in wk19 and wk20, and you lose to them in wk21.
    totals = [team(1000, 1000, 10)] + [team(10, 10, 1000)] * 3
    result = run(totals, [4, 3, 2, 1])
    assert result["rr_win_pct"] == pytest.approx(200 / 3)
    assert result["title"] is False


def test_a_tie_goes_to_the_higher_seed():
    # All totals are 0, so each matchup is a tie: you win as the first seed, and you get half in the round robin
    totals = [team(0, 0, 0)] * 4
    assert run(totals, [4, 3, 2, 1]) == {"made_playoffs": True, "rr_win_pct": 50.0, "title": True}
    assert run(totals, [1, 4, 3, 2])["title"] is False
