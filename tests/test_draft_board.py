import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

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


GROUPS = pd.DataFrame([
    # keeper, group, size, runs, title_pct, se, low (sorted by low, as simulation_groups.csv is)
    ("Flagg", "A + B", 2, 300, 70.0, 2.0, 66.0),
    ("Flagg", "A + C + D + E", 4, 30, 80.0, 7.0, 66.0),
    ("Flagg", "A + B + C", 3, 70, 74.0, 5.0, 64.0),
    ("Buzelis", "B + C + D", 3, 50, 60.0, 6.0, 48.0),
], columns=["keeper", "group", "size", "runs", "title_pct", "se", "low"])


def test_top_combos_keep_the_top_of_each_size_in_the_file_order():
    combos = draft_board.top_combos(GROUPS, top=1)
    assert list(zip(combos.keeper, combos.group)) == [
        ("Flagg", "A + B"), ("Flagg", "A + C + D + E"), ("Flagg", "A + B + C"), ("Buzelis", "B + C + D")]


def test_combo_stats_give_the_edge_and_the_median_price_of_runs_with_all_combo_players():
    runs = pd.DataFrame([
        # keeper, run, player, price, core
        ("Flagg", 0, "A", 10.0, True), ("Flagg", 0, "B", 5.0, True), ("Flagg", 0, "C", 3.0, True),
        ("Flagg", 1, "A", 20.0, True), ("Flagg", 1, "B", 7.0, True), ("Flagg", 1, "C", 1.0, True),
        ("Flagg", 2, "A", 30.0, True), ("Flagg", 2, "B", 9.0, False), ("Flagg", 2, "C", 1.0, True),  # B not core
        ("Flagg", 3, "A", 40.0, True), ("Flagg", 3, "C", 1.0, True),  # B not bought
    ], columns=["keeper", "run", "player", "price", "core"])
    summary = pd.DataFrame({"title_pct": [30.0]}, index=pd.Index(["Flagg"], name="keeper"))
    combos = pd.DataFrame({"keeper": ["Flagg", "Buzelis"], "group": ["A + B + C", "B + C + D"],
                           "title_pct": [74.0, 60.0]})
    out = draft_board.combo_stats(combos, runs, summary)
    assert out.price[0] == 23.0  # the median of 18 (run 0) and 28 (run 1)
    assert out.edge[0] == 44.0
    assert out.price.isna()[1] and out.edge.isna()[1]  # no runs and no summary for this keeper


CFG = {"playoffs": {"weeks": [{"name": "wk19"}, {"name": "wk20"}, {"name": "wk21"}]},
       "flags": {"good_playoff_games": 11, "poor_playoff_games": 9, "good_quality_games": 3,
                 "poor_quality_games": 1, "avoid_week_games": 2}}


def test_combo_cells_give_the_positions_prices_and_games_of_the_combo():
    df = pd.DataFrame({"name": ["A", "B"], "pos": ["PG/SG", "SG/SF"], "dollars": [30.4, 10.0],
                       "league_price": [25.0, float("nan")],
                       "wk19": [4, 2], "wk20": [4, 4], "wk21": [4, 3], "q_wk19": [1, 0], "q_wk20": [2, 1], "q_wk21": [1, 1]})
    pos, dollars, league, games, quality = draft_board.combo_cells(["A", "B", "Not in df"], df, CFG)
    assert re.findall(r'class="pill on">(\w+)<', pos) == ["PG", "SG", "SF"]
    assert dollars.endswith(">$40</td>")
    assert league.endswith(">$25</td>")  # a missing League $ adds nothing
    assert ">6-8-7 <b>21</b></td>" in games and 'data-v="21"' in games
    assert ">1-3-2 <b>6</b></td>" in quality
    # 10.5 playoff games and 3 quality games for each player: gray S, green Q
    assert 'class="g-avg"' in games and 'class="g-good"' in quality


PAGE_CFG = {**CFG, "weights": {"pts": 1.0}, "board": {"low_games": 60},
            "league": {"teams": 14, "slots": ["PG", "SG", "SF", "PF", "C"]}, "auction": {"budget": 200, "spots": 10}}
PAGE_DF = pd.DataFrame({"name": ["A", "B"], "pos": ["C", "PG/SG"], "team": ["DEN", "—"], "no_team": [False, True],
                        "player_id": [3930, 7], "rank": [1, 2], "value": [9.4612, 3.2], "rests_b2b": [0, 1],
                        "dollars": [10.0, 3.0], "league_price": [12.4, float("nan")],
                        "wk19": [4, 0], "wk20": [4, 0], "wk21": [4, 0], "q_wk19": [1, 0], "q_wk20": [1, 0], "q_wk21": [1, 0]})


def write_page(monkeypatch, tmp_path, sim=None, days=None):
    """The HTML page for PAGE_DF, with no board table and no filter bar."""
    monkeypatch.setattr(draft_board, "OUT", tmp_path)
    monkeypatch.setattr(draft_board, "html_table", lambda df, cfg: "")
    monkeypatch.setattr(draft_board, "filter_bar", lambda df: "")
    draft_board.write_html(PAGE_DF, PAGE_CFG, sim, days)
    return (tmp_path / "draft_board.html").read_text(encoding="utf-8")


