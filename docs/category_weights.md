# Category weights

## League settings

- 14 teams, 10 active roster spots, 3 IL spots.
- Head-to-head categories: PTS, REB, AST, 3PM, STL, BLK.
- Punted categories: FG%, FT% and TO. These categories get no weight.

## Weights

| Cat | Weight |
|---|---|
| PTS | 1.00 |
| REB | 1.00 |
| AST | 1.00 |
| 3PM | 0.70 |
| BLK | 0.65 |
| STL | 0.50 |

Multiply the per-game z-score of each category by its weight. Then add the results to get the player value.

## Method

1. Change the totals in `Projections.csv` to per-game values. Points = 2 × FG + 3PM + FT.
2. Calculate z-scores against a pool of the top 140 players (14 × 10).
3. Measure two values for each category:
   - **Waiver availability:** the output of the waiver tier (the 28 players after the rostered pool) as a percentage of the pool average.
   - **Weekly signal-to-noise:** the spread between teams (10 active players, about 3.5 games each) divided by the random weekly noise.
4. Compare each value to the average of PTS, REB and AST. The weight is the geometric mean of the two ratios.
5. Calculate the weights for 14 to 42 players on IL league-wide (1 to 3 per team). Use the average.

## Results

| Cat | Waiver tier, % of pool average (no IL) | Signal-to-noise | Weight, IL 14–42 |
|---|---|---|---|
| PTS | 70% | 1.56 | 1.00 |
| REB | 87% | 2.01 | 1.00 |
| AST | 50% | 1.84 | 1.00 |
| 3PM | 78% | 1.39 | 0.51–0.88 (avg 0.71) |
| STL | 80% | 0.53 | 0.39–0.50 (avg 0.44) |
| BLK | 91% | 1.19 | 0.61–0.69 (avg 0.65) |

- **STL:** weekly noise causes the low weight. Steals are the most random category. The weight is 0.44, rounded up to 0.50 to keep tiebreaker value.
- **BLK:** IL stashes remove streamable bigs from the waiver wire. Thus the BLK weight increases from 0.44 (no IL) to about 0.65.
- **3PM:** the weight changes with IL use because the waiver-tier sample is small. If teams use all 3 IL spots, use about 0.80.
- **3PM, STL and BLK** have almost no correlation with PTS + REB + AST (r ≤ 0.10). A lower weight on these categories does not decrease the value of core stats.

## How to read these tables

- **Weights table:** the final weight for each category. It is the number to multiply by the z-score.
- **Baseline:** PTS, REB and AST are 1.00 by definition. The other categories are compared to their average.
- **Punted categories:** FG%, FT% and TO have no row because they get no weight.
- **Waiver tier, % of pool average:** a high number means the waiver wire has good players in this category. A high number gives a lower weight. **(no IL)** means the calculation assumes no player is on IL.
- **Signal-to-noise:** the spread between teams divided by the random weekly noise. A low number means luck decides the week. A low number gives a lower weight.
- **Weight, IL 14–42:** the range of weights when 14 to 42 players are on IL league-wide (1 to 3 per team). The number in parentheses is the average.
- **How the two values combine:** the weight is the geometric mean of the waiver ratio and the signal-to-noise ratio (Method, step 4).
- **Rounding:** the Weights table uses the Results averages, rounded to 0.05. STL is the exception. Its average is 0.44, and it is raised to 0.50 on purpose to keep tiebreaker value.
- A lower weight means the category counts for less. It does not mean the category does not count.

## Draft notes

- Assists are the scarcest category. Draft them early.
- Rebounds are easy to find on waivers (87% of the pool average). If you stream bigs, a REB weight of 0.85 is also reasonable.
- With equal weights, 3PM, STL and BLK give 44% of the top-50 value. With these weights, they give 29%.
- Players who move up include Sabonis, Towns, Jamal Murray, Trae Young and Booker. Players who move down include Dyson Daniels, Ausar Thompson, Jalen Suggs and Jaren Jackson Jr.

## Limits

- The noise model treats counting stats as random counts and gives points more spread. The order of the categories is reliable. The exact decimals are not.
- The IL model removes the next N players by rank from the waiver tier. It does not model which players get injured.
