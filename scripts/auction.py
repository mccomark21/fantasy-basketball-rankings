"""Auction simulator: run this league's auction many times. Team 0 is your team. Teams 1 to teams - 1 are bots.

One auction:
  1. Nominations go in league_price order, with random noise.
  2. Each bot's maximum bid starts at league_price and moves to yahoo_cost as the roster spots fill
     (the room cools). Each bot multiplies it by its own random noise.
  3. Your bot buys a core of [simulation] core players and pays min_bid for each stream spot (the other spots).
     For a core player, your maximum bid is dollars x core_scale x the playoff fit (see _your_bid).
     When your core is full, your maximum bid is min_bid.
  4. A team bids only if the player leaves room to fill the position slots (config.toml [league] slots).
     Util and bench take any player.
  5. A maximum bid is at least min_bid and at most money left - min_bid x (empty spots - 1).
  6. The highest maximum bid wins. The winner pays the second-highest maximum bid + $1,
     but not more than his own maximum bid. Ties go to a random team.
Team score: the playoff score of your core and your streamers (team_score.py), and the sum of your dollars.
Then the top teams play the playoff weeks head to head (matchups.py).
Output: for each keeper in config.toml [simulation], your title percent, your playoff results and the players that
you win most. The auctions run in parallel, one process for each CPU core.
"""
import os
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat

import numpy as np
import pandas as pd

from common import OUT, load_config
from matchups import face_offs
from playoffs import playoff_schedule, read_schedule
from rankings import build_rankings
from sim_results import group_table, player_table
from team_score import make_playoffs, open_slots

CHUNKS = 64  # parts of the auctions for the parallel run


def run_auction(pool, cfg, rng, keeper=None, playoffs=None):
    """One auction. Returns one row for each player sold: name, team and price.

    pool needs name, pos, dollars, league_price and yahoo_cost. A missing price is $0.
    keeper is the name of your keeper. He is the first row, and his price is league_price (rounded).
    playoffs is a team_score.Playoffs. With it, your bid uses the playoff fit, and pool also needs team and prod.
    """
    teams, a = cfg["league"]["teams"], cfg["auction"]
    noise = cfg["simulation"]["noise"]
    min_bid, slots = a["min_bid"], cfg["league"]["slots"]
    scale = core_scale(pool.dollars, cfg)
    pool = pool.assign(league_price=pool.league_price.fillna(0), yahoo_cost=pool.yahoo_cost.fillna(0),
                       positions=pool.pos.str.split("/").map(set))
    money = np.full(teams, a["budget"])
    spots = np.full(teams, a["spots"])
    rosters = [[] for _ in range(teams)]
    core = []  # your core players, as team_score players
    total = spots.sum()
    sales = []
    if keeper is not None:
        kept = next(pool[pool.name == keeper].itertuples())
        price = round(kept.league_price)
        rosters[0].append(kept.positions)
        core.append(_player(kept, playoffs))
        money[0] -= price
        spots[0] -= 1
        sales.append((keeper, 0, price))
        pool = pool[pool.name != keeper]

    order = pool.league_price.clip(lower=min_bid) * rng.lognormal(0, noise, len(pool))
    for p in pool.loc[order.sort_values(ascending=False, kind="stable").index].itertuples():
        if spots.sum() == 0:
            break
        fits = np.array([_fits(rosters[t], spots[t], p.positions, slots) for t in range(teams)])
        if not fits.any():
            continue
        cooled = 1 - spots.sum() / total
        bids = ((1 - cooled) * p.league_price + cooled * p.yahoo_cost) * rng.lognormal(0, noise, teams)
        bids[0] = _your_bid(p, core, scale, playoffs, cfg) if fits[0] else 0
        limit = money - min_bid * (spots - 1)
        bids = np.where(fits, np.clip(np.floor(bids), min_bid, limit), 0)
        top = np.flatnonzero(bids == bids.max())
        win = rng.choice(top)
        price = bids[win] if len(top) > 1 else np.sort(bids)[-2] + 1
        money[win] -= price
        spots[win] -= 1
        rosters[win].append(p.positions)
        if win == 0 and len(core) < cfg["simulation"]["core"]:
            core.append(_player(p, playoffs))
        sales.append((p.name, win, price))
    return pd.DataFrame(sales, columns=["name", "team", "price"])


