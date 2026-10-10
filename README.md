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

The scripts count the games that each player's NBA team plays in the fantasy playoff weeks. This data does not change the rankings. The draft board shows it as flags, so you can use it to choose between two players with close values. A player who rests on back-to-backs (`rests_b2b`) does not get the second night of a back-to-back in these counts.

## Pipeline

The scripts run in sequence. The fetch scripts write the files in `data/`. `rankings.py` reads them.
`draft_board.py` calls `build_rankings()` in `rankings.py`. It does not read `rankings.csv`.

```
data/Projections.csv ──┐
ESPN (fetch_data.py) ──┼──> rankings.py ──> output/rankings.csv, output/playoff_schedule.csv
Yahoo (fetch_yahoo.py) ┘        │
                                └──> draft_board.py ──> output/draft_board.html, output/draft_board.md
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
python scripts/publish.py      # Optional. Put the board on GitHub Pages.
python scripts/auction.py      # Optional. Simulate the auction for each keeper candidate.
python scripts/report.py       # Optional. Write the keeper report page from the simulator results.
```

Open `output/draft_board.html` in a browser.

### Publish the board

`publish.py` puts the board on GitHub Pages, so you can open it on a phone during the auction:

```
python scripts/publish.py      # Push output/draft_board.html to the gh-pages branch.
```

The page is at `https://mccomark21.github.io/fantasy-basketball-rankings/`. GitHub can take a few minutes to show a new board.

The published page is public. Anyone with the URL can see it. GitHub Pages has no private sites on this plan.

The script does not change your working tree or your current branch. It replaces the one commit on `gh-pages` each time, so old boards do not stay in the repo.

The first run of `publish.py` makes the `gh-pages` branch. Then tell GitHub to serve that branch:

```
gh api -X POST repos/mccomark21/fantasy-basketball-rankings/pages -f "source[branch]=gh-pages" -f "source[path]=/"
```

## Configuration

All settings are in [`config.toml`](config.toml). To apply a change, run the scripts again.

