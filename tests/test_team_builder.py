import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from common import DATA, load_config  # noqa: E402

ENGINE = ROOT / "scripts" / "team_builder.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")

# Reads {"data", "core": [ids], "fit": [ids]} on stdin. Writes {"score", "fits", "ms", "slots", "bench"}:
# ms = time of all fit calls. slots and bench: slotRoster of the core in the order of core, as player names.
DRIVER = """
const { scoreCore, fit, slotRoster } = require(process.argv[1]);
let text = "";
process.stdin.on("data", c => (text += c));
process.stdin.on("end", () => {
  const { data, core, fit: ids } = JSON.parse(text);
  const byId = new Map(data.players.map(p => [p.id, p]));
  const team = core.map(id => byId.get(id));
  const score = scoreCore(team, data);
  const start = performance.now();
  const fits = ids.map(id => fit(team, byId.get(id), data));
  const ms = performance.now() - start;
  const roster = slotRoster(team, data);
  const slots = Object.fromEntries(Object.entries(roster.slots).map(([s, p]) => [s, p.name]));
  process.stdout.write(JSON.stringify({ score, fits, ms, slots, bench: roster.bench.map(p => p.name) }));
});
"""


def engine(data, core, fit=()):
    """Run team_builder.js in node. core and fit are lists of player ids."""
    out = subprocess.run(["node", "-e", DRIVER, str(ENGINE)], input=json.dumps({"data": data, "core": core, "fit": list(fit)}),
                         capture_output=True, text=True, check=True, encoding="utf-8")
    return json.loads(out.stdout)


def day(teams, week="wk21", quality=False, b2b=(), date="2027-03-22"):
    return {"date": date, "week": week, "nba_games": 3 if quality else 10, "quality": quality, "teams": list(teams), "b2b": list(b2b)}


def player(id, team, pos, value, rests_b2b=0):
    """The name is the id as text, for example "p1"."""
    return {"id": id, "name": f"p{id}", "team": team, "pos": pos.split("/"), "rank": id, "value": value,
            "rests_b2b": rests_b2b, "league_price": 1}


def data(days, players):
    return {"slots": ["PG", "SG", "SF", "PF", "C"], "util": 1, "budget": 200, "spots": 10, "core_max_rank": 75,
            "weak_week_started": 0, "weeks": ["wk19", "wk20", "wk21"], "days": days, "players": players}


def test_two_pgs_and_a_c_all_start():
    result = engine(data([day(["BOS"])], [player(1, "BOS", "PG", 9), player(2, "BOS", "PG", 8), player(3, "BOS", "C", 7)]), [1, 2, 3])
    assert result["score"]["total"] == {"started": 3, "lost": 0, "holes": 0}
    assert result["score"]["days"][0]["starters"] == {"PG": "p1", "C": "p3", "Util": "p2"}
    assert result["score"]["days"][0]["empty"] == ["SG", "SF", "PF"]


def test_the_lowest_value_pg_sits_when_util_is_full():
    pgs = [player(1, "BOS", "PG", 5), player(2, "BOS", "PG", 9), player(3, "BOS", "PG", 7)]
    result = engine(data([day(["BOS"])], pgs), [1, 2, 3])["score"]
    assert result["weeks"]["wk21"] == {"started": 2, "lost": 1, "lost_by": {"p1": 1}, "holes": 0}
    assert result["days"][0]["sat"] == ["p1"]


def test_matching_puts_a_pg_sg_player_in_sg_when_pg_is_full():
    # The PG/SG player has the higher value, so he takes PG first. The PG-only player moves him to SG.
    players = [player(1, "BOS", "PG/SG", 9), player(2, "BOS", "PG", 8), player(3, "BOS", "PG", 7)]
    result = engine(data([day(["BOS"])], players), [1, 2, 3])["score"]
    assert result["days"][0]["starters"] == {"PG": "p2", "SG": "p1", "Util": "p3"}
    assert result["total"]["lost"] == 0


def test_a_rest_player_on_a_second_night_has_no_started_and_no_lost_game():
    players = [player(1, "BOS", "PG", 9, rests_b2b=1), player(2, "BOS", "C", 8)]
    result = engine(data([day(["BOS"], b2b=["BOS"])], players), [1, 2])["score"]
    assert result["total"] == {"started": 1, "lost": 0, "holes": 0}
    assert result["days"][0]["rested"] == ["p1"]
    assert result["days"][0]["sat"] == []


