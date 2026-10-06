"""Auction simulator: run this league's auction many times. Team 0 is your team. Teams 1 to teams - 1 are bots.

One auction:
  1. Nominations go in league_price order, with random noise.
  2. Each bot's maximum bid starts at league_price and moves to yahoo_cost as the roster spots fill
     (the room cools). Each bot multiplies it by its own random noise.
  3. Your maximum bid is your dollar value (dollars).
  4. A team bids only if the player leaves room to fill the position slots (config.toml [league] slots).
     Util and bench take any player.
  5. A maximum bid is at least min_bid and at most money left - min_bid x (empty spots - 1).
  6. The highest maximum bid wins. The winner pays the second-highest maximum bid + $1,
     but not more than his own maximum bid. Ties go to a random team.
Team score: the sum of your dollar values for your players. It does not use the playoff schedule yet.
Output: for each keeper in config.toml [simulation], the range of your team score and the players that you win most.
"""
import numpy as np
import pandas as pd

from common import load_config
from rankings import build_rankings


def run_auction(pool, cfg, rng, keeper=None):
    """One auction. Returns one row for each player sold: name, team and price.

    pool needs name, pos, dollars, league_price and yahoo_cost. A missing price is $0.
    keeper is the name of your keeper. He is the first row, and his price is league_price (rounded).
    """
    teams, a = cfg["league"]["teams"], cfg["auction"]
    noise = cfg["simulation"]["noise"]
    min_bid, slots = a["min_bid"], cfg["league"]["slots"]
    pool = pool.assign(league_price=pool.league_price.fillna(0), yahoo_cost=pool.yahoo_cost.fillna(0),
                       pos=pool.pos.str.split("/").map(set))
    money = np.full(teams, a["budget"])
    spots = np.full(teams, a["spots"])
    rosters = [[] for _ in range(teams)]
    total = spots.sum()
    sales = []
    if keeper is not None:
        kept = pool.set_index("name").loc[keeper]
        price = round(kept.league_price)
        rosters[0].append(kept.pos)
        money[0] -= price
        spots[0] -= 1
        sales.append((keeper, 0, price))
        pool = pool[pool.name != keeper]

    order = pool.league_price.clip(lower=min_bid) * rng.lognormal(0, noise, len(pool))
    for p in pool.loc[order.sort_values(ascending=False, kind="stable").index].itertuples():
        if spots.sum() == 0:
            break
        fits = np.array([_fits(rosters[t], spots[t], p.pos, slots) for t in range(teams)])
        if not fits.any():
            continue
        cooled = 1 - spots.sum() / total
        bids = ((1 - cooled) * p.league_price + cooled * p.yahoo_cost) * rng.lognormal(0, noise, teams)
        bids[0] = p.dollars
        limit = money - min_bid * (spots - 1)
        bids = np.where(fits, np.clip(np.floor(bids), min_bid, limit), 0)
        top = np.flatnonzero(bids == bids.max())
        win = rng.choice(top)
        price = bids[win] if len(top) > 1 else np.sort(bids)[-2] + 1
        money[win] -= price
        spots[win] -= 1
        rosters[win].append(p.pos)
        sales.append((p.name, win, price))
    return pd.DataFrame(sales, columns=["name", "team", "price"])


def _fits(roster, spots, pos, slots):
    """True if a team with this roster (a list of position sets) and empty spots can add a player with pos."""
    return spots > 0 and _open_slots(roster + [pos], slots) <= spots - 1


def _open_slots(roster, slots):
    """Number of slots that the roster cannot fill. Each player fills one slot (bipartite matching)."""
    holder = {}

    def place(player, tried):
        for slot in slots:
            if slot in roster[player] and slot not in tried:
                tried.add(slot)
                if slot not in holder or place(holder[slot], tried):
                    holder[slot] = player
                    return True
        return False

    for player in range(len(roster)):
        place(player, set())
    return len(slots) - len(holder)


def simulate(pool, cfg, keeper, runs, rng):
    """Run the auction runs times. Returns (scores, won).

    scores: your team score in each run, as an array. The score is the sum of dollars of your players.
    won: one row for each player that you win (not the keeper), most often first.
         win_pct is the percent of runs that you win him. price is the median price that you pay.
    """
    dollars = pool.set_index("name").dollars
    scores, sales = [], []
    for _ in range(runs):
        mine = run_auction(pool, cfg, rng, keeper).query("team == 0")
        scores.append(dollars[mine.name].sum())
        sales.append(mine[mine.name != keeper])
    won = pd.concat(sales).groupby("name").price.agg(win_pct="size", price="median")
    won["win_pct"] = 100 * won.win_pct / runs
    return np.array(scores), won.sort_values("win_pct", ascending=False)


def main():
    cfg = load_config()
    sim = cfg["simulation"]
    pool = build_rankings(cfg)[["name", "pos", "dollars", "league_price", "yahoo_cost"]]
    missing = sorted(set(sim["keepers"]) - set(pool.name))
    if missing:
        raise SystemExit(f"The rankings do not have these keepers: {', '.join(missing)}. "
                         "Change keepers in [simulation] in config.toml.")

    summary = {}
    for keeper in sim["keepers"]:
        # The same seed for each keeper: each keeper sees the same random numbers, so the comparison is fair
        scores, won = simulate(pool, cfg, keeper, sim["runs"], np.random.default_rng(sim["seed"]))
        summary[keeper] = {"cost": round(pool.set_index("name").league_price[keeper]),
                           **dict(zip(["p10", "median", "p90"], np.percentile(scores, [10, 50, 90]))),
                           "mean": scores.mean()}
        print(f"\nKeeper {keeper}: players that you win most often")
        print(won.head(15).round(0).to_string())
    print(f"\nTeam score (sum of your dollars for {cfg['auction']['spots']} players) in {sim['runs']} auctions:")
    print(pd.DataFrame(summary).T.round(0).to_string())


if __name__ == "__main__":
    main()
