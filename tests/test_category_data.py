import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from category_data import category_data, load_benchmark  # noqa: E402

CATS = ["pts", "reb", "ast", "threes", "stl", "blk"]
CFG = {"weights": {"pts": 1.0, "reb": 1.0, "ast": 1.0, "threes": 0.7, "blk": 0.65, "stl": 0.5},
       "simulation": {"core": 7}, "auction": {"min_bid": 1}, "category_balance": {"band": 0.5}}
BENCHMARK = {cat: 1.5 for cat in CATS}


def league(n=150):
    """n players. Rank 1 costs the most and has the best z-scores. z of rank r is (n - r) / 10."""
    ranks = range(1, n + 1)
    df = pd.DataFrame({"rank": ranks, "dollars": [max(1.0, 80 - 0.6 * r) for r in ranks]})
    for cat in CATS:
        df["z_" + cat] = [(n - r) / 10 for r in ranks]
    return df


def test_the_loader_returns_none_when_the_file_is_missing(tmp_path):
    assert load_benchmark(tmp_path / "missing.csv") is None


def test_the_loader_reads_the_one_row(tmp_path):
    path = tmp_path / "category_benchmark.csv"
    path.write_text("pts,reb,ast,threes,stl,blk\n1.23456,2,3,4,5,6\n")
    assert load_benchmark(path) == {"pts": 1.235, "reb": 2, "ast": 3, "threes": 4, "stl": 5, "blk": 6}


def test_without_a_benchmark_there_is_no_category_and_no_wz():
    assert category_data(league(), CFG, None) == (None, None)


def test_the_category_object_has_the_shape_of_the_contract():
    category, wz = category_data(league(), CFG, BENCHMARK)
    assert list(category) == ["cats", "benchmark", "core_size", "min_bid", "band", "filler_curve"]
    assert category["cats"] == CATS
    assert category["benchmark"] == BENCHMARK
    assert (category["core_size"], category["min_bid"], category["band"]) == (7, 1, 0.5)
    assert [e["price"] for e in category["filler_curve"]] == list(range(1, 61))
    assert all(list(e["wz"]) == CATS for e in category["filler_curve"])
    assert len(wz) == 150 and list(wz[0]) == CATS


def test_wz_is_z_times_the_weight():
    _, wz = category_data(league(), CFG, BENCHMARK)
    assert wz[0]["pts"] == pytest.approx(14.9)
    assert wz[0]["threes"] == pytest.approx(14.9 * 0.7)
    assert wz[0]["stl"] == pytest.approx(14.9 * 0.5)


def test_the_filler_curve_falls_from_a_high_price_to_a_low_price():
    curve = category_data(league(), CFG, BENCHMARK)[0]["filler_curve"]
    pts = [e["wz"]["pts"] for e in reversed(curve)]
    assert pts[0] > pts[-1]
    assert pts == sorted(pts, reverse=True)


def test_a_filler_is_the_mean_of_the_five_players_with_the_closest_dollars():
    df = league().assign(dollars=[float(r) for r in range(1, 151)])
    curve = category_data(df, CFG, BENCHMARK)[0]["filler_curve"]
    # Ranks 8 to 12 are the closest to 10 dollars.
    assert curve[9]["wz"]["pts"] == pytest.approx(sum((150 - r) / 10 for r in range(8, 13)) / 5, abs=1e-3)


def test_a_player_below_rank_140_is_not_a_filler():
    df = league(150)
    df.loc[df["rank"] == 145, ["dollars", "z_pts"]] = [30.0, 99.0]
    curve = category_data(df, CFG, BENCHMARK)[0]["filler_curve"]
    assert curve[29]["wz"]["pts"] < 20


def test_the_categories_of_the_benchmark_must_match_the_weights():
    with pytest.raises(ValueError):
        category_data(league(), CFG, {"pts": 1.0})
