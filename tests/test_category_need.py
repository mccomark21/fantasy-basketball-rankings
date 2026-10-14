import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
ENGINE = ROOT / "scripts" / "category_need.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")

CATS = ["pts", "reb", "ast", "threes", "stl", "blk"]

# Reads {"data", "roster", "candidates": [{player, price}]} on stdin.
# Writes {"gap", "needs", "ms"}: gap = categoryGap of the roster, needs = need for each candidate, ms = time of all need calls.
DRIVER = """
const { categoryGap, need } = require(process.argv[1]);
let text = "";
process.stdin.on("data", c => (text += c));
process.stdin.on("end", () => {
  const { data, roster, candidates } = JSON.parse(text);
  const gap = categoryGap(roster, data);
  const start = performance.now();
  const needs = candidates.map(c => need(roster, c, data));
  const ms = performance.now() - start;
  process.stdout.write(JSON.stringify({ gap, needs, ms }));
});
"""


def engine(data, roster, candidates=()):
    """Run category_need.js in node."""
    out = subprocess.run(["node", "-e", DRIVER, str(ENGINE)],
                         input=json.dumps({"data": data, "roster": roster, "candidates": list(candidates)}),
                         capture_output=True, text=True, check=True, encoding="utf-8")
    return json.loads(out.stdout)


def wz(**kw):
    return {c: kw.get(c, 0.0) for c in CATS}


def player(name, **kw):
    return {"name": name, "wz": wz(**kw)}


def pick(name, price, core=True, **kw):
    return {"player": player(name, **kw), "price": price, "core": core}


def curve():
    """Prices 1 to 60. The filler gets better as the price rises: pts and blk both equal 0.1 x price."""
    return [{"price": p, "wz": wz(pts=p / 10, blk=p / 10)} for p in range(1, 61)]


def data(benchmark=None):
    return {"budget": 200, "spots": 10, "category": {
        "cats": CATS, "benchmark": benchmark or wz(pts=10.0, blk=8.0), "core_size": 7, "min_bid": 1, "band": 0.5,
        "filler_curve": curve()}}


def test_empty_roster_is_seven_fillers():
    # Core money = 200 - 1 x 3 stream spots = 197. Filler price = 197 / 7 = 28.14, so the row is 28.
    out = engine(data(), [])["gap"]
    assert out["filler_price"] == pytest.approx(197 / 7)
    assert out["totals"]["pts"] == pytest.approx(7 * 2.8)
    assert out["gaps"]["pts"] == 0 and out["labels"]["pts"] == "ahead"
    assert out["gaps"]["reb"] == 0 and out["labels"]["reb"] == "even"


def test_half_full_roster_counts_players_and_fillers():
    roster = [pick("a", 40, pts=3.0, blk=1.0), pick("b", 30, pts=2.0), pick("c", 1, core=False, pts=9.0),
              pick("d", 20, pts=1.0, blk=0.5)]
    out = engine(data(wz(pts=30.0, blk=30.0)), roster)["gap"]
    # Other spent = 1 and 2 stream spots are empty, so core money = 200 - 1 - 2 = 197.
    # Core spent = 90 and 4 core spots are empty, so the filler price = 107 / 4 = 26.75. The row is 27 (2.7).
    assert out["filler_price"] == pytest.approx(107 / 4)
    assert out["totals"]["pts"] == pytest.approx(6.0 + 4 * 2.7)  # the non-core pts 9.0 is not counted
    assert out["totals"]["blk"] == pytest.approx(1.5 + 4 * 2.7)
    assert out["gaps"]["blk"] == pytest.approx(30.0 - 1.5 - 4 * 2.7)
    assert out["labels"]["blk"] == "behind"


def test_full_core_has_no_filler():
    roster = [pick(f"p{i}", 20, pts=1.0, blk=1.0) for i in range(7)]
    out = engine(data(wz(pts=8.0, blk=7.0)), roster)["gap"]
    assert out["filler_price"] is None
    assert out["totals"]["pts"] == pytest.approx(7.0)
    assert out["gaps"]["pts"] == pytest.approx(1.0) and out["labels"]["pts"] == "behind"
    assert out["gaps"]["blk"] == 0 and out["labels"]["blk"] == "even"  # the total equals the benchmark