def core_scale(dollars, cfg):
    """Multiplier for your core bids: the money of your stream spots goes to your core.

    The dollars of the bought players assume that each team pays for all its spots. A team's stream spots are
    worth the cheapest bought players (spots - core for each team). You pay min_bid for each of them instead.
    """
    teams, a, core = cfg["league"]["teams"], cfg["auction"], cfg["simulation"]["core"]
    bought = dollars.nlargest(teams * a["spots"])
    streams = a["spots"] - core
    stream_dollars = bought.nsmallest(teams * streams).sum() / teams if streams else 0
    return (a["budget"] - a["min_bid"] * streams) / (a["budget"] - stream_dollars)


def _your_bid(p, core, scale, playoffs, cfg):
    """Your maximum bid before the limits: dollars x scale for a core player, x the playoff fit if playoffs is set.

    Your bid blends the fit: 1 - playoff_weight + playoff_weight x fit. When your core is full, the bid is 0 (min_bid).
    """
    sim = cfg["simulation"]
    if len(core) >= sim["core"] or p.dollars <= 0:
        return 0
    bid = p.dollars * scale
    if playoffs is not None:
        w = sim["playoff_weight"]
        bid *= 1 - w + w * playoffs.fit(core, _player(p, playoffs))
    return bid


def _player(row, playoffs):
    """A pool row as a team_score player. None if playoffs is None."""
    return {"team": row.team, "prod": row.prod, "pos": row.pos} if playoffs is not None else None


def _fits(roster, spots, pos, slots):
    """True if a team with this roster (a list of position sets) and empty spots can add a player with pos."""
    return spots > 0 and open_slots(roster + [pos], slots) <= spots - 1


def simulate(pool, cfg, keeper, runs, rng, playoffs=None):
    """Run the auction runs times. Returns (scores, won).

    scores: one row for each run. dollars is the sum of dollars of your players. With playoffs:
            - playoff: the playoff score of your core (the keeper and the first players that you win).
            - made_playoffs, rr_win_pct and title: your results in the face-offs (matchups.py).
              Each bot streams like you: its core is its best players by prod. pool also needs stats and value.
    won: one row for each player that you win (not the keeper), most often first.
         win_pct is the percent of runs that you win him. price is the median price that you pay.
    """
    scores, mine = _auctions(pool, cfg, keeper, runs, rng, playoffs)
    return scores, _wins(mine[mine.name != keeper], runs)


def _auctions(pool, cfg, keeper, runs, rng, playoffs):
    """(scores, mine): the scores of simulate() and the players that you buy in each run.

    mine has name, price, run (the row of scores) and core (True for the keeper and your core players).
    """
    players = pool.set_index("name")
    scores, sales = [], []
    for run in range(runs):
        sold = run_auction(pool, cfg, rng, keeper, playoffs)
        mine = sold.query("team == 0").assign(run=run)
        mine["core"] = np.arange(len(mine)) < cfg["simulation"]["core"]  # the same core as _core()
        score = {"dollars": players.dollars[mine.name].sum()}
        if playoffs is not None:
            cores = [_core(players, sold.name[sold.team == t], t, cfg) for t in range(cfg["league"]["teams"])]
            score["playoff"] = playoffs.score(cores[0].to_dict("records"))
            totals = [playoffs.week_totals(core.to_dict("records")) for core in cores]
            # Each team plays its core and streams its other spots, so the season value of its core gives the seeds
            score.update(face_offs(totals, np.array([core.value.sum() for core in cores]), rng, cfg))
        scores.append(score)
        sales.append(mine.drop(columns="team"))
    return pd.DataFrame(scores), pd.concat(sales)


def _wins(mine, runs):
    """Make won (see simulate()) from the players that you buy in all runs."""
    won = mine.groupby("name").price.agg(win_pct="size", price="median")
    won["win_pct"] = 100 * won.win_pct / runs
    return won.sort_values("win_pct", ascending=False)


def _core(players, names, team, cfg):
    """The core of a team: your first core players (you buy them first), or a bot's best core players by prod."""
    roster = players.loc[names].reset_index()
    core = cfg["simulation"]["core"]
    return roster.head(core) if team == 0 else roster.nlargest(core, "prod")


