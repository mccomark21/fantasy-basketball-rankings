import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from auction import run_auction, simulate  # noqa: E402

ANY = "PG/SG/SF/PF/C"


def config(teams=2, spots=5, budget=100, noise=0.0, slots=()):
    return {"league": {"teams": teams, "slots": list(slots)}, "auction": {"budget": budget, "min_bid": 1, "spots": spots},
            "simulation": {"noise": noise}}


def pool(*players):
    """Each player is (name, pos, dollars, league_price, yahoo_cost)."""
    return pd.DataFrame(players, columns=["name", "pos", "dollars", "league_price", "yahoo_cost"])


def sold(sales, name):
    return sales.set_index("name").loc[name, ["team", "price"]].tolist()


def test_every_team_fills_its_roster_inside_its_budget():
    cfg = config(teams=4, spots=6, noise=0.3)
    players = pool(*[(f"P{i}", ANY, 60 - i, 70 - i, 50 - i) for i in range(40)])
    sales = run_auction(players, cfg, np.random.default_rng(0))

    assert sales.groupby("team").size().to_dict() == {0: 6, 1: 6, 2: 6, 3: 6}
    assert sales.groupby("team").price.sum().max() <= 100
    assert sales.price.min() >= 1
    assert sales.name.is_unique


def test_the_highest_bid_wins_and_pays_the_second_bid_plus_one():
    # Your bot bids up to dollars. The bot (team 1) bids up to league_price at the start.
    players = pool(("A", ANY, 30, 20, 20), ("B", ANY, 5, 18, 18))
    sales = run_auction(players, config(spots=1), np.random.default_rng(0))
    assert sold(sales, "A") == [0, 21]
    assert sold(sales, "B") == [1, 1]  # you have no spots left, so the bot pays min_bid


def test_your_bot_does_not_bid_more_than_your_dollars():
    players = pool(("A", ANY, 12, 40, 40), ("B", ANY, 1, 30, 30))
    sales = run_auction(players, config(spots=1), np.random.default_rng(0))
    assert sold(sales, "A") == [1, 13]


def test_a_bid_leaves_min_bid_for_each_other_empty_spot():
    # Budget 10 and 3 spots: the maximum bid is 10 - 1 x 2 = 8. Both teams bid 8, so the price is 8.
    players = pool(*[(f"P{i}", ANY, 50 - i, 50 - i, 50 - i) for i in range(6)])
    sales = run_auction(players, config(spots=3, budget=10), np.random.default_rng(0))
    assert sales.price.iloc[0] == 8


def test_bot_prices_move_from_league_price_to_yahoo_cost_as_the_room_cools():
    # 5 equal bots with 3 spots each. While 2 or more bots have empty spots, they tie, and the price is
    # their maximum bid. That is true for the first 12 sales. You bid only min_bid, so you buy last.
    players = pool(*[(f"P{i}", ANY, 0, 20, 4) for i in range(30)])
    prices = run_auction(players, config(teams=6, spots=3), np.random.default_rng(0)).price.tolist()[:12]
    assert prices[0] == 20
    assert all(a >= b for a, b in zip(prices, prices[1:]))
    assert prices[11] == 10  # 11 of 18 spots full: 20 - (20 - 4) x 11/18 = 10.2


def test_your_keeper_costs_league_price_and_takes_one_spot():
    players = pool(("Keeper", ANY, 30, 40.4, 10), ("A", ANY, 60, 50, 50), ("B", ANY, 60, 30, 30),
                   ("C", ANY, 1, 20, 20), ("D", ANY, 1, 10, 10))
    sales = run_auction(players, config(spots=2), np.random.default_rng(0), keeper="Keeper")
    # $100 - $40 = $60 for 1 spot: you win A at $51. The bot buys the rest.
    assert sales[sales.team == 0].values.tolist() == [["Keeper", 0, 40], ["A", 0, 51]]
    assert sales.groupby("team").size().to_dict() == {0: 2, 1: 2}


def test_a_team_buys_only_players_that_leave_room_for_pg_sg_sf_pf_and_c():
    # 5 spots and 5 position slots. The point guards cost the most, but each team can use only one.
    guards = [(f"PG{i}", "PG", 50, 50 - i, 40) for i in range(6)]
    others = [(f"{pos}{i}", pos, 2, 2, 2) for pos in ["SG", "SF", "PF", "C"] for i in range(2)]
    players = pool(*guards, *others, ("None", "–", 0, 0, 0))
    sales = run_auction(players, config(spots=5, slots=["PG", "SG", "SF", "PF", "C"]), np.random.default_rng(0))

    pos = sales.merge(players, on="name").groupby("team").pos.apply(sorted)
    assert pos.tolist() == [["C", "PF", "PG", "SF", "SG"]] * 2


def test_simulate_gives_your_team_score_and_the_players_you_win():
    # Each run is the same: you keep K ($10) and win A at $21 (the bot bids $20). The bot buys B.
    players = pool(("K", ANY, 15, 10, 10), ("A", ANY, 30, 20, 20), ("B", ANY, 5, 18, 18))
    scores, won = simulate(players, config(spots=2), "K", runs=5, rng=np.random.default_rng(0))

    assert scores.tolist() == [45] * 5  # dollars of K + A
    assert won.to_dict("index") == {"A": {"win_pct": 100.0, "price": 21.0}}


def test_win_pct_counts_the_runs_that_you_win_the_player():
    # You and the bot both bid $20 for A, so a coin flip gives A to one team.
    players = pool(("A", ANY, 20, 20, 20), ("B", ANY, 1, 5, 5))
    won = simulate(players, config(spots=1), None, runs=400, rng=np.random.default_rng(0))[1]
    assert 40 < won.win_pct["A"] < 60
    assert won.price["A"] == 20