def test_labels_at_the_band_edges():
    roster = [pick(f"p{i}", 20) for i in range(7)]
    roster[0]["player"]["wz"].update(pts=9.5, reb=-0.5, ast=10.5, threes=10.49, stl=10.51)
    d = data(wz(pts=10.0, reb=0.0, ast=10.0, threes=10.0, stl=10.0, blk=0.0))
    labels = engine(d, roster)["gap"]["labels"]
    assert labels["pts"] == "behind"  # gap 0.5
    assert labels["reb"] == "behind"  # gap 0.5
    assert labels["ast"] == "ahead"  # total = benchmark + 0.5
    assert labels["threes"] == "even"
    assert labels["stl"] == "ahead"
    assert labels["blk"] == "even"


def test_candidate_closes_a_gap():
    roster = [pick(f"p{i}", 10, pts=1.0, blk=1.0) for i in range(3)]
    cand = {"player": player("big", pts=5.0, blk=5.0), "price": 20}
    out = engine(data(wz(pts=30.0, blk=30.0)), roster, [cand])["needs"][0]
    # Before: 4 empty spots, price 167 / 4 = 41.75, row 42 (4.2). Totals 3 + 16.8 = 19.8. Gaps 10.2 and 10.2.
    # After: 3 empty spots, price 147 / 3 = 49 (4.9). Totals 3 + 5 + 14.7 = 22.7. Gaps 7.3 and 7.3.
    assert out["need"] == pytest.approx(20.4 - 14.6)
    assert out["gaps_after"]["pts"] == pytest.approx(7.3)
    assert out["gaps_after"]["reb"] == 0


def test_candidate_with_negative_need():
    # A weak, expensive pick takes money from the fillers and gives little, so the gaps grow.
    roster = [pick(f"p{i}", 10, pts=1.0, blk=1.0) for i in range(3)]
    cand = {"player": player("dud", pts=0.5), "price": 80}
    out = engine(data(wz(pts=15.0, blk=15.0)), roster, [cand])["needs"][0]
    # Before: 4 empty spots, price 167 / 4 = 41.75, row 42 (4.2). Totals 3 + 16.8 = 19.8. No gap.
    # After: 3 empty spots, price 87 / 3 = 29 (2.9). pts 3.5 + 8.7 = 12.2 and blk 3 + 8.7 = 11.7.
    assert out["need"] == pytest.approx(-(15 - 12.2) - (15 - 11.7))
    assert out["gaps_after"]["pts"] == pytest.approx(2.8)
    assert out["gaps_after"]["blk"] == pytest.approx(3.3)


def test_category_above_benchmark_adds_nothing():
    roster = [pick(f"p{i}", 20, pts=3.0) for i in range(6)]
    cand = {"player": player("scorer", pts=5.0), "price": 20}
    out = engine(data(wz(pts=5.0)), roster, [cand])["needs"][0]
    assert out["gaps_after"]["pts"] == 0
    assert out["need"] == pytest.approx(0)


def test_price_outside_the_curve_is_clamped():
    rich = engine(data(), [pick(f"p{i}", 1) for i in range(6)])["gap"]
    assert rich["filler_price"] == pytest.approx(191)  # above 60: the row for 60
    assert rich["totals"]["pts"] == pytest.approx(6.0)
    poor = engine(data(), [pick(f"p{i}", 40) for i in range(6)])["gap"]
    assert poor["filler_price"] == pytest.approx(-43)  # below 1: the row for 1
    assert poor["totals"]["pts"] == pytest.approx(0.1)


def test_speed_500_candidates():
    roster = [pick(f"p{i}", 15, pts=1.0, blk=0.5) for i in range(4)]
    cands = [{"player": player(f"c{i}", pts=(i % 7) / 3, blk=(i % 5) / 4), "price": 1 + i % 60} for i in range(500)]
    out = engine(data(), roster, cands)
    print(f"need x 500: {out['ms']:.2f} ms")
    assert out["ms"] < 100