def test_holes_count_on_quality_days_only():
    players = [player(i, "BOS", pos, 10 - i) for i, pos in enumerate(["PG", "SG", "SF", "PF"], 1)]
    days = [day(["BOS"], week="wk19", quality=True, date="2027-03-08"), day(["BOS"], week="wk20", date="2027-03-15")]
    result = engine(data(days, players), [1, 2, 3, 4])["score"]
    assert result["weeks"]["wk19"]["holes"] == 2
    assert result["weeks"]["wk20"]["holes"] == 0
    assert result["days"][0]["empty"] == ["C", "Util"]
    assert result["days"][1]["empty"] == ["C", "Util"]  # stream room: empty, but not a hole


def test_the_finals_values_equal_the_week_21_values():
    players = [player(1, "BOS", "PG", 9), player(2, "BOS", "PG", 8), player(3, "BOS", "PG", 7)]
    days = [day(["BOS"], week="wk19", date="2027-03-08"), day(["BOS"], quality=True), day(["BOS"], quality=True, date="2027-03-23")]
    result = engine(data(days, players), [1, 2, 3])["score"]
    week = result["weeks"]["wk21"]
    assert result["finals"] == {"started": week["started"], "lost": week["lost"], "holes": week["holes"]}
    assert result["finals"] == {"started": 4, "lost": 2, "holes": 8}
    assert result["total"] == {"started": 6, "lost": 3, "holes": 8}


def test_fit_gives_the_change_in_started_games_finals_and_holes():
    players = [player(1, "BOS", "PG", 9), player(2, "BOS", "C", 8),
               player(3, "NY", "SF", 5), player(4, "BOS", "PG", 4), player(5, "LAL", "SG", 3)]
    days = [day(["BOS", "NY"], week="wk19", quality=True, date="2027-03-08"), day(["BOS"], quality=True)]
    result = engine(data(days, players), [1, 2, 4], fit=[3, 5])
    # NY plays on one quality day in wk19: +1 started game, 1 hole less, no finals game. LAL does not play.
    assert result["fits"] == [
        {"started": 1, "finals": 0, "holes_removed": 1, "games": 1, "quality": 1, "quality_started": 1},
        {"started": 0, "finals": 0, "holes_removed": 0, "games": 0, "quality": 0, "quality_started": 0}]


def test_fit_of_a_player_who_sits_is_zero_of_his_games_and_fit_with_an_empty_core_is_his_games():
    players = [player(1, "BOS", "PG", 9), player(2, "BOS", "PG", 8), player(3, "BOS", "PG", 7)]
    days = [day(["BOS"], quality=True)]
    assert engine(data(days, players), [1, 2], fit=[3])["fits"] == [
        {"started": 0, "finals": 0, "holes_removed": 0, "games": 1, "quality": 1, "quality_started": 0}]
    assert engine(data(days, players), [], fit=[3])["fits"] == [
        {"started": 1, "finals": 1, "holes_removed": 1, "games": 1, "quality": 1, "quality_started": 1}]


def test_fit_games_leave_out_rest_nights():
    players = [player(1, "BOS", "C", 9), player(2, "NY", "PG", 5, rests_b2b=1)]
    days = [day(["NY"], quality=True, b2b=["NY"]), day(["NY"], date="2027-03-23")]
    fits = engine(data(days, players), [1], fit=[2])["fits"]
    assert fits == [{"started": 1, "finals": 1, "holes_removed": 0, "games": 1, "quality": 0, "quality_started": 0}]


def test_slot_roster_fills_position_slots_then_util_then_the_bench():
    players = [player(1, "BOS", "PG", 9), player(2, "NY", "PG", 8), player(3, "LAL", "PG/SG", 7),
               player(4, "BOS", "C", 6), player(5, "NY", "PG", 5), player(6, "LAL", "", 4)]
    result = engine(data([day(["BOS"])], players), [1, 2, 3, 4, 5, 6])
    # p3 moves to SG so that p2 can take Util. p5 has no PG or Util slot left. p6 has no position.
    assert result["slots"] == {"PG": "p1", "SG": "p3", "C": "p4", "Util": "p2"}
    assert result["bench"] == ["p5", "p6"]


