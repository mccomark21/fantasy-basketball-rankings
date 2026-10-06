"""Playoff face-offs: the top teams play head-to-head category matchups in the playoff weeks.

  1. Seeds: the teams with the highest season value make the playoffs ([league] playoff_teams).
  2. Each playoff team gets one random result for each week: each category total is its expected total
     (team_score.Playoffs.week_totals) + random noise. The noise treats a total as a random count
     (variance = mean). Points have more spread (SPREAD). See docs/category_weights.md.
  3. A team wins a matchup if it wins more categories. In the bracket, a tie goes to the higher seed.
  4. Round robin: in each playoff week, each pair of playoff teams plays. A tie counts as half a win.
  5. Bracket: 1 v 8, 4 v 5, 2 v 7, 3 v 6. The final is in the last playoff week.
Team 0 is your team.
"""
import math

import numpy as np

SPREAD = {"pts": 2.0}  # variance / mean of a weekly total. Other categories: 1.


def face_offs(totals, season_values, rng, cfg):
    """Your results: made_playoffs, rr_win_pct (your round-robin win percent) and title.

    totals: the week totals of each team (a DataFrame with one row for each week). season_values: an array.
    """
    weeks = [w["name"] for w in cfg["playoffs"]["weeks"]]
    seeds = [int(t) for t in np.argsort(-season_values, kind="stable")[:cfg["league"]["playoff_teams"]]]
    if 0 not in seeds:
        return {"made_playoffs": False, "rr_win_pct": math.nan, "title": False}

    results = {t: _week_results(totals[t].loc[weeks], rng) for t in seeds}
    rr = [_score(results[0][w], results[t][w]) for w in range(len(weeks)) for t in seeds if t != 0]

    alive = [seeds[s - 1] for s in _bracket_order(len(seeds))]
    first_week = len(weeks) - int(math.log2(len(seeds)))
    for w in range(first_week, len(weeks)):
        alive = [_winner(a, b, results, w, seeds) for a, b in zip(alive[::2], alive[1::2])]
    return {"made_playoffs": True, "rr_win_pct": 100 * float(np.mean(rr)), "title": alive == [0]}


def _week_results(expected, rng):
    """One random week for each row of expected: an array with one row for each week."""
    spread = np.array([SPREAD.get(cat, 1.0) for cat in expected.columns])
    mean = expected.to_numpy()
    return rng.normal(mean, np.sqrt(spread * np.clip(mean, 0, None)))


def _score(a, b):
    """1 if a wins more categories than b, 0.5 for a tie, 0 for a loss."""
    wins, losses = (a > b).sum(), (b > a).sum()
    return 1.0 if wins > losses else 0.5 if wins == losses else 0.0


def _winner(a, b, results, w, seeds):
    """The winner of a bracket matchup in week w. A tie goes to the higher seed."""
    score = _score(results[a][w], results[b][w])
    if score == 0.5:
        return min(a, b, key=seeds.index)
    return a if score == 1.0 else b


def _bracket_order(n):
    """Seeds in bracket order, so that the top seeds meet last. 8 teams: 1, 8, 4, 5, 2, 7, 3, 6."""
    order = [1]
    while len(order) < n:
        order = [s for seed in order for s in (seed, 2 * len(order) + 1 - seed)]
    return order
