# Fantasy basketball rankings

Welcome. This project makes custom player rankings and an auction draft board for one fantasy basketball league for the 2026-27 season.

The league is a Yahoo head-to-head league with 14 teams and a $200 auction draft. It counts 9 categories. Our strategy punts 3 of them: FG%, FT% and TO. Public rankings value all 9 categories, so they do not fit this strategy. These scripts rank players on only the 6 categories that we try to win: PTS, REB, AST, 3PM, BLK and STL.

The scripts also look at the fantasy playoff weeks (weeks 19 to 21). They count the games that each player's team plays in those weeks. This data does not change the rankings. It shows on the draft board as flags, so you can see it when two players are close.

## Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Map of the repo](#map-of-the-repo)
- [Where to make a change](#where-to-make-a-change)
- [Reference](#reference)
  - [Method](#method)
  - [Output columns](#output-columns)
  - [Schedule score](#schedule-score)
  - [Quality games](#quality-games)
  - [Yahoo data](#yahoo-data)
  - [When a player has no team](#when-a-player-has-no-team)
  - [Tests](#tests)

## How it works

The scripts run in a chain. Each script reads the files that the scripts before it wrote.

```
data/Projections.csv ──┐
ESPN (fetch_data.py) ──┼──> rankings.py ──> output/rankings.csv ──> draft_board.py ──> output/draft_board.html
Yahoo (fetch_yahoo.py) ┘                    output/playoff_schedule.csv                 output/draft_board.md
```

1. `fetch_data.py` downloads NBA rosters and the schedule from ESPN.
2. `fetch_yahoo.py` downloads Yahoo positions, auction prices and ADP.
3. `rankings.py` gives each player a value from the projections and `config.toml`. It writes the rankings and the playoff schedule.
4. `draft_board.py` turns the rankings into a sortable draft board for use during the draft.

## Quick start

Requires Python 3.11 or later.

Install the packages once:

```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Put the season projections in `data/Projections.csv`. Git does not track CSV files, so a new copy of the repo does not have this file.

Run the scripts in this order:

```
python scripts/fetch_data.py   # download rosters and schedule (do again after trades)
python scripts/fetch_yahoo.py  # download Yahoo positions, auction prices and ADP
python scripts/rankings.py     # write output/rankings.csv and output/playoff_schedule.csv
python scripts/draft_board.py  # write output/draft_board.md and output/draft_board.html
```

Open `output/draft_board.html` in a browser.

## Map of the repo

### Settings and setup

| File | Use |
|---|---|
| [`config.toml`](config.toml) | All settings: league size, category weights, games played, playoff weeks, quality games, draft board and flags. Change a value, then run the scripts again. |
| [`requirements.txt`](requirements.txt) | Python packages. |

### Scripts

| File | Use |
|---|---|
| [`scripts/fetch_data.py`](scripts/fetch_data.py) | Downloads `data/rosters.csv` and `data/schedule.csv` from ESPN. |
| [`scripts/fetch_yahoo.py`](scripts/fetch_yahoo.py) | Downloads `data/yahoo_players.csv` from the public Yahoo draft analysis pages. |
| [`scripts/rankings.py`](scripts/rankings.py) | Writes `output/rankings.csv` and `output/playoff_schedule.csv`. |
| [`scripts/valuation.py`](scripts/valuation.py) | Calculates the value of each player. `rankings.py` uses it. See [Method](#method). |
| [`scripts/draft_board.py`](scripts/draft_board.py) | Writes `output/draft_board.html` and `output/draft_board.md`. |
| [`scripts/common.py`](scripts/common.py) | Paths, config, playoff-week, position and name helpers that more than one script uses. |

### Data (`data/`)

Git does not track these files.

| File | Use |
|---|---|
| `data/Projections.csv` | Season projections. Replace this file when projections change. |
| `data/team_overrides.csv` | Name fixes (`espn_name`) or a set team (`team`) for each player. See [When a player has no team](#when-a-player-has-no-team). |
| `data/yahoo_names.csv` | Yahoo name (`yahoo_name`) for each player whose name is different on Yahoo. |
| `data/rosters.csv`, `data/schedule.csv` | Downloaded from ESPN by `fetch_data.py`. Do not edit. |
| `data/yahoo_players.csv` | Downloaded from Yahoo by `fetch_yahoo.py`. Do not edit. See [Yahoo data](#yahoo-data). |

### Output (`output/`)

The scripts make these files. Do not edit them. Git does not track them.

| File | Use |
|---|---|
| `output/rankings.csv` | Player rankings. See [Output columns](#output-columns). |
| `output/playoff_schedule.csv` | Playoff days for each team. Q = quality game, x = other game. The number in each column name is the number of NBA games that day. |
| `output/draft_board.html` | Playoff Draft Board: one sortable table of all players in the projections, with Yahoo positions and S, Q and X flags. Open in a browser. |
| `output/draft_board.md` | Playoff Draft Board as Markdown. |

### Docs, tests and notes

| File | Use |
|---|---|
| [`docs/category_weights.md`](docs/category_weights.md) | How the category weights were calculated. |
| [`tests/`](tests/) | Tests for `valuation.py` and `draft_board.py`. See [Tests](#tests). |
| [GitHub issues](https://github.com/mccomark21/fantasy-basketball-rankings/issues) | Planned features for the draft board and refactors from the architecture review. Each issue has its priority and the issues it depends on. |

## Where to make a change

| To do this | Go to |
|---|---|
| Change a category weight, the games-played penalty or the playoff weeks | [`config.toml`](config.toml) |
| Change when a draft board flag is green, gray, yellow or a red X | `[flags]` in [`config.toml`](config.toml) |
| Change how player value is calculated | [`scripts/valuation.py`](scripts/valuation.py) |
| Add a column to the rankings | [`scripts/rankings.py`](scripts/rankings.py) |
| Change the look or the columns of the draft board | [`scripts/draft_board.py`](scripts/draft_board.py) |
| Fix a player with no team | `data/team_overrides.csv` |
| Fix a player with no Yahoo data | `data/yahoo_names.csv` |
| Read why the weights have their values | [`docs/category_weights.md`](docs/category_weights.md) |
| Find the next thing to build | [GitHub issues](https://github.com/mccomark21/fantasy-basketball-rankings/issues) |

## Reference

### Method

1. **Per-game value:** the weighted per-game z-scores. The pool is the top 140 players (14 × 10).
2. **Value above replacement:** per-game value minus the average of the next 14 players.
3. **Final value:** value above replacement × (games / 82) ^ `games.power`.

The playoff schedule does not change the final value. The schedule columns and the draft board flags are for information only.

For a player below replacement level, the final value is the per-game value above replacement. Missed games do not make the player look better.

### Output columns

Columns of `output/rankings.csv`:

- `rank`: final rank. `pg_rank`: rank by per-game value only.
- `pos`: Yahoo positions, for example `PG/SG`. — = not in the Yahoo data.
- `wk19`, `wk20`, `wk21`: games in each playoff week. `playoff_games`: total.
- `q_wk19`, `q_wk20`, `q_wk21`: quality games in each playoff week. `quality_games`: total. `q_season`: quality games in the full season.
- `sched_score`, `sched_rank`: playoff schedule score of the team, and its rank from 1 to 30.
- `pg_value`, `value`: per-game value and final value. `z_*`: z-score for each category.

### Schedule score

The schedule score of a team is the average of its playoff week values:

- Week value = `playoffs.week_value` for the number of games + `quality_games.bonus` × quality games that week.
- The average is then divided by the league average, so 1.00 = an average playoff schedule. In 2026-27, the scores are from 0.78 (CLE) to 1.20 (PHX).
- The score does not change the rankings.

`playoff_schedule.csv` shows the score and rank of each team.

### Quality games

A quality game is a game on a low-volume day (`quality_games.max_games_per_day` NBA games or fewer).
If your core players play on these days, you can use your adds (5 each week) on high-volume days, when more free agents play.

### Yahoo data

`fetch_yahoo.py` uses Playwright. `requirements.txt` installs it. The Chromium step in [Quick start](#quick-start) installs the browser.
On this PC, `greenlet` 3.5 is blocked by Windows Application Control. Use `python -m pip install greenlet==3.1.1`.

The data comes from all Yahoo leagues, not only our league. Our league pages need a Yahoo login, so the script does not read them.

Columns of `yahoo_players.csv`:

- `yahoo_id`, `name`, `team`: Yahoo player ID, name and team (Yahoo abbreviations, for example `NYK`, `GSW`, `SAS`).
- `positions`: Yahoo positions, for example `PG,SG`.
- `status`: injury status (`Q`, `O`, `P`, `NA`). Empty = healthy.
- `yahoo_rank`: Yahoo preseason rank.
- `pct_drafted`: percent of Yahoo auction drafts that took the player.
- `yahoo_cost`: average price in Yahoo auction drafts ($200 budget).
- `yahoo_value`: Yahoo projected auction value.
- `adp`: average pick in Yahoo snake drafts. Empty when the player has no ADP.

Some names are different on Yahoo, for example Alex Sarr, Nic Claxton, Cameron Johnson, Herbert Jones and Luguentz Dort.
`draft_board.py` matches names without accents, punctuation or suffixes (Jr., III). For other differences, add the player to `data/yahoo_names.csv`.

### When a player has no team

`rankings.py` prints a list of players with no team. Add each player to `data/team_overrides.csv`:

- Different name on ESPN: put the ESPN name in `espn_name`.
- Free agent or other case: put the team abbreviation in `team` (ESPN style, for example `GS`, `NY`, `SA`).

### Tests

```
python -m pytest
```

The tests are in `tests/`. They cover `valuation.py` and the filter bar of `draft_board.py`.
