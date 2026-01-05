from pathlib import Path
import polars as pl


DATA_PATH = Path('data/processed/stats.parquet')




def ingest() -> None:
# Ingest raw player stats and write to Parquet.


# This is intentionally simple to unblock the rest of the app.


# TODO: Replace with nba_api pull
    df = pl.read_csv('data/raw/example_stats.csv')


DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
df.write_parquet(DATA_PATH)




if __name__ == '__main__':
    ingest()