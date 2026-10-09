import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from team_score import Playoffs  # noqa: E402

CFG = {"league": {"slots": ["PG", "SG", "SF", "PF", "C"]}, "auction": {"spots": 10}, "weights": {"pts": 1, "reb": 1},
       "simulation": {"fit_limits": [0.5, 1.5]},
       "risk": {"missed_week": {"low": 0.0, "med": 0.2, "high": 1.0}, "missing_tier": "low", "rest_chance": 1.0}}


def days(*teams_by_day, week="wk1", quality=False, b2b=None):
    """One row for each day. Each argument is the list of NBA teams that play that day.

    b2b: for each day, the teams on the second night of a back-to-back. None = no column.
    """
    out = pd.DataFrame({"week": week, "quality": quality, "teams": list(teams_by_day)})
    return out if b2b is None else out.assign(b2b=list(b2b))


def player(team, prod, pos="PG", stats=(0, 0), **more):
    """stats: per-game pts and reb. more: inj_risk, rests_b2b."""
    return {"team": team, "prod": prod, "pos": pos, "stats": list(stats), **more}


def playoffs(schedule, streamer=0.0, adds=0, streams=0, streamer_stats=(0, 0)):
    """streams = stream spots (auction spots - core). adds = adds each week."""
    cfg = {**CFG, "league": {**CFG["league"], "adds": adds}, "simulation": {**CFG["simulation"], "core": 10 - streams}}
    return Playoffs(schedule, streamer, cfg, list(streamer_stats))


def test_each_game_that_a_player_starts_adds_his_production():
    schedule = days(["BOS", "NY"], ["BOS"], ["LAL"], ["BOS"])
    assert playoffs(schedule).score([player("BOS", 10), player("LAL", 4)]) == pytest.approx(34)


def test_only_the_best_legal_lineup_starts():
    # PG, SG, SF, PF, C and Util: 3 centers on one day give C + Util. The weakest center sits.
    centers = [player("BOS", 9, "C"), player("BOS", 7, "PF/C"), player("BOS", 5, "C")]
    assert playoffs(days(["BOS"])).score(centers) == pytest.approx(9 + 7 + 5)  # PF/C takes the PF slot
    centers[1]["pos"] = "C"
    assert playoffs(days(["BOS"])).score(centers) == pytest.approx(9 + 7)


def test_streamers_fill_empty_slots_on_a_busy_day():
    # 6 empty slots, 3 stream spots: 3 streamer games. With 2 adds, only 2.
    assert playoffs(days(["BOS"]), streamer=2, adds=5, streams=3).score([]) == pytest.approx(3 * 2)
    assert playoffs(days(["BOS"]), streamer=2, adds=2, streams=3).score([]) == pytest.approx(2 * 2)


def test_streamers_fill_only_the_empty_slots():
    full = [player("BOS", 1, pos) for pos in ["PG", "SG", "SF", "PF", "C", "C"]]
    assert playoffs(days(["BOS"]), streamer=2, adds=5, streams=3).score(full) == pytest.approx(6)


def test_a_streamer_stays_until_the_end_of_the_week():
    # 1 add: the streamer from day 1 plays all 3 days
    assert playoffs(days(["NY"], ["NY"], ["NY"]), streamer=1, adds=1, streams=1).score([]) == pytest.approx(3)


def test_a_streamer_comes_from_the_team_with_the_most_games_left():
    # NY plays on day 1 only. BOS plays on days 1 and 2.
    assert playoffs(days(["NY", "BOS"], ["BOS"]), streamer=1, adds=1, streams=1).score([]) == pytest.approx(2)


def test_a_new_add_replaces_a_streamer_who_does_not_play_today():
    assert playoffs(days(["NY"], ["BOS"]), streamer=1, adds=2, streams=1).score([]) == pytest.approx(2)


def test_no_adds_on_quality_days():
    quality = days(["NY"], quality=True)
    assert playoffs(quality, streamer=1, adds=5, streams=3).score([]) == pytest.approx(0)
    # A streamer that you added on a busy day plays on a quality day
    week = pd.concat([days(["NY"]), quality])
    assert playoffs(week, streamer=1, adds=1, streams=1).score([]) == pytest.approx(2)


def test_the_adds_are_for_each_week():
    schedule = pd.concat([days(["BOS"], week="wk1"), days(["NY"], week="wk2")])
    assert playoffs(schedule, streamer=1, adds=1, streams=1).score([]) == pytest.approx(2)


def test_fit_compares_what_a_player_adds_with_a_player_on_an_average_schedule():
    # BOS 3 games, LAL 1, NY 1. On an average schedule, a player gets (3 + 1 + 1) / 3 games.
    schedule = days(["BOS"], ["BOS"], ["NY"], ["BOS", "LAL"])
    p = playoffs(schedule)
    assert p.fit([], player("BOS", 4)) == pytest.approx(1.5)  # 3 / (5/3) = 1.8: 1.5 is the most that fit can be
    assert p.fit([], player("NY", 4)) == pytest.approx(0.6)   # 1 / (5/3)
    assert p.fit([], player("MIA", 4)) == pytest.approx(0.5)  # no games: the least that fit can be


