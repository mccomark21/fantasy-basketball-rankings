# Fantasy basketball rankings

Custom rankings for a 14-team, 6-category H2H league (punt FG%, FT%, TO).

## Run

```
python scripts/fetch_data.py   # download rosters and schedule (do again after trades)
python scripts/fetch_yahoo.py  # download Yahoo positions, auction prices and ADP
python scripts/rankings.py     # write output/rankings.csv and output/playoff_schedule.csv
python scripts/draft_board.py  # write output/draft_board.md and output/draft_board.html
```

## Files

```
config.toml        settings: weights, games, playoffs, quality games, draft board and flags
scripts/           the scripts above, and common.py (paths, config, playoff-week and position helpers they share)
data/              inputs
output/            made by the scripts; do not edit
docs/              notes
```

| File | Use |
|---|---|
| `config.toml` | All settings. Change a value, then run the scripts again. |
| `data/Projections.csv` | Season projections. Replace this file when projections change. |
| `data/team_overrides.csv` | Name fixes (`espn_name`) or a set team (`team`) for each player. |
| `data/rosters.csv`, `data/schedule.csv` | Downloaded from ESPN by `fetch_data.py`. Do not edit. |
| `data/yahoo_players.csv` | Downloaded from the public Yahoo draft analysis pages by `fetch_yahoo.py`. Do not edit. `rankings.py` uses the positions. |
| `data/yahoo_names.csv` | Yahoo name (`yahoo_name`) for each player whose name is different on Yahoo. |
| `output/rankings.csv` | Player rankings. |
| `output/playoff_schedule.csv` | Playoff days for each team. Q = quality game, x = other game. The number in each column name is the number of NBA games that day. |
| `output/draft_board.html` | Playoff Draft Board: one sortable table of all players in the projections, with Yahoo positions and S, Q and X flags. Open in a browser. |
| `output/draft_board.md` | Playoff Draft Board as Markdown. |
| `docs/category_weights.md` | How the category weights were calculated. |

## Method

1. **Per-game value:** the weighted per-game z-scores. The pool is the top 140 players (14 × 10).
2. **Value above replacement:** per-game value minus the average of the next 14 players.
3. **Final value:** value above replacement × (games / 82) ^ `games.power`.

The playoff schedule does not change the final value. The schedule columns and the draft board flags are for information only.

For a player below replacement level, the final value is the per-game value above replacement. Missed games do not make the player look better.

## Yahoo data

`fetch_yahoo.py` uses Playwright. Install it once: `python -m pip install playwright`, then `python -m playwright install chromium`.
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

## Output columns

- `rank`: final rank. `pg_rank`: rank by per-game value only.
- `pos`: Yahoo positions, for example `PG/SG`. — = not in the Yahoo data.- `wk19`, `wk20`, `wk21`: games in each playoff week. `playoff_games`: total.
- `q_wk19`, `q_wk20`, `q_wk21`: quality games in each playoff week. `quality_games`: total. `q_season`: quality games in the full season.
- `sched_score`, `sched_rank`: playoff schedule score of the team, and its rank from 1 to 30.
- `pg_value`, `value`: per-game value and final value. `z_*`: z-score for each category.

## Schedule score

The schedule score of a team is the average of its playoff week values:

- Week value = `playoffs.week_value` for the number of games + `quality_games.bonus` × quality games that week.
- The average is then divided by the league average, so 1.00 = an average playoff schedule. In 2026-27, the scores are from 0.78 (CLE) to 1.20 (PHX).
- The score does not change the rankings.

`playoff_schedule.csv` shows the score and rank of each team.

## Quality games

A quality game is a game on a low-volume day (`quality_games.max_games_per_day` NBA games or fewer).
If your core players play on these days, you can use your adds (5 each week) on high-volume days, when more free agents play.

## When a player has no team

`rankings.py` prints a list of players with no team. Add each player to `data/team_overrides.csv`:

- Different name on ESPN: put the ESPN name in `espn_name`.
- Free agent or other case: put the team abbreviation in `team` (ESPN style, for example `GS`, `NY`, `SA`).
