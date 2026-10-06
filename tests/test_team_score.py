import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from team_score import Playoffs  # noqa: E402

CFG = {"league": {"slots": ["PG", "SG", "SF", "PF", "C"]}, "auction": {"spots": 10}, "weights": {"pts": 1, "reb": 1},
       "simulation": {"fit_limits": [0.5, 1.5]}}


def days(*teams_by_day, week="wk1", quality=False):
    """One row for each day. Each argument is the list of NBA teams that play that day."""
    return pd.DataFrame({"week": week, "quality": quality, "teams": list(teams_by_day)})


def player(team, prod, pos="PG", stats=(0, 0)):
    """stats: per-game pts and reb."""
    return {"team": team, "prod": prod, "pos": pos, "stats": list(stats)}


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