| Section | Controls |
|---|---|
| `[league]` | League size, roster spots, the position slots, the adds each week, the playoff teams, the projections file and the ESPN season. |
| `[auction]` | The budget, the minimum bid and the bought roster spots for auction dollars. See [Valuation](#valuation). |
| `[weights]` | The weight of each ranked category. See [`docs/category_weights.md`](docs/category_weights.md). |
| `[games]` | The penalty for missed games. See [Valuation](#valuation). |
| `[playoffs]` | The playoff weeks and the value of each week by number of games. |
| `[quality_games]` | The low-volume day limit and the bonus for each quality game. |
| `[board]` | The low-games mark and the tiers in the Markdown board. |
| `[flags]` | The limits that make a draft board flag green, gray, yellow or a red X. |
| `[simulation]` | The auction simulator: the number of runs, the bid noise, the seed, your keeper candidates, your core size and the playoff fit. See [Auction simulator](#auction-simulator). |
| `[risk]` | Injury risk and back-to-back rest. The file for the rankings and the draft board, and for the simulator: the chance of a missed playoff week for each tier and the chance of a rest day. See [Injuries and rest days](#injuries-and-rest-days). |

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
  publish.py              Pushes the draft board to GitHub Pages
  auction.py              Simulates the auction many times for each keeper candidate
  team_score.py           Playoff score of a roster: daily lineups and streamers in weeks 19 to 21
  matchups.py             Playoff face-offs: round robin and bracket of the top teams
  sim_results.py          Player and group tables from the simulator runs
  report.py               Writes output/keeper_report.html from the simulator results
  common.py               Shared helpers: paths, config, playoff week names and names
data/                     Inputs (not tracked by Git)
output/                   Generated files (not tracked by Git)
docs/
  category_weights.md     How the category weights were calculated
tests/                    Tests for valuation.py, identity.py, playoffs.py, draft_board.py, publish.py, auction.py, team_score.py, matchups.py and sim_results.py
```

### Data files

| File | Purpose | Edit by hand |
|---|---|---|
| `data/Projections.csv` | Season projections. Replace the file when projections change. | Yes |
| `data/name_overrides.csv` | Name fixes for players who do not match: the ESPN name (`espn_name`), the Yahoo name (`yahoo_name`) or a fixed team (`team`). | Yes |
| `data/rosters.csv`, `data/schedule.csv` | ESPN data from `fetch_data.py`. | No |
| `data/projection_risk.csv` | Injury risk tier (`inj_risk`) and back-to-back rest (`rests_b2b`) for each player, from the projections page. | Yes |
| `data/yahoo_players.csv` | Yahoo data from `fetch_yahoo.py`. | No |

### Output files

The scripts write these files. Do not edit them.

| File | Contents |
|---|---|
| `output/rankings.csv` | Player rankings. See [rankings.csv](#rankingscsv). |
| `output/playoff_schedule.csv` | Playoff days for each team. See [playoff_schedule.csv](#playoff_schedulecsv). |
| `output/draft_board.html` | The Playoff Draft Board: one sortable table of all players in the projections, with Yahoo positions and S, Q and X flags. Open it in a browser. |
| `output/draft_board.md` | The Playoff Draft Board as Markdown. |
| `output/simulation_summary.csv` | The auction simulator: one row for each keeper (title %, playoff results, playoff score, dollars). |
| `output/simulation_players.csv` | The auction simulator: for each keeper, the players in your core, how often, the lowest, median and highest price that you pay, and the lift (title % with the player − without him). |
| `output/simulation_groups.csv` | The auction simulator: groups of 2 to 4 players in your core, with your title %, its standard error and the low end (title % − 2 × error). |
| `output/keeper_report.html` | The keeper report: title % for each keeper, the top 5 groups of 3 or 4, the best roster with the top group and the players in your core. Open it in a browser. |
| `output/simulation_runs.csv` | The auction simulator: one row for each player that you buy in each auction, with the results of that auction. |

## Common tasks

| Task | Location |
|---|---|
| Change a category weight, the games-played penalty or the playoff weeks | [`config.toml`](config.toml) |
| Change the limits for draft board flags | `[flags]` in [`config.toml`](config.toml) |
| Change how player value is calculated | [`scripts/valuation.py`](scripts/valuation.py) |
| Change a playoff-week rule (week value, quality days, schedule score, short weeks) | [`scripts/playoffs.py`](scripts/playoffs.py) |
| Add a column to the rankings | [`scripts/rankings.py`](scripts/rankings.py) |
| Change the layout or the columns of the draft board | [`scripts/draft_board.py`](scripts/draft_board.py) |
| Publish the board for use on a phone | `python scripts/publish.py`. See [Publish the board](#publish-the-board). |
| Fix a player with no team or no Yahoo data | `data/name_overrides.csv`. See [Players who do not match](#players-who-do-not-match). |
| Read why the weights have their values | [`docs/category_weights.md`](docs/category_weights.md) |
| Find planned work | [GitHub issues](https://github.com/mccomark21/fantasy-basketball-rankings/issues) |

## Methodology

### Valuation

`valuation.py` calculates the value of each player in 4 steps:

1. **Per-game value.** The sum of the weighted per-game z-scores. The player pool is the top 140 players (14 teams × 10 roster spots).
2. **Value above replacement.** The per-game value minus the average of the next 14 players.
3. **Final value.** The value above replacement × (games / 82) ^ `games.power`.
4. **Auction dollars.** The teams buy the top 140 players by final value (14 teams × `auction.spots`). Each bought player gets `auction.min_bid`. The rest of the $2,800 (14 × `auction.budget`) goes to the bought players in proportion to final value above replacement. For dollars, replacement is the first player who is not bought, so the last bought player costs about the minimum bid. All other players get $0.

For a player below replacement level, the final value is the per-game value above replacement. This rule stops missed games from making a below-replacement player look better.

The playoff schedule does not change the final value. The schedule columns and the draft board flags are for information only.

### Auction simulator

`auction.py` runs the 14-team auction `simulation.runs` times for each keeper in `simulation.keepers`. Team 0 is your team. The other 13 teams are bots.

- Bots: a bot's maximum bid starts at `league_price` and moves to `yahoo_cost` as the roster spots fill. Each bid has random noise.
- Your bot: it buys a core of `simulation.core` players (7) and pays $1 for each other spot. You use those spots for streamers. For a core player, it bids your `dollars` × a scale × the playoff fit:
  - The scale moves the money of the stream spots to the core.
  - The fit compares what the player adds to your playoff score with what a player on an average playoff schedule adds. That other player has any position, so a crowded position lowers the fit. The fit goes from 0.5 to 1.5.
- Rules: $200 budget, 10 spots, $1 minimum bid. A maximum bid leaves $1 for each other empty spot. A team bids only if it can still fill PG, SG, SF, PF and C.
- Price: the winner pays the second-highest maximum bid + $1.
- Your keeper costs his `league_price` and takes one spot. The keeper option `"No keeper"` runs the auction with no keeper. The players in `simulation.other_keepers` go to the bot teams at their `league_price` before the auction.

After each auction, the top teams play the playoff weeks head to head. See [Playoff face-offs](#playoff-face-offs).

For each keeper, the output shows your title percent, your face-off results, your playoff score and the median sum of your `dollars`. It also shows the players that you win most often and the median price that you pay for each one.

The auctions run in parallel, one process for each CPU core. Each keeper gets the same random seeds, so the comparison between keepers is fair. 2,000 auctions for each keeper take about 5 minutes on 16 cores.

The simulator writes the `simulation_*.csv` files to `output/`. Run `draft_board.py` after it: the board then shows a **Core combos** tab and a **Lift** column. The tab shows the combos of 3 or 4 with the best low end, for the keeper that you pick, with the playoff games and quality games of each combo. Click a combo to show only its players on the board.

### Playoff score

`team_score.py` scores a roster in weeks 19 to 21:

1. Production: the weighted per-game stats of a player, each divided by the standard deviation of the player pool, × (games / full season).
2. Each day, the best legal lineup of your core starts (PG, SG, SF, PF, C and Util).
3. Streamers fill empty starting slots on busy days. Your stream spots start each week empty, and each new streamer uses one of your 5 adds. A streamer comes from the team with the most games left in the week and stays until the end of the week. There are no adds on quality days.
4. The playoff score is the total production of the starters and the streamers.

### Injuries and rest days

The simulator adds the risk that the value does not show. The settings are in `[risk]`.

The rankings and the draft board use the same file. The schedule columns and the S flag do not count the second nights for a player with `rests_b2b`. The board shows `inj_risk` in the Risk column. Neither changes `value`.

- Back-to-back rest: a player with `rests_b2b` sits on the second night of a back-to-back with the chance `rest_chance` (1.0). The playoff weeks have 19 of these nights, so he misses games that his team plays. The rest days lower his playoff fit, so your bot bids less for him.
- Injuries: in each simulated auction, each player misses each playoff week with the chance of his `inj_risk` tier (`missed_week`). The projected games already hold the average cost of injuries, so the simulator raises his production on the days that he plays by 1 / (1 − chance). His expected production stays the same. The draw changes the spread only: a core of high-risk players loses a whole week more often, and the face-offs show it in the title percent.
- The first tier chances come from the games in `data/Projections.csv`: the share of the season that each tier misses. A player who is not in `data/projection_risk.csv` gets `missing_tier` (med).

### Playoff face-offs

`matchups.py` plays the playoff weeks for each simulated auction:

1. Each team has a core of 7 players and streams the other spots, as you do. A bot's core is its best 7 players by production.
2. The 8 teams with the highest season value of their core make the playoffs (`league.playoff_teams`).
3. Each week, a team's total in each category is its expected total, with the injuries and the rest days of this run, + random noise. The noise treats a total as a random count (variance = mean). Points get twice that variance.
4. A team wins a matchup if it wins more of the 6 categories.
5. Round robin: each week, each pair of playoff teams plays. `rr_win_pct` is your win percent, and a tie counts as half a win.
6. Bracket: 1 v 8, 4 v 5, 2 v 7 and 3 v 6 in week 19, then the semifinals and the final. A tie goes to the higher seed. `title_pct` is the percent of auctions that you win the final.

The bots do not plan for the playoffs, so the title percent is higher than in a real league. Use it to compare keepers, not as a forecast.

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
| `wk19`, `wk20`, `wk21` | Games in each playoff week. A player who rests on back-to-backs does not get the second nights. |
| `playoff_games` | Total games in the playoff weeks. |
| `q_wk19`, `q_wk20`, `q_wk21` | Quality games in each playoff week. |
| `quality_games` | Total quality games in the playoff weeks. |
| `q_season` | Quality games in the full season. |
| `sched_score` | The playoff schedule score of the player's team. For a player who rests on back-to-backs, the score of the games that he plays. |
| `sched_rank` | The rank of that schedule score among the 30 teams. A player who rests on back-to-backs can get 31: his score is below all team scores. |
| `pg_value` | Per-game value. |
| `value` | Final value. |
| `dollars` | Auction dollars. The dollars of all players add up to 14 × $200. |
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

The tests are in `tests/`. They cover `valuation.py`, `identity.py`, `playoffs.py`, two parts of `draft_board.py` (the data load and the filter bar), `publish.py`, `auction.py`, `team_score.py`, `matchups.py` and `sim_results.py`. The `publish.py` tests make temporary Git repos, so they need `git` on the `PATH`.

## Roadmap

Planned work is in [GitHub issues](https://github.com/mccomark21/fantasy-basketball-rankings/issues). The issues include draft board features and refactors from the architecture review. Each issue shows its priority and the issues it depends on.