def test_slot_roster_moves_a_high_value_player_into_a_starting_slot():
    # In value order, p2 (PG/SG) takes PG first. p3 (PG) then needs PG, so the matching moves p2 to SG.
    # p4 and p5 are SG only: p4 gets Util and p5, the lowest value, goes to the bench.
    players = [player(1, "BOS", "C", 9), player(2, "NY", "PG/SG", 8), player(3, "LAL", "PG", 7),
               player(4, "BOS", "SG", 6), player(5, "NY", "SG", 5)]
    result = engine(data([day(["BOS"])], players), [1, 2, 3, 4, 5])
    assert result["slots"] == {"PG": "p3", "SG": "p2", "C": "p1", "Util": "p4"}
    assert result["bench"] == ["p5"]


def test_fit_for_500_players_takes_less_than_100_ms():
    rng = random.Random(36)
    teams = [f"T{i}" for i in range(30)]
    days = [day(rng.sample(teams, rng.randint(4, 30)), week=f"wk{19 + i // 7}", quality=rng.random() < 0.3, date=str(i))
            for i in range(21)]
    positions = ["PG", "PG/SG", "SG/SF", "SF/PF", "PF/C", "C", "SG/SF/PF"]
    players = [player(i, rng.choice(teams), rng.choice(positions), 500 - i, rests_b2b=int(rng.random() < 0.1)) for i in range(500)]
    result = engine(data(days, players), [0, 3, 7, 12, 20, 33, 41], fit=range(500))
    assert len(result["fits"]) == 500
    assert result["ms"] < 100


# Real schedule and rankings: 3 random cores of 6, 7 and 8 top-75 players.

@pytest.fixture(scope="module")
def real():
    """(page data, Playoffs) from data/. Skips when the data files are not there."""
    cfg = load_config()
    if not (DATA / "schedule.csv").exists() or not (ROOT / cfg["league"]["projections"]).exists():
        pytest.skip("data/schedule.csv or the projections file is missing")
    from playoffs import playoff_schedule, read_schedule
    from rankings import build_rankings
    from team_score import make_playoffs

    teams, days = playoff_schedule(read_schedule(), cfg)
    rankings = build_rankings(cfg, teams)
    top = rankings[(rankings["rank"] <= 75) & rankings.team.notna()]
    players, playoffs = make_playoffs(top, days, cfg)
    page = data([{"date": d.date.strftime("%Y-%m-%d"), "week": d.week, "nba_games": int(d.nba_games), "quality": bool(d.quality),
                  "teams": list(d.teams), "b2b": list(d.b2b)} for d in days.itertuples()],
                [{"id": int(r.player_id), "name": r.name, "team": r.team, "pos": r.pos.split("/"), "rank": int(r.rank),
                  "value": float(r.value), "rests_b2b": int(r.rests_b2b), "league_price": 1} for r in players.itertuples()])
    page["weeks"] = [w["name"] for w in cfg["playoffs"]["weeks"]]
    return page, playoffs, players


def random_core(page, size):
    return random.Random(size).sample([p["id"] for p in page["players"]], size)


@pytest.mark.parametrize("size", [6, 7, 8])
def test_random_core_counts_agree_with_the_days(real, size):
    page, _, _ = real
    result = engine(page, random_core(page, size))["score"]
    slots = len(page["slots"]) + page["util"]
    assert all(len(d["starters"]) + len(d["empty"]) == slots for d in result["days"])
    assert result["total"]["started"] == sum(len(d["starters"]) for d in result["days"])
    assert result["total"]["lost"] == sum(len(d["sat"]) for d in result["days"])
    assert result["total"]["holes"] == sum(len(d["empty"]) for d in result["days"] if d["quality"])
    assert result["finals"] == {k: v for k, v in result["weeks"][page["weeks"][-1]].items() if k != "lost_by"}


@pytest.mark.parametrize("size", [6, 7, 8])
def test_random_core_agrees_with_python_game_counts(real, size):
    page, playoffs, players = real
    if not hasattr(playoffs, "game_counts"):
        pytest.skip("Playoffs.game_counts is not in team_score.py yet (#35)")
    core = random_core(page, size)
    roster = players.set_index("player_id").loc[core].reset_index().to_dict("records")
    expected = playoffs.game_counts(roster)
    result = engine(page, core)["score"]
    assert result["weeks"] == expected["weeks"]
    assert result["total"] == expected["total"]
    assert result["finals"] == expected["finals"]
