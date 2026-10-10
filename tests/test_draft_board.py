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
        "extra": [40.123456, 1.0],  # a new column that the board does not use yet
    })
    monkeypatch.setattr(draft_board, "build_rankings", lambda c: players.copy())

    df = draft_board.load(cfg)
    assert df.extra.tolist() == [40.123456, 1.0]  # the board gets the new column, not rounded
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


def test_league_price_and_diff_come_after_dollars_and_sort_a_missing_price_last():
    cfg = {"weights": {"pts": 1.0}, "board": {"low_games": 60},
           "flags": {"good_quality_games": 3, "poor_quality_games": 1}}
    cols = {h: fn for h, _, _, fn in draft_board.html_columns(cfg)}
    assert list(cols)[list(cols).index("$"):][:4] == ["$", "League $", "Diff", "Sched"]

    bargain = pd.Series({"league_price": 20.0, "surplus": 11.9})
    assert cols["League $"](bargain) == '<td data-v="20.00">$20</td>'
    assert cols["Diff"](bargain).endswith('>+12</td>') and "var(--good)" in cols["Diff"](bargain)
    unknown = pd.Series({"league_price": float("nan"), "surplus": float("nan")})
    assert cols["League $"](unknown) == cols["Diff"](unknown) == '<td data-v="-999">—</td>'


def test_group_panel_lists_the_top_groups_of_3_or_more_for_each_keeper():
    groups = pd.DataFrame([
        # keeper, group, size, runs, title_pct, se, low (sorted by low, as simulation_groups.csv is)
        ("Flagg", "A + B", 2, 300, 70.0, 2.0, 66.0),
        ("Flagg", "A + C + D + E", 4, 30, 80.0, 7.0, 66.0),
        ("Flagg", "A + B + C", 3, 70, 74.0, 5.0, 64.0),
        ("Buzelis", "B + C + D", 3, 50, 60.0, 6.0, 48.0),
    ], columns=["keeper", "group", "size", "runs", "title_pct", "se", "low"])
    html = draft_board.group_panel(groups, top=1)

    assert re.findall(r'<option value="([^"]*)"', html) == ["Flagg", "Buzelis"]  # the order of the file
    # Pairs are left out. The top group by low for each keeper.
    assert re.findall(r'data-players="([^"]*)"', html) == ["A|C|D|E", "B|C|D"]
    assert "80% ±7" in html and "30 auctions" in html


def test_risk_column_shows_the_tier_and_sorts_a_missing_tier_last():
    cfg = {"weights": {"pts": 1.0}, "board": {"low_games": 60},
           "flags": {"good_quality_games": 3, "poor_quality_games": 1}}
    cols = {h: fn for h, _, _, fn in draft_board.html_columns(cfg)}
    assert list(cols)[list(cols).index("Games"):][:2] == ["Games", "Risk"]
    assert cols["Risk"](pd.Series({"inj_risk": "low"})).endswith('>low</td>')
    assert "var(--good)" in cols["Risk"](pd.Series({"inj_risk": "low"}))
    assert 'data-v="3"' in cols["Risk"](pd.Series({"inj_risk": "extreme"}))
    assert "var(--bad)" in cols["Risk"](pd.Series({"inj_risk": "extreme"}))
    assert cols["Risk"](pd.Series({"inj_risk": float("nan")})) == '<td data-v="-1">—</td>'


def test_s_flag_note_says_when_the_player_rests_on_back_to_backs(monkeypatch):
    cfg = {"weights": {"pts": 1.0}, "board": {"low_games": 60},
           "flags": {"good_playoff_games": 11, "poor_playoff_games": 9,
                     "good_quality_games": 3, "poor_quality_games": 1}}
    players = pd.DataFrame({
        "name": ["A", "B"], "team": ["BOS", "BOS"], "games": [70, 70], "pts": [20.0, 10.0],
        "playoff_games": [11, 8], "quality_games": [1, 1], "short_weeks": ["", ""], "rests_b2b": [0, 1],
    })
    monkeypatch.setattr(draft_board, "build_rankings", lambda c: players.copy())
    assert draft_board.load(cfg).s_note.tolist() == ["11 playoff games", "8 playoff games (rests on back-to-backs)"]
