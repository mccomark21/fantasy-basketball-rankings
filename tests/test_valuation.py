import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from valuation import value_players  # noqa: E402

# Pool = 2 teams x 5 roster spots = 10 players. The waiver tier is the next 2 players.
CFG = {
    "league": {"teams": 2, "roster_spots": 5},
    "weights": {"pts": 1.0, "reb": 0.5},
    "games": {"full_season": 82, "power": 1.25},
}


def players(n=30):
    """Player i has pts = reb = 30 - i, so the order by minutes, pg_value and value is the same."""
    i = pd.Series(range(n))
    return pd.DataFrame({
        "player_id": 100 + i,
        "minutes": 3000 - 10 * i,
        "games": 82,
        "pts": (30 - i).astype(float),
        "reb": (30 - i).astype(float),
    })


def test_z_scores_and_replacement_level_use_the_pool():
    out = value_players(players(), CFG)

    # The pool is pts 30..21: mean 25.5, sample std sqrt(55 / 6)
    sd = math.sqrt(55 / 6)
    assert out.z_pts[0] == pytest.approx(4.5 / sd)
    assert out.z_reb[29] == pytest.approx((1 - 25.5) / sd)
    assert out.pg_value[0] == pytest.approx(1.5 * 4.5 / sd)

    # The waiver tier is pts 20 and 19: mean 19.5
    replacement = 1.5 * (19.5 - 25.5) / sd
    assert (out.pg_value - out.pg_var).to_numpy() == pytest.approx([replacement] * len(out))
    assert out.value.to_numpy() == pytest.approx(out.pg_var.to_numpy())


def test_few_games_do_not_raise_a_player_below_replacement():
    full = players()
    few = players()
    few.loc[20, "games"] = 20

    full_out, few_out = value_players(full, CFG), value_players(few, CFG)
    assert full_out.pg_var[20] < 0
    assert few_out.value[20] <= full_out.value[20]
    assert (few_out.value > few_out.value[20]).sum() >= (full_out.value > full_out.value[20]).sum()


def test_power_zero_gives_value_equal_to_pg_var():
    df = players()
    df["games"] = [82, 40, 10] * 10
    cfg = {**CFG, "games": {"full_season": 82, "power": 0}}

    out = value_players(df, cfg)
    assert out.value.to_numpy() == pytest.approx(out.pg_var.to_numpy())


def test_input_frame_does_not_change():
    df = players()
    df.loc[3, "games"] = 50
    before = df.copy()

    out = value_players(df, CFG)
    pd.testing.assert_frame_equal(df, before)
    assert {"pg_value", "pg_var", "value", "z_pts", "z_reb"} <= set(out.columns)
    assert "value" not in df
