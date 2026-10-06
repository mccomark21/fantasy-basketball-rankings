import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import draft_board  # noqa: E402
from draft_board import filter_bar  # noqa: E402

DF = pd.DataFrame({
    "team": ["NYK", "BOS", "—", "BOS"],
    "pos": ["C", "SF/PF", "—", "PG/SG"],
})


def test_board_gets_every_column_from_build_rankings(monkeypatch):
    cfg = {"weights": {"pts": 1.0},
           "board": {"low_games": 60},
           "flags": {"good_playoff_games": 11, "poor_playoff_games": 9,
                     "good_quality_games": 3, "poor_quality_games": 1}}
    players = pd.DataFrame({
        "name": ["A", "B"], "team": ["BOS", None], "games": [70, 50], "pts": [20.0, 10.0],
        "playoff_games": [11, 0], "quality_games": [1, 0], "short_weeks": ["", ""],
        "dollars": [40.123456, 1.0],  # a new column that the board does not use yet
    })
    monkeypatch.setattr(draft_board, "build_rankings", lambda c: players.copy())

    df = draft_board.load(cfg)
    assert df.dollars.tolist() == [40.123456, 1.0]  # the board gets the new column, not rounded
    assert df.team.tolist() == ["BOS", "—"]
    assert df.player.tolist() == ["A", "B ⚠"]


def test_position_buttons_use_the_yahoo_order():
    html = filter_bar(DF)
    assert re.findall(r'data-pos="(\w+)"', html) == ["PG", "SG", "SF", "PF", "C"]


def test_team_options_are_sorted_with_no_team_last():
    html = filter_bar(DF)
    assert re.findall(r'<option value="([^"]*)"', html) == ["", "BOS", "NYK", "—"]


def test_flag_buttons_give_green_gray_yellow_for_s_and_q():
    html = filter_bar(DF)
    assert re.findall(r'data-flag="(\w)" data-grade="(\w+)"', html) == [
        ("s", "good"), ("s", "avg"), ("s", "warn"), ("q", "good"), ("q", "avg"), ("q", "warn")]


def test_row_gives_flags_to_the_filter_bar():
    def row(**kw):
        base = dict(team="BOS", pos="PG", no_team=False, two_game=False, s_flag="good", q_flag="warn")
        return pd.Series({**base, **kw})

    assert draft_board.row_open(row()) == '<tr data-team="BOS" data-pos="PG" data-s="good" data-q="warn">'
    # A player with an X or no team has no S or Q flags. An S or Q filter hides the player.
    assert 'data-s="" data-q=""' in draft_board.row_open(row(two_game=True))
    assert 'data-s="" data-q=""' in draft_board.row_open(row(no_team=True))
