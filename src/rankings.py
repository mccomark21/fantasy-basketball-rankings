import polars as pl
from src.config import DEFAULT_WEIGHTS




def add_z_scores(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
# Add z-score columns for the provided stats.
return df.with_columns([
((pl.col(c) - pl.col(c).mean()) / pl.col(c).std())
.alias(f'{c}_Z')
for c in columns
])




def compute_rankings(
stats_df: pl.DataFrame,
weights: dict = DEFAULT_WEIGHTS,
) -> pl.DataFrame:
# Compute weighted fantasy rankings.
# Assumes percentage stats have already been converted to volume-based
# impact metrics (FG_IMPACT, FT_IMPACT).


df = add_z_scores(stats_df, list(weights.keys()))


df = df.with_columns([
(pl.col(f'{cat}_Z') * weight).alias(f'{cat}_WZ')
for cat, weight in weights.items()
])


df = df.with_columns(
pl.sum_horizontal(
[pl.col(c) for c in df.columns if c.endswith('_WZ')]
).alias('TOTAL_SCORE')
)


return df.sort('TOTAL_SCORE', descending=True)