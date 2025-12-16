from nicegui import ui
import polars as pl

from src.rankings import compute_rankings
from src.config import DEFAULT_WEIGHTS

DATA_PATH = 'data/processed/stats.parquet'

@ui.page('/')
def index():
ui.label('Fantasy Basketball Rankings').classes('text-2xl font-bold')


df = pl.read_parquet(DATA_PATH)
weights = DEFAULT_WEIGHTS.copy()


rankings = compute_rankings(df, weights)


table = ui.table(
columns=[
{'name': 'PLAYER', 'label': 'Player', 'field': 'PLAYER'},
{'name': 'TOTAL_SCORE', 'label': 'Score', 'field': 'TOTAL_SCORE'},
],
rows=rankings.head(100).to_dicts(),
pagination=20,
)


def update():
updated = compute_rankings(df, weights)
table.rows = updated.head(100).to_dicts()


ui.separator()
ui.label('Adjust Category Weights').classes('text-lg font-semibold')


for cat in weights:
ui.slider(
min=0.0,
max=2.0,
step=0.05,
value=weights[cat],
on_change=lambda e, c=cat: (
weights.update({c: e.value}),
update(),
),
).props(f'label="{cat}"')




ui.run()