def main():
    cfg = load_config()
    sim = cfg["simulation"]
    rankings = build_rankings(cfg)
    players, playoffs = make_playoffs(rankings, playoff_schedule(read_schedule(), cfg)[1], cfg)
    pool = players[["name", "pos", "dollars", "league_price", "yahoo_cost", "team", "prod", "stats", "value"]]
    missing = sorted(set(sim["keepers"]) - set(pool.name))
    if missing:
        raise SystemExit(f"The rankings do not have these keepers: {', '.join(missing)}. "
                         "Change keepers in [simulation] in config.toml.")

    # The auctions run in CHUNKS parts, each with its own seed, on all CPU cores. The number of parts does not
    # change with the CPU count, so each PC gets the same results. Each keeper gets the same seeds, so each
    # keeper sees the same random numbers, and the comparison is fair.
    parts = [len(part) for part in np.array_split(np.arange(sim["runs"]), CHUNKS)]
    starts = np.cumsum([0, *parts[:-1]])  # the first run number of each part
    summary, all_runs = {}, []
    with ProcessPoolExecutor(os.cpu_count()) as executor:
        for keeper in sim["keepers"]:
            seeds = np.random.SeedSequence(sim["seed"]).spawn(CHUNKS)
            results = list(executor.map(_auctions, repeat(pool), repeat(cfg), repeat(keeper), parts,
                                        [np.random.default_rng(seed) for seed in seeds], repeat(playoffs)))
            scores = pd.concat([r[0] for r in results], ignore_index=True)
            mine = pd.concat([r[1].assign(run=r[1].run + start) for r, start in zip(results, starts)])
            won = _wins(mine[mine.name != keeper], sim["runs"])
            all_runs.append(mine.join(scores, on="run").rename(columns={"name": "player"}).assign(keeper=keeper))
            summary[keeper] = {"cost": round(pool.set_index("name").league_price[keeper]),
                               "title_pct": 100 * scores.title.mean(),
                               "playoffs_pct": 100 * scores.made_playoffs.mean(),
                               "rr_win_pct": scores.rr_win_pct.mean(),
                               "playoff_score": scores.playoff.median(),
                               "dollars": scores.dollars.median()}
            print(f"\nKeeper {keeper}: players that you win most often")
            print(won.head(15).round(0).to_string())

    print(f"\nIn {sim['runs']} auctions:")
    print("  title_pct: you win the title. playoffs_pct: you are in the top "
          f"{cfg['league']['playoff_teams']} by season value.")
    print("  rr_win_pct: your win percent against the other playoff teams in each playoff week (when you are in).")
    print(f"  playoff_score: the median playoff score of your core ({sim['core']} players) and your streamers.")
    print("  dollars: the median sum of your dollars.")
    summary = pd.DataFrame(summary).T.rename_axis("keeper")
    print(summary.round(1).to_string())
    write_results(summary, pd.concat(all_runs, ignore_index=True), players)


def write_results(summary, runs, players):
    """Write the simulation_*.csv files to output/. runs: one row for each player that you buy in each auction."""
    OUT.mkdir(exist_ok=True)
    info = players.set_index("name")[["pos", "team", "dollars", "league_price", "playoff_games", "quality_games"]]
    summary.round(2).to_csv(OUT / "simulation_summary.csv")
    order = {k: i for i, k in enumerate(summary.index)}  # the keeper order of config.toml
    table = player_table(runs).join(info, on="player").sort_values("keeper", key=lambda k: k.map(order), kind="stable")
    table.round(2).to_csv(OUT / "simulation_players.csv", index=False)
    groups = group_table(runs).sort_values("keeper", key=lambda k: k.map(order), kind="stable")
    groups.round(2).to_csv(OUT / "simulation_groups.csv", index=False)
    cols = ["keeper", "run", "player", "price", "core", "title", "made_playoffs", "rr_win_pct", "playoff", "dollars"]
    runs[cols].rename(columns={"playoff": "playoff_score"}).round(2).to_csv(OUT / "simulation_runs.csv", index=False)
    print("\nWrote simulation_summary.csv, simulation_players.csv, simulation_groups.csv and simulation_runs.csv "
          f"to {OUT}")


if __name__ == "__main__":
    main()
