"""Page data for the category balance panel (#39 Contracts): wz for each player, the filler curve and the benchmark.

  wz: the weighted z-score of a player in one category: z_<cat> x weights[cat].
  filler_curve: for each price, the mean wz of the players whose dollars are closest to that price.
  benchmark: the file output/category_benchmark.csv (scripts/benchmark.py writes it).
"""
import pandas as pd

from common import OUT

BENCHMARK_FILE = OUT / "category_benchmark.csv"
MAX_PRICE = 60         # the last price of the filler curve
FILLER_PLAYERS = 5     # players in the mean for each price
FILLER_MAX_RANK = 140  # a player with a larger rank number is not a filler


def load_benchmark(path=BENCHMARK_FILE):
    """The benchmark as a dict of category -> weighted z-score sum, or None when the file is missing."""
    if not path.exists():
        return None
    row = pd.read_csv(path).iloc[0]
    return {cat: round(float(value), 3) for cat, value in row.items()}


def category_data(df, cfg, benchmark):
    """(category, wz): the "category" object of the page data and the wz of each player.

    df: the rankings, with rank, dollars and z_<cat> columns. benchmark: load_benchmark().
    wz is a list of dicts in the order of df. Without a benchmark, both values are None.
    """
    if benchmark is None:
        return None, None
    cats, weights = list(benchmark), cfg["weights"]
    if set(cats) != set(weights):
        raise ValueError(f"The benchmark has the categories {cats}. The weights have {list(weights)}.")
    wz = pd.DataFrame({cat: df["z_" + cat] * weights[cat] for cat in cats})
    category = {"cats": cats, "benchmark": {cat: round(float(benchmark[cat]), 3) for cat in cats},
                "core_size": cfg["simulation"]["core"], "min_bid": cfg["auction"]["min_bid"],
                "band": cfg.get("category_balance", {}).get("band", 0.5),
                "filler_curve": filler_curve(df, wz, cfg["auction"]["min_bid"])}
    return category, [{cat: round(float(v), 3) for cat, v in row.items()} for _, row in wz.iterrows()]


def filler_curve(df, wz, min_bid):
    """One entry for each price from min_bid to MAX_PRICE: the mean wz of the players with the closest dollars.

    Only the players with rank <= FILLER_MAX_RANK count. A tie in distance goes to the player with the better rank.
    """
    fillers = df[df["rank"] <= FILLER_MAX_RANK].sort_values("rank")
    dollars = fillers.dollars.to_numpy()
    curve = []
    for price in range(min_bid, MAX_PRICE + 1):
        nearest = abs(dollars - price).argsort(kind="stable")[:FILLER_PLAYERS]
        mean = wz.loc[fillers.index[nearest]].mean()
        curve.append({"price": price, "wz": {cat: round(float(v), 3) for cat, v in mean.items()}})
    return curve
