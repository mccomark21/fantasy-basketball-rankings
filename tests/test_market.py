import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from market import league_prices, price_curve  # noqa: E402

# 2 teams x 2 spots = 4 bought players, $10 budget = $20 in the league
CFG = {"league": {"teams": 2}, "auction": {"budget": 10, "min_bid": 1, "spots": 2}}


def drafts(*years):
    return pd.DataFrame([{"year": y, "cost": c} for y, costs in enumerate(years) for c in costs])


def test_curve_adds_up_to_the_league_money():
    curve = price_curve(drafts([8, 6, 4, 2]), CFG)
    assert curve.sum() == pytest.approx(20)
    assert list(curve) == pytest.approx([8, 6, 4, 2])


def test_curve_scales_a_draft_with_less_money():
    assert list(price_curve(drafts([4, 3, 2, 1]), CFG)) == pytest.approx([8, 6, 4, 2])


def test_bigger_draft_is_read_at_the_same_relative_place():
    # 8 players drafted: the place of rank 1 of 4 (1/8) is between the first two of 8 (1/16 and 3/16)
    curve = price_curve(drafts([9, 7, 5, 4, 3, 2, 1, 1]), CFG)
    assert curve[0] > curve[1] > curve[2] > curve[3]
    assert curve.sum() == pytest.approx(20)


def test_drafts_are_averaged():
    assert list(price_curve(drafts([10, 6, 3, 1], [6, 6, 5, 3]), CFG)) == pytest.approx([8, 6, 4, 2])


def test_min_bid_is_the_lowest_price():
    assert price_curve(drafts([17, 1, 1, 1]), CFG).min() == pytest.approx(1)


def test_prices_follow_the_yahoo_order():
    yahoo = pd.DataFrame({
        "yahoo_cost": [3.0, 7.0, None, 1.0, 1.0, 5.0],
        "yahoo_value": [None, 6, None, 1, 1, 2],
        "yahoo_rank": [4, 1, 3, 6, 5, 2],
    }, index=[10, 11, 12, 13, 14, 15])
    prices = league_prices(yahoo, drafts([8, 6, 4, 2]), CFG)

    assert prices.index.tolist() == yahoo.index.tolist()
    # 7 -> 8, 5 -> 6, 3 -> 4, then the tie at 1.0 goes to the better yahoo_rank (5)
    assert prices.to_dict() == {10: 4, 11: 8, 12: 0, 13: 0, 14: 2, 15: 6}


def test_a_projected_value_above_the_average_cost_moves_the_player_up():
    yahoo = pd.DataFrame({
        "yahoo_cost": [7.0, 3.5, 0.5, 2.0, 0.2],
        "yahoo_value": [6, 3, 5, 1, None],
        "yahoo_rank": [1, 2, 3, 4, 5],
    })
    # Order by the higher number: 7, 5 (cost only 0.5), 3.5, 2. The last player is not bought.
    assert league_prices(yahoo, drafts([8, 6, 4, 2]), CFG).tolist() == [8, 4, 6, 2, 0]


def test_a_bought_player_does_not_go_below_his_yahoo_number():
    yahoo = pd.DataFrame({
        "yahoo_cost": [30.0, 20.0, 1.0, 1.0, 1.0],
        "yahoo_value": [25, 15, 5, 3, 2],
        "yahoo_rank": [1, 2, 3, 4, 5],
    })
    # The curve gives 8, 6, 4, 2. Yahoo says 5 and 3 for the last two bought players.
    assert league_prices(yahoo, drafts([8, 6, 4, 2]), CFG).tolist() == [30, 20, 5, 3, 0]
