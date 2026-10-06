"""Tables from the auction simulator runs: the players and the groups of players that go with your titles.

runs has one row for each player that you buy in each auction: keeper, run, player, price, core and title.
core is True for the keeper and the players that you buy for your core (not for your stream spots).
The keeper is in each core, so the tables leave him out. The numbers show what goes with a title.
They do not show that a player causes it: a cheap player also leaves money for the rest of your core.
"""
from itertools import combinations

import numpy as np
import pandas as pd


def player_table(runs, min_pct=3):
    """One row for each keeper and each player in your core in min_pct percent of the auctions or more.

    core_pct: percent of the auctions that the player is in your core.
    min_price, median_price, max_price: the prices that you pay for him in those auctions.
    title_with, title_without: your title percent when the player is in your core, and when he is not.
    lift: title_with - title_without.
    """
    tables = []
    for keeper, data in runs.groupby("keeper"):
        titles = data.groupby("run").title.first()
        core = data[data.core & (data.player != keeper)]
        table = core.groupby("player").agg(n=("run", "nunique"), wins=("title", "sum"), min_price=("price", "min"),
                                           median_price=("price", "median"), max_price=("price", "max"))
        table = table[100 * table.n / len(titles) >= min_pct]
        table["core_pct"] = 100 * table.n / len(titles)
        table["title_with"] = 100 * table.wins / table.n
        table["title_without"] = 100 * (titles.sum() - table.wins) / (len(titles) - table.n)
        table["lift"] = table.title_with - table.title_without
        tables.append(table.reset_index().assign(keeper=keeper))
    cols = ["keeper", "player", "core_pct", "min_price", "median_price", "max_price", "title_with", "title_without", "lift"]
    return pd.concat(tables)[cols].sort_values(["keeper", "core_pct"], ascending=[True, False]).reset_index(drop=True)


def group_table(runs, sizes=(2, 3, 4), min_pct=1):
    """One row for each keeper and each group of players in your core together in min_pct percent of the auctions or more.

    group: the names, joined by " + ". runs: the auctions with the group. title_pct: your title percent in them.
    se: the standard error of title_pct. It adds 1 title and 1 loss, so a group with 100% in a few runs has an
    error above 0. low: title_pct - 2 x se. The table is sorted by low, so a group in few auctions goes down.
    """
    tables = []
    for keeper, data in runs.groupby("keeper"):
        core = data[data.core & (data.player != keeper)]
        n_runs = data.run.nunique()
        counts = {}
        for (_, title), players in core.groupby(["run", "title"]).player:
            for size in sizes:
                for group in combinations(sorted(players), size):
                    n, wins = counts.get(group, (0, 0))
                    counts[group] = (n + 1, wins + title)
        rows = [{"group": " + ".join(g), "size": len(g), "runs": n, "wins": wins}
                for g, (n, wins) in counts.items() if 100 * n / n_runs >= min_pct]
        tables.append(pd.DataFrame(rows, columns=["group", "size", "runs", "wins"]).assign(keeper=keeper))
    table = pd.concat(tables)
    table["title_pct"] = 100 * table.wins / table.runs
    p = (table.wins + 1) / (table.runs + 2)
    table["se"] = 100 * np.sqrt(p * (1 - p) / table.runs)
    table["low"] = table.title_pct - 2 * table.se
    table = table.sort_values(["keeper", "low", "runs", "group"], ascending=[True, False, False, True])
    return table[["keeper", "group", "size", "runs", "title_pct", "se", "low"]].reset_index(drop=True)
