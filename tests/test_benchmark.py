import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from auction import _auctions, run_auction  # noqa: E402
from benchmark import run_benchmark  # noqa: E402


def config(teams=3, core=2, top=2, weights=None):
    return {"league": {"teams": teams, "slots": [], "adds": 0},
            "auction": {"budget": 100, "min_bid": 1, "spots": core + 1},
            "simulation": {"noise": 0.0, "core": core, "playoff_weight": 1.0, "fit_limits": [0.5, 1.5]},
            "weights": weights or {"pts": 1.0, "reb": 0.5},
            "category_balance": {"top_teams": top, "band": 0.5}}


def pool(*players):
    """Each player is (name, value, z_pts, z_reb)."""
    return pd.DataFrame(players, columns=["name", "value", "z_pts", "z_reb"])


def sales(*teams):
    """Each team is a list of player names. Team numbers follow the order."""
    return pd.DataFrame([(n, t, 1) for t, names in enumerate(teams) for n in names], columns=["name", "team", "price"])


PLAYERS = pool(("A", 9, 4, 2), ("B", 8, 2, 4), ("C", 7, 1, 1), ("D", 6, 3, 0), ("E", 5, 0, 2), ("F", 4, 1, 3),
               ("G", 3, 0, 0), ("H", 2, 1, 1), ("I", 1, 0, 1))


def test_benchmark_is_the_mean_wz_of_the_top_teams_cores():
    # The core is the best 2 players by value. Team 0: A+B = (6, 3). Team 1: C+D = (4, 0.5). Team 2: E+F = (1, 2.5).
    # Totals: 9, 4.5, 3.5. The top 2 teams are 0 and 1.
    result = run_benchmark(sales(["A", "B", "G"], ["C", "D", "H"], ["E", "F", "I"]), PLAYERS, config())
    assert result.to_dict() == pytest.approx({"pts": 5.0, "reb": 1.75})


def test_benchmark_counts_only_the_core_not_the_streamers():
    # Team 0 has A, B and the worst player I. I is not in the core, so it adds nothing.
    with_streamer = run_benchmark(sales(["A", "B", "I"], ["C", "D"], ["E", "F"]), PLAYERS, config(top=1))
    without = run_benchmark(sales(["A", "B"], ["C", "D"], ["E", "F"]), PLAYERS, config(top=1))
    assert with_streamer.to_dict() == pytest.approx(without.to_dict())
    assert without.to_dict() == pytest.approx({"pts": 6.0, "reb": 3.0})


def test_a_tie_in_the_total_keeps_the_team_number_order():
    # Team 0 is (3, 0) = 3 and team 1 is (0, 6) = 3 after the weights. One team can enter the top 1.
    players = pool(("X", 2, 3, 0), ("Y", 1, 0, 0), ("Z", 2, 0, 6), ("W", 1, 0, 0))
    result = run_benchmark(sales(["X", "Y"], ["Z", "W"], []), players, config(top=1))
    assert result.to_dict() == pytest.approx({"pts": 3.0, "reb": 0.0})
    # Both teams enter the top 2: the mean of the two profiles.
    both = run_benchmark(sales(["X", "Y"], ["Z", "W"], []), players, config(top=2))
    assert both.to_dict() == pytest.approx({"pts": 1.5, "reb": 1.5})


def test_a_team_with_fewer_players_than_the_core_uses_all_its_players():
    # Team 0 has only A: (4, 1) = 5 total. Team 1 has B, C: (3, 2.5). Team 2 has no players: zeros.
    result = run_benchmark(sales(["A"], ["B", "C"]), PLAYERS, config(top=3))
    assert result.to_dict() == pytest.approx({"pts": (4 + 3 + 0) / 3, "reb": (1 + 2.5 + 0) / 3})


def test_a_keeper_is_in_the_core_of_its_team():
    # Your keeper Z is the first sale of team 0 in run_auction. The keeper has the best value, so it is in the core.
    players = pool(("Z", 9, 5, 0), ("P1", 5, 1, 0), ("P2", 4, 1, 0), ("P3", 3, 1, 0), ("P4", 2, 1, 0),
                   ("P5", 1, 1, 0))
    cfg = config(teams=2, core=2, top=1)
    pricing = players.assign(pos="PG/SG/SF/PF/C", dollars=10.0, league_price=10.0, yahoo_cost=10.0)
    sold = run_auction(pricing, cfg, np.random.default_rng(0), keeper="Z")
    assert sold.name[0] == "Z"
    assert sold.team[0] == 0
    result = run_benchmark(sold, players, cfg)
    assert result["pts"] >= 5  # the best core holds Z


def test_simulate_adds_the_benchmark_of_each_run_when_the_pool_has_z_columns():
    cfg = config(teams=2, core=2, top=1)
    players = pool(("A", 9, 4, 2), ("B", 8, 2, 4), ("C", 7, 1, 1), ("D", 6, 3, 0), ("E", 5, 0, 2), ("F", 4, 1, 3))
    players = players.assign(pos="PG/SG/SF/PF/C", dollars=10.0, league_price=10.0, yahoo_cost=10.0)
    scores, _ = _auctions(players, cfg, None, 3, np.random.default_rng(0), None)
    assert {"bench_pts", "bench_reb"} <= set(scores.columns)
    assert len(scores) == 3
    plain, _ = _auctions(players[["name", "pos", "dollars", "league_price", "yahoo_cost"]], cfg, None, 1,
                         np.random.default_rng(0), None)
    assert not any(c.startswith("bench_") for c in plain.columns)