def test_board_has_the_core_combos_tab_only_when_the_simulator_has_run(monkeypatch, tmp_path):
    html = write_page(monkeypatch, tmp_path)
    assert 'data-tab=' not in html and 'id="keeper"' not in html
    # The team table is on the board without the simulator files too
    assert 'id="roster"' in html
    df, cfg = PAGE_DF, PAGE_CFG

    combos = draft_board.top_combos(GROUPS).assign(base=30.0, edge=10.0, price=50.0)
    summary = pd.DataFrame({"cost": [56.0, 16.0], "title_pct": [30.0, 25.0], "playoffs_pct": [99.0, 98.0],
                            "rr_win_pct": [60.0, 58.0]}, index=pd.Index(["Flagg", "Buzelis"], name="keeper"))
    draft_board.write_html(df, cfg, (combos, summary))
    html = (tmp_path / "draft_board.html").read_text(encoding="utf-8")
    assert re.findall(r'data-tab="(\w+)"', html) == ["board", "combos"]
    assert re.findall(r'<option value="([^"]*)"', html) == ["Flagg", "Buzelis"]
    assert "Keeper cost $56" in html and ">+10</td>" in html and ">$50</td>" in html
    # The size filter shows the combos of 3 and 4 when the page opens
    assert re.findall(r'data-size="(\d)" aria-pressed="(\w+)"', html) == [("2", "false"), ("3", "true"), ("4", "true")]
    assert re.findall(r'<tr data-size="(\d)"( hidden)?>', html) == [("2", " hidden"), ("4", ""), ("3", ""), ("3", "")]
    assert "<details" in html and "Strong groups" not in html


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


def test_page_has_one_team_data_block_with_the_contract_keys(monkeypatch, tmp_path):
    days = pd.DataFrame({"date": pd.to_datetime(["2027-03-08"]), "week": ["wk19"], "nba_games": [5],
                         "quality": [True], "teams": [["BOS", "DEN"]], "b2b": [["DEN"]]})
    html = write_page(monkeypatch, tmp_path, days=days)
    blocks = re.findall(r'<script type="application/json" id="team-data">(.*?)</script>', html, re.S)
    assert len(blocks) == 1
    data = json.loads(blocks[0])
    assert list(data) == ["slots", "util", "budget", "spots", "core_max_rank", "weak_week_started", "weeks", "days",
                          "players"]
    assert (data["util"], data["budget"], data["spots"]) == (1, 200, 10)
    # No [team_builder] in the config: the defaults
    assert (data["core_max_rank"], data["weak_week_started"]) == (75, 0)
    assert data["days"] == [{"date": "2027-03-08", "week": "wk19", "nba_games": 5, "quality": True,
                             "teams": ["BOS", "DEN"], "b2b": ["DEN"]}]
    assert data["players"][0] == {"id": 3930, "name": "A", "team": "DEN", "pos": ["C"], "rank": 1, "value": 9.4612,
                                  "rests_b2b": 0, "league_price": 12}
    # A player with no team and no League $
    assert data["players"][1]["team"] is None and data["players"][1]["league_price"] is None


def test_team_data_reads_the_team_builder_config():
    cfg = {**PAGE_CFG, "team_builder": {"core_max_rank": 60, "weak_week_started": 20}}
    data = draft_board.team_data(PAGE_DF, None, cfg)
    assert (data["core_max_rank"], data["weak_week_started"], data["days"]) == (60, 20, [])


def test_positions_become_a_list_of_slots():
    slots = ["PG", "SG", "SF", "PF", "C"]
    assert draft_board.positions("PG/SG", slots) == ["PG", "SG"]
    assert draft_board.positions("—", slots) == []
    assert draft_board.team_data(PAGE_DF, None, PAGE_CFG)["players"][1]["pos"] == ["PG", "SG"]


def test_page_inlines_team_builder_js_when_the_file_is_there(monkeypatch, tmp_path):
    monkeypatch.setattr(draft_board, "ENGINE", tmp_path / "missing.js")
    html = write_page(monkeypatch, tmp_path)
    assert "Stub engine" in html and "__ENGINE__" not in html
    engine = tmp_path / "team_builder.js"
    engine.write_text("function scoreCore() {}  // the real engine", encoding="utf-8")
    monkeypatch.setattr(draft_board, "ENGINE", engine)
    html = write_page(monkeypatch, tmp_path)
    assert "// the real engine" in html and "Stub engine" not in html


def test_markdown_board_has_no_team_builder_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(draft_board, "OUT", tmp_path)
    cfg = {**PAGE_CFG, "board": {"low_games": 60, "tiers": [20]}}
    df = PAGE_DF.assign(player=PAGE_DF.name, two_game=False, s_flag="good", q_flag="avg", surplus=[-2.4, float("nan")],
                        sched_score=1.0, games_wk="4-4-4", quality_wk="1-1-1", games=70, inj_risk="low", stats="20.0")
    draft_board.write_markdown(df, cfg)
    md = (tmp_path / "draft_board.md").read_text(encoding="utf-8")
    assert ("| Rank | Player | Flags | Team | Pos | $ | League $ | Diff | Sched | Playoff games | Quality games "
            "| Games | Risk | Stats |") in md
    assert "Fit" not in md and "team-data" not in md


def test_each_board_row_has_an_add_button_and_a_taken_button():
    r = SimpleNamespace(player_id=7, name="Tyrese Maxey")
    cell = draft_board.add_cell(r)
    assert 'class="add" data-id="7"' in cell and 'class="take" data-id="7"' in cell
    assert 'aria-label="Mark Tyrese Maxey taken"' in cell


def test_filter_bar_has_fit_buttons_for_each_color_and_for_a_hole():
    bar = filter_bar(pd.DataFrame({"team": ["BOS"]}))
    assert re.findall(r'data-fit="(\w+)"', bar) == ["good", "warn", "bad", "hole"]
