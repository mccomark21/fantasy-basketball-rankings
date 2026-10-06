import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from auction import run_auction, simulate  # noqa: E402
from team_score import Playoffs  # noqa: E402

ANY = "PG/SG/SF/PF/C"


def config(teams=2, spots=5, budget=100, noise=0.0, slots=(), core=None):
    """core = spots by default: your bot has no stream spots."""
    return {"league": {"teams": teams, "slots": list(slots), "adds": 0},
            "auction": {"budget": budget, "min_bid": 1, "spots": spots},
            "simulation": {"noise": noise, "core": core or spots, "playoff_weight": 1.0, "fit_limits": [0.5, 1.5]}}


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

    assert scores.dollars.tolist() == [45] * 5  # dollars of K + A
    assert won.to_dict("index") == {"A": {"win_pct": 100.0, "price": 21.0}}


def test_win_pct_counts_the_runs_that_you_win_the_player():
    # You and the bot both bid $20 for A, so a coin flip gives A to one team.
    players = pool(("A", ANY, 20, 20, 20), ("B", ANY, 1, 5, 5))
    won = simulate(players, config(spots=1), None, runs=400, rng=np.random.default_rng(0))[1]
    assert 40 < won.win_pct["A"] < 60
    assert won.price["A"] == 20


def test_after_your_core_is_full_your_bot_bids_only_min_bid():
    players = pool(("A", ANY, 30, 20, 20), ("B", ANY, 30, 10, 10), ("C", ANY, 0, 5, 5), ("D", ANY, 0, 5, 5))
    sales = run_auction(players, config(spots=2, core=1), np.random.default_rng(0))
    assert sold(sales, "A") == [0, 21]
    assert sold(sales, "B") == [1, 2]


def test_your_bot_moves_the_money_of_the_stream_spots_to_the_core():
    # The bought players have $120 of dollars. The 2 cheapest ($40, 1 stream spot for each team) are $20 a team.
    # You pay $1 for your stream spot, so the core gets $99 for $80 of dollars: bids x 99/80.
    players = pool(("A", ANY, 40, 45, 45), ("B", ANY, 40, 30, 30), ("C", ANY, 20, 5, 5), ("D", ANY, 20, 5, 5))
    sales = run_auction(players, config(spots=2, core=1), np.random.default_rng(0))
    assert sold(sales, "A") == [0, 46]  # your bid: 40 x 99/80 = 49.5


def test_your_bot_bids_more_for_a_player_who_fits_your_playoff_schedule():
    # BOS plays on both playoff days, NY on none. An average bought player plays 2 games, so fit = 1 and 0.5.
    days = pd.DataFrame({"week": "wk1", "quality": False, "teams": [["BOS"], ["BOS"]]})
    cfg = config(spots=2)
    players = pool(("X", ANY, 20, 15, 15), ("Y", ANY, 20, 15, 15)).assign(team=["BOS", "NY"], prod=[5.0, 5.0])
    sales = run_auction(players, cfg, np.random.default_rng(0), playoffs=Playoffs(days, 0.0, 2, cfg))
    assert sold(sales, "X") == [0, 16]
    assert sold(sales, "Y") == [1, 11]  # your bid: 20 x 0.5 = 10


def test_simulate_gives_the_playoff_score_of_your_core():
    # Your core is K and A. Both play for BOS on the 2 playoff days, at C and Util.
    # B is your stream spot and does not count.
    days = pd.DataFrame({"week": "wk1", "quality": False, "teams": [["BOS"], ["BOS"]]})
    cfg = config(spots=3, core=2, slots=["C"])
    players = pool(("K", ANY, 15, 10, 10), ("A", ANY, 30, 20, 20), ("B", ANY, 0, 1, 1),
                   ("C", ANY, 5, 18, 18), ("D", ANY, 1, 9, 9), ("E", ANY, 1, 8, 8))
    players = players.assign(team="BOS", prod=[3.0, 5.0, 9.0, 1.0, 1.0, 1.0])
    scores = simulate(players, cfg, "K", runs=3, rng=np.random.default_rng(0), playoffs=Playoffs(days, 0.0, 2, cfg))[0]
    assert scores.playoff.tolist() == [16] * 3  # (3 + 5) x 2 days
