import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from sim_results import group_table, player_table  # noqa: E402


def runs(*auctions, keeper="K"):
    """Each auction is (title, core players, stream players). The keeper is in each core."""
    rows = []
    for run, (title, core, streams) in enumerate(auctions):
        for player, is_core in [(keeper, True), *[(p, True) for p in core], *[(p, False) for p in streams]]:
            rows.append({"keeper": keeper, "run": run, "player": player, "price": 10 * run + 1, "core": is_core,
                         "title": title})
    return pd.DataFrame(rows)


def test_player_table_compares_your_title_percent_with_and_without_each_core_player():
    data = runs((True, ["A"], ["S"]), (True, ["A", "B"], []), (False, ["B"], []), (True, [], ["A"]))
    table = player_table(data, min_pct=0).set_index("player")

    # A is in your core in runs 0 and 1 (2 titles). In runs 2 and 3, A is not in your core (1 title in 2).
    assert table.loc["A", ["core_pct", "title_with", "title_without", "lift"]].tolist() == pytest.approx([50, 100, 50, 50])
    # A costs $1 in run 0 and $11 in run 1
    assert table.loc["A", ["min_price", "median_price", "max_price"]].tolist() == pytest.approx([1, 6, 11])
    assert "K" not in table.index  # the keeper is in each core
    assert "S" not in table.index  # a stream player is not in the core
    assert table.keeper.unique().tolist() == ["K"]


def test_player_table_leaves_out_rare_players():
    data = runs(*[(True, ["A"], [])] * 19, (False, ["B"], []))
    assert player_table(data, min_pct=10).player.tolist() == ["A"]


def test_group_table_gives_the_title_percent_of_each_group_sorted_by_the_low_end():
    data = runs((True, ["A", "B", "C"], []), (True, ["A", "B"], []), (False, ["A", "C"], []), (False, ["B"], []))
    table = group_table(data, sizes=(2, 3), min_pct=0)

    assert table.group.tolist()[:2] == ["A + B", "A + B + C"]  # 100% in 2 runs is more sure than 100% in 1 run
    ac = table.set_index("group").loc["A + C"]
    # 1 title in 2 runs. With 1 more title and 1 more loss: p = 2/4. Standard error = sqrt(0.5 x 0.5 / 2) = 35.4.
    # Low end = 50 - 2 x 35.4.
    assert ac[["size", "runs", "title_pct", "low"]].tolist() == pytest.approx([2, 2, 50, 50 - 2 * 35.355], abs=0.01)


def test_group_table_leaves_out_rare_groups():
    data = runs(*[(True, ["A", "B"], [])] * 19, (False, ["C", "D"], []))
    assert group_table(data, sizes=(2,), min_pct=10).group.tolist() == ["A + B"]