def test_fit_is_lower_for_a_player_with_no_slot():
    # Your 2 centers start at C and Util on each day. A third center has no slot, so he adds nothing.
    # A guard on the same schedule starts each day, as a player with any position does.
    schedule = days(["BOS", "NY"], ["BOS", "NY"])
    p = playoffs(schedule)
    core = [player("BOS", 9, "C"), player("BOS", 8, "C")]
    assert p.fit(core, player("NY", 4, "C")) == pytest.approx(0.5)
    assert p.fit(core, player("NY", 4, "PG")) == pytest.approx(1.0)


def test_fit_does_not_count_the_streamer_that_every_new_player_replaces():
    # Each new player takes the slot of the one streamer, so his gain is 4 - 3 = 1 on each day.
    # A player with any position on an average schedule has the same gain: fit = 1.
    p = playoffs(days(["BOS"], ["BOS"]), streamer=3, adds=1, streams=1)
    assert p.fit([player("BOS", 9, pos) for pos in ["PG", "SG", "SF", "PF", "C"]], player("BOS", 4, "C")) == pytest.approx(1.0)


def test_week_totals_add_the_stats_of_each_start_and_each_streamer():
    schedule = pd.concat([days(["BOS"], ["BOS", "NY"], week="wk1"), days(["BOS"], week="wk2")])
    p = playoffs(schedule, adds=1, streams=1, streamer_stats=(4, 2))
    totals = p.week_totals([player("BOS", 1, stats=(10, 5))])
    # wk1: 2 BOS games + 1 streamer game (the add on day 1 goes to BOS: 2 games left). wk2: 1 game + 1 streamer.
    assert totals.loc["wk1"].tolist() == pytest.approx([2 * 10 + 2 * 4, 2 * 5 + 2 * 2])
    assert totals.loc["wk2"].tolist() == pytest.approx([10 + 4, 5 + 2])
    assert totals.columns.tolist() == ["pts", "reb"]


class Fixed:
    """A random source that gives the same number each time."""

    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def test_a_player_who_rests_on_back_to_backs_gives_less_on_a_second_night():
    # BOS plays 3 days. Day 2 is the second night of a back-to-back. With rest_chance 1.0, the rester sits.
    schedule = days(["BOS"], ["BOS"], ["BOS"], b2b=[[], ["BOS"], []])
    p = playoffs(schedule)
    assert p.score([player("BOS", 10, rests_b2b=1)]) == pytest.approx(20)
    assert p.score([player("BOS", 10, rests_b2b=0)]) == pytest.approx(30)
    # With rest_chance 0.5, the second night gives half of his production.
    p.cfg = {**p.cfg, "risk": {**p.cfg["risk"], "rest_chance": 0.5}}
    assert p.score([player("BOS", 10, rests_b2b=1)]) == pytest.approx(25)


def test_the_rest_days_lower_the_fit():
    # A rester on a 2-game schedule with a back-to-back gets 1 game. The average schedule gives 2.
    schedule = days(["BOS", "NY"], ["BOS", "NY"], b2b=[[], ["BOS"]])
    p = playoffs(schedule)
    assert p.fit([], player("BOS", 4, rests_b2b=1)) == pytest.approx(0.5)
    assert p.fit([], player("BOS", 4)) == pytest.approx(1.0)


def test_draw_takes_a_player_out_for_a_whole_week():
    # med: chance 0.2. The random number 0.1 is below it, so he misses every week. 0.5 is above: he plays.
    schedule = pd.concat([days(["BOS"], ["BOS"], week="wk1"), days(["BOS"], week="wk2")])
    p = playoffs(schedule)
    out = p.draw([player("BOS", 8, stats=(4, 2), inj_risk="med")], Fixed(0.1))[0]
    assert out["out"] == {0, 1, 2}
    assert p.score([out]) == 0
    kept = p.draw([player("BOS", 8, stats=(4, 2), inj_risk="med")], Fixed(0.5))[0]
    assert kept["out"] == set()
    # His production goes up by 1 / (1 - 0.2), so the expected production is the same as without the draw.
    assert p.score([kept]) == pytest.approx(3 * 8 / 0.8)
    assert kept["stats"] == pytest.approx([4 / 0.8, 2 / 0.8])


def test_draw_uses_the_missing_tier_for_a_player_with_no_tier():
    # missing_tier is low, with chance 0. The player is never out, and his production does not change.
    p = playoffs(days(["BOS"]))
    for tier in [None, float("nan")]:
        out = p.draw([player("BOS", 8, inj_risk=tier)], Fixed(0.0))[0]
        assert out["out"] == set() and out["prod"] == 8
    out = p.draw([player("BOS", 8)], Fixed(0.0))[0]
    assert out["out"] == set()


def test_draw_gives_the_rest_days_of_a_rester():
    # No injury (random 0.5 is above every chance but high). Day 2 is a second night: the rester sits.
    schedule = days(["BOS"], ["BOS"], ["BOS"], b2b=[[], ["BOS"], []])
    p = playoffs(schedule)
    out = p.draw([player("BOS", 10, rests_b2b=1, inj_risk="low")], Fixed(0.5))[0]
    assert out["out"] == {1}
    assert p.score([out]) == pytest.approx(20)
    # week_totals also skips the rest day
    assert p.week_totals([{**out, "stats": [1.0, 1.0]}]).loc["wk1"].tolist() == pytest.approx([2, 2])
