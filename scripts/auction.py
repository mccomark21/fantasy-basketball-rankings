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
Output: for each keeper in config.toml [simulation], the range of your team score and the players that you win most.
"""
import numpy as np
import pandas as pd

from common import load_config
from playoffs import playoff_schedule, read_schedule
from rankings import build_rankings
from team_score import make_playoffs, open_slots


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

    The fit is blended: 1 - playoff_weight + playoff_weight x fit. When your core is full, the bid is 0 (min_bid).
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
    """A pool row as a team_score player. None if there is no playoffs."""
    return {"team": row.team, "prod": row.prod, "pos": row.pos} if playoffs is not None else None


def _fits(roster, spots, pos, slots):
    """True if a team with this roster (a list of position sets) and empty spots can add a player with pos."""
    return spots > 0 and open_slots(roster + [pos], slots) <= spots - 1


def simulate(pool, cfg, keeper, runs, rng, playoffs=None):
    """Run the auction runs times. Returns (scores, won).

    scores: one row for each run. dollars is the sum of dollars of your players. With playoffs, playoff is
            the playoff score of your core (the keeper and the first players that you win, see team_score.py).
    won: one row for each player that you win (not the keeper), most often first.
         win_pct is the percent of runs that you win him. price is the median price that you pay.
    """
    players = pool.set_index("name")
    scores, sales = [], []
    for _ in range(runs):
        mine = run_auction(pool, cfg, rng, keeper, playoffs).query("team == 0")
        score = {"dollars": players.dollars[mine.name].sum()}
        if playoffs is not None:
            core = players.loc[mine.name[:cfg["simulation"]["core"]]]
            score["playoff"] = playoffs.score(core.reset_index()[["team", "prod", "pos"]].to_dict("records"))
        scores.append(score)
        sales.append(mine[mine.name != keeper])
    won = pd.concat(sales).groupby("name").price.agg(win_pct="size", price="median")
    won["win_pct"] = 100 * won.win_pct / runs
    return pd.DataFrame(scores), won.sort_values("win_pct", ascending=False)


def main():
    cfg = load_config()
    sim = cfg["simulation"]
    rankings = build_rankings(cfg)
    players, playoffs = make_playoffs(rankings, playoff_schedule(read_schedule(), cfg)[1], cfg)
    pool = players[["name", "pos", "dollars", "league_price", "yahoo_cost", "team", "prod"]]
    missing = sorted(set(sim["keepers"]) - set(pool.name))
    if missing:
        raise SystemExit(f"The rankings do not have these keepers: {', '.join(missing)}. "
                         "Change keepers in [simulation] in config.toml.")

    summary = {}
    for keeper in sim["keepers"]:
        # The same seed for each keeper: each keeper sees the same random numbers, so the comparison is fair
        scores, won = simulate(pool, cfg, keeper, sim["runs"], np.random.default_rng(sim["seed"]), playoffs)
        summary[keeper] = {"cost": round(pool.set_index("name").league_price[keeper]),
                           "dollars": scores.dollars.median(),
                           **dict(zip(["playoff_p10", "playoff_median", "playoff_p90"],
                                      np.percentile(scores.playoff, [10, 50, 90])))}
        print(f"\nKeeper {keeper}: players that you win most often")
        print(won.head(15).round(0).to_string())
    print(f"\nIn {sim['runs']} auctions. dollars: the median sum of your dollars. "
          f"playoff: the playoff score of your core ({sim['core']} players) and your streamers.")
    print(pd.DataFrame(summary).T.round(0).to_string())


if __name__ == "__main__":
    main()
