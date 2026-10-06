# Fantasy Basketball Rankings

Custom player rankings and an auction draft board for one Yahoo fantasy basketball league, 2026-27 season.

Public rankings value all 9 categories. This league's strategy punts 3 of them, so public rankings do not fit it. These scripts rank players on only the 6 categories that the strategy tries to win.

## Table of contents

- [Overview](#overview)
- [Pipeline](#pipeline)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Common tasks](#common-tasks)
- [Methodology](#methodology)
- [Output reference](#output-reference)
- [Data maintenance](#data-maintenance)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Roadmap](#roadmap)

## Overview

### League format

| Setting | Value |
|---|---|
| Platform | Yahoo, head-to-head |
| Teams | 14 |
| Draft | Auction, $200 budget |
| Categories | 9 |
| Punted categories | FG%, FT%, TO |
| Ranked categories | PTS, REB, AST, 3PM, BLK, STL |
| Fantasy playoffs | Weeks 19 to 21 |

### Playoff schedule

The scripts count the games that each player's NBA team plays in the fantasy playoff weeks. This data does not change the rankings. The draft board shows it as flags, so you can use it to choose between two players with close values.

## Pipeline

The scripts run in sequence. Each script reads the files that the earlier scripts wrote.

```
data/Projections.csv ──┐
ESPN (fetch_data.py) ──┼──> rankings.py ──> output/rankings.csv ──> draft_board.py ──> output/draft_board.html
Yahoo (fetch_yahoo.py) ┘                    output/playoff_schedule.csv                 output/draft_board.md
```

| Step | Script | Result |
|---|---|---|
| 1 | `fetch_data.py` | Downloads NBA rosters and the schedule from ESPN. |
| 2 | `fetch_yahoo.py` | Downloads Yahoo positions, auction prices and ADP. |
| 3 | `rankings.py` | Gives each player a value from the projections and `config.toml`. Writes the rankings and the playoff schedule. |
| 4 | `draft_board.py` | Turns the rankings and the playoff schedule into a sortable draft board for use during the draft. |

## Getting started

### Prerequisites

- Python 3.11 or later. The scripts use `tomllib`.
- A season projections file. Git does not track CSV files, so a new clone of the repo does not include it.

### Installation

1. Install the Python packages:

   ```
   python -m pip install -r requirements.txt
   ```

2. Install the browser that `fetch_yahoo.py` uses:

   ```
   python -m playwright install chromium
   ```

3. Put the season projections in `data/Projections.csv`.

### Usage

Run the scripts in this order:

```
python scripts/fetch_data.py   # Download rosters and schedule. Run again after trades.
python scripts/fetch_yahoo.py  # Download Yahoo positions, auction prices and ADP.
python scripts/rankings.py     # Write output/rankings.csv and output/playoff_schedule.csv.
python scripts/draft_board.py  # Write output/draft_board.md and output/draft_board.html.
```

Open `output/draft_board.html` in a browser.

## Configuration

All settings are in [`config.toml`](config.toml). To apply a change, run the scripts again.

| Section | Controls |
|---|---|
| `[league]` | League size, roster spots, the projections file and the ESPN season. |
| `[weights]` | The weight of each ranked category. See [`docs/category_weights.md`](docs/category_weights.md). |
| `[games]` | The penalty for missed games. See [Valuation](#valuation). |
| `[playoffs]` | The playoff weeks and the value of each week by number of games. |
| `[quality_games]` | The low-volume day limit and the bonus for each quality game. |
| `[board]` | The low-games mark and the tiers in the Markdown board. |
| `[flags]` | The limits that make a draft board flag green, gray, yellow or a red X. |

## Project structure

```
config.toml               All settings
requirements.txt          Python packages
scripts/
  fetch_data.py           Downloads data/rosters.csv and data/schedule.csv from ESPN
  fetch_yahoo.py          Downloads data/yahoo_players.csv from the public Yahoo draft analysis pages
  rankings.py             Writes output/rankings.csv and output/playoff_schedule.csv
  valuation.py            Calculates the value of each player (used by rankings.py)
  identity.py             Links each player to an ESPN team and a Yahoo row (used by rankings.py)
  playoffs.py             Playoff-week rules: games, quality games, schedule score, short weeks
  draft_board.py          Writes output/draft_board.html and output/draft_board.md
  common.py               Shared helpers: paths, config, playoff week names and names
data/                     Inputs (not tracked by Git)
output/                   Generated files (not tracked by Git)
docs/
  category_weights.md     How the category weights were calculated
tests/                    Tests for valuation.py, identity.py, playoffs.py and draft_board.py
```

### Data files

| File | Purpose | Edit by hand |
|---|---|---|
| `data/Projections.csv` | Season projections. Replace the file when projections change. | Yes |
| `data/name_overrides.csv` | Name fixes for players who do not match: the ESPN name (`espn_name`), the Yahoo name (`yahoo_name`) or a fixed team (`team`). | Yes |
| `data/rosters.csv`, `data/schedule.csv` | ESPN data from `fetch_data.py`. | No |
| `data/yahoo_players.csv` | Yahoo data from `fetch_yahoo.py`. | No |

### Output files

The scripts write these files. Do not edit them.

| File | Contents |
|---|---|
| `output/rankings.csv` | Player rankings. See [rankings.csv](#rankingscsv). |
| `output/playoff_schedule.csv` | Playoff days for each team. See [playoff_schedule.csv](#playoff_schedulecsv). |
| `output/draft_board.html` | The Playoff Draft Board: one sortable table of all players in the projections, with Yahoo positions and S, Q and X flags. Open it in a browser. |
| `output/draft_board.md` | The Playoff Draft Board as Markdown. |

## Common tasks

| Task | Location |
|---|---|
| Change a category weight, the games-played penalty or the playoff weeks | [`config.toml`](config.toml) |
| Change the limits for draft board flags | `[flags]` in [`config.toml`](config.toml) |
| Change how player value is calculated | [`scripts/valuation.py`](scripts/valuation.py) |
| Change a playoff-week rule (week value, quality days, schedule score, short weeks) | [`scripts/playoffs.py`](scripts/playoffs.py) |
| Add a column to the rankings | [`scripts/rankings.py`](scripts/rankings.py) |
| Change the layout or the columns of the draft board | [`scripts/draft_board.py`](scripts/draft_board.py) |
| Fix a player with no team or no Yahoo data | `data/name_overrides.csv`. See [Players who do not match](#players-who-do-not-match). |
| Read why the weights have their values | [`docs/category_weights.md`](docs/category_weights.md) |
| Find planned work | [GitHub issues](https://github.com/mccomark21/fantasy-basketball-rankings/issues) |

## Methodology

### Valuation

`valuation.py` calculates the value of each player in 3 steps:

1. **Per-game value.** The sum of the weighted per-game z-scores. The player pool is the top 140 players (14 teams × 10 roster spots).
2. **Value above replacement.** The per-game value minus the average of the next 14 players.
3. **Final value.** The value above replacement × (games / 82) ^ `games.power`.

For a player below replacement level, the final value is the per-game value above replacement. This rule stops missed games from making a below-replacement player look better.

The playoff schedule does not change the final value. The schedule columns and the draft board flags are for information only.

### Schedule score

The schedule score of a team is the average of its playoff week values.

- Week value = `playoffs.week_value` for the number of games + `quality_games.bonus` × the number of quality games in that week.
- The scripts divide the average by the league average, so 1.00 is an average playoff schedule.
- In 2026-27, the scores go from 0.78 (CLE) to 1.20 (PHX).

The score does not change the rankings.

### Quality games

A quality game is a game on a low-volume day. A low-volume day has `quality_games.max_games_per_day` NBA games or fewer.

If your core players play on low-volume days, you can use your adds (5 each week) on high-volume days, when more free agents play.

## Output reference

### rankings.csv

| Column | Description |
|---|---|
| `rank` | Final rank. |
| `pg_rank` | Rank by per-game value only. |
| `pos` | Yahoo positions, for example `PG/SG`. `—` means the player is not in the Yahoo data. |
| `wk19`, `wk20`, `wk21` | Games in each playoff week. |
| `playoff_games` | Total games in the playoff weeks. |
| `q_wk19`, `q_wk20`, `q_wk21` | Quality games in each playoff week. |
| `quality_games` | Total quality games in the playoff weeks. |
| `q_season` | Quality games in the full season. |
| `sched_score` | The playoff schedule score of the player's team. |
| `sched_rank` | The rank of that schedule score, from 1 to 30. |
| `pg_value` | Per-game value. |
| `value` | Final value. |
| `z_*` | The z-score for each category. |

### playoff_schedule.csv

Each row is a team. Each day column shows `Q` for a quality game and `x` for a different game. The number in each column name is the number of NBA games on that day. The file also shows the schedule score and rank of each team.

### yahoo_players.csv

The data comes from all Yahoo leagues, not only this league. The league's own pages need a Yahoo login, so the script does not read them.

| Column | Description |
|---|---|
| `yahoo_id` | Yahoo player ID. |
| `name` | Player name. |
| `team` | Team, as a Yahoo abbreviation, for example `NYK`, `GSW`, `SAS`. |
| `positions` | Yahoo positions, for example `PG,SG`. |
| `status` | Injury status: `Q`, `O`, `P` or `NA`. Empty means healthy. |
| `yahoo_rank` | Yahoo preseason rank. |
| `pct_drafted` | Percent of Yahoo auction drafts that took the player. |
| `yahoo_cost` | Average price in Yahoo auction drafts ($200 budget). |
| `yahoo_value` | Yahoo projected auction value. |
| `adp` | Average pick in Yahoo snake drafts. Empty when the player has no ADP. |

## Data maintenance

### Players who do not match

`rankings.py` matches each projection name to the ESPN rosters and the Yahoo data. The match ignores accents, punctuation and suffixes such as Jr. and III.

For players in the top 190 (the player pool plus 50), `rankings.py` prints each player with no team and each player with no Yahoo data. Add each player to `data/name_overrides.csv` and fill only the cells that you need:

- `espn_name`: the name on ESPN, if it is different.
- `yahoo_name`: the name on Yahoo, if it is different. Examples: Alex Sarr, Nic Claxton, Cameron Johnson, Herbert Jones and Luguentz Dort.
- `team`: the team abbreviation for a free agent or a different case. Use ESPN abbreviations, for example `GS`, `NY`, `SA`. This value replaces the ESPN team.

A player outside the Yahoo top 500 has no Yahoo data. This is expected.

## Troubleshooting

### greenlet is blocked on Windows

`fetch_yahoo.py` uses Playwright, which needs `greenlet`. On the development PC, Windows Application Control blocks `greenlet` 3.5. Install an earlier version:

```
python -m pip install greenlet==3.1.1
```

## Testing

```
python -m pytest
```

The tests are in `tests/`. They cover `valuation.py`, `identity.py`, `playoffs.py` and the filter bar of `draft_board.py`.

## Roadmap

Planned work is in [GitHub issues](https://github.com/mccomark21/fantasy-basketball-rankings/issues). The issues include draft board features and refactors from the architecture review. Each issue shows its priority and the issues it depends on.
