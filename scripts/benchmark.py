"""Category benchmark: the weighted z-scores of a strong team's core, from the auction simulator.

In one auction, the core of a team is its best [simulation] core players by value. The keepers are included.
The benchmark of the run is the per-category mean of the top [category_balance] top_teams teams,
ranked by the total weighted z-score of the core. main() in auction.py averages the runs and the keepers.
"""
import pandas as pd

CATS = ["pts", "reb", "ast", "threes", "stl", "blk"]  # the columns of category_benchmark.csv


def weighted_z(pool, cfg):
    """The wz of each player: z_<cat> x weights[cat]. One row for each pool row, one column for each category."""
    return pd.DataFrame({cat: pool["z_" + cat] * w for cat, w in cfg["weights"].items()}).set_index(pool.name)


def has_z(pool, cfg):
    """True if pool has a z_<cat> column for each category in [weights]."""
    return bool(cfg.get("weights")) and all("z_" + cat in pool.columns for cat in cfg["weights"])


def run_benchmark(sales, pool, cfg):
    """The benchmark of one auction: a Series with the mean wz of the top teams, for each category.

    sales is the result of run_auction. pool needs name, value and z_<cat>.
    A team with fewer players than core uses all its players. A team with no players counts as zeros.
    Teams with the same total keep the order of their team number.
    """
    cats = list(cfg["weights"])
    wz = weighted_z(pool, cfg)
    value = pool.set_index("name").value
    cores = []
    for team in range(cfg["league"]["teams"]):
        best = value[sales.name[sales.team == team]].nlargest(cfg["simulation"]["core"], keep="first").index
        cores.append(wz.loc[best].sum())
    cores = pd.DataFrame(cores, columns=cats)
    top = cores.assign(total=cores.sum(axis=1)).sort_values("total", ascending=False, kind="stable")
    return top[cats].head(cfg["category_balance"]["top_teams"]).mean()
