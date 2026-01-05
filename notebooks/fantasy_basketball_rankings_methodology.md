# Executive Summary

This project builds an **explainable, data-driven ranking model** using professional basketball statistics as the domain.

I am a long-time basketball fan and regularly play fantasy basketball with friends. Because fantasy basketball involves evaluating players across many dimensions — scoring, efficiency, versatility, and consistency — it naturally mirrors many real-world ranking and decision problems.

Given both my personal interest in the sport and the public availability of high-quality basketball data, this made for a logical and engaging portfolio project.

From a technical perspective, this work demonstrates:
- Feature normalization across heterogeneous metrics
- Outlier control and stability considerations
- Weighted composite scoring
- Bias mitigation (over-penalizing weaknesses, over-rewarding single strengths)
- Transparent, explainable modeling decisions

While fantasy basketball is the application, the underlying techniques are broadly applicable to problems such as:
- Performance evaluation
- Candidate ranking
- Risk and scoring models
- Recommendation systems

The sections below explain **what the model does**, **why each step exists**, and **how it is implemented**, assuming no prior knowledge of fantasy basketball.

---

# Fantasy Basketball Rankings — An Explainable Scoring Model

This document explains **what this project does**, **why each decision was made**, and **how the scoring model works**, even if you are **not familiar with fantasy basketball**.

Think of this system as a **general-purpose player evaluation model**:
- Many metrics
- Different scales
- Some metrics are noisier than others
- We want a **fair, explainable composite score**

Fantasy basketball is simply the use case.

---

## 1. What Problem Are We Solving?

If we want to rank players, we immediately run into three challenges:

1. Players contribute in **many different ways**
2. Metrics are on **different scales** (points vs percentages vs counts)
3. A single extreme value can **distort rankings**

This project builds a ranking system that:
- Combines many metrics into **one score**
- Avoids over-penalizing a single weakness
- Avoids over-rewarding a single strength
- Remains **transparent and tunable**

These challenges appear in **many domains** beyond sports:
- Risk scoring models
- Product evaluation
- Recommendation systems

---

## 2. Data Quality Filters (Minimum Games & Minutes)

Before any normalization or scoring occurs, the dataset is filtered to include only players with a **meaningful sample size**.

### Why this matters

Public sports datasets often include players who:
- Appeared in only a handful of games
- Played very limited minutes
- Have statistics that are not representative of sustained performance

Including these players can introduce noise and distort averages, standard deviations, and rankings.

This concern generalizes well beyond sports:
- Short-tenure employees
- One-off transactions
- Sparse observations in time-series data

Filtering ensures the model evaluates **reliable performance**, not statistical artifacts.

---

### Minimum Thresholds

Two filters are applied:

1. **Minimum games played** — ensures sufficient observations
2. **Minimum minutes per game** — ensures meaningful on-court contribution

Example thresholds:

```python
MIN_GAMES_PLAYED = 20
MIN_MINUTES_PER_GAME = 20
```

These values are tunable and depend on the evaluation context.

---

### Implementation

```python
df = df.with_columns([
    (pl.col("Min") / pl.col("Games")).alias("Min_pg")
])

# Apply data quality filters
df = df.filter(
    (pl.col("Games") >= MIN_GAMES_PLAYED) &
    (pl.col("Min_pg") >= MIN_MINUTES_PER_GAME)
)
```

Only after this filtering step do we proceed with normalization and scoring.

---

## 3. Normalizing Metrics with Z-Scores

Different statistics have different units:
- Points per game
- Assists per game
- Shooting percentages

To combine them fairly, we **standardize** each metric using a z-score.

### Z-Score Formula

```
z = (value − average) / standard deviation
```

### Intuition

| Z-Score | Meaning |
|--------|--------|
| 0 | Exactly average |
| +1 | One standard deviation above average |
| −1 | One standard deviation below average |

After this step:
- Every metric lives on the **same scale**
- Positive = better than average
- Negative = worse than average

---

## 3. Per-Game Normalization (Fair Comparisons)

Before combining any metrics, all raw statistics are converted to **per-game values**.

### Why this matters

Players do not all have the same availability:
- Different numbers of games played
- Different minutes per game
- Injuries or load management

Using raw totals would unfairly favor players who simply played more.

By normalizing **per game**, the model evaluates *quality of contribution*, not durability.

### Example

```python
df = df.with_columns([
    (pl.col("PTS") / pl.col("Games")).alias("PTS_pg"),
    (pl.col("REB") / pl.col("Games")).alias("REB_pg"),
    (pl.col("AST") / pl.col("Games")).alias("AST_pg"),
    (pl.col("STL") / pl.col("Games")).alias("STL_pg"),
    (pl.col("BLK") / pl.col("Games")).alias("BLK_pg"),
])
```

This step ensures players are compared on equal footing.

---

## 4. Outlier Control with Winsorization

Some metrics naturally contain **extreme values**:
- Steals
- Blocks
- Low-volume shooting percentages

Extreme outliers can distort averages and standard deviations, which then distort z-scores.

### Winsorization

Winsorization caps extreme values at chosen percentiles (e.g. 5th and 95th) while preserving rank order.

> The goal is **stability**, not removing information.

### Implementation (Selective)

```python
def winsorize(col: str, lower=0.05, upper=0.95):
    return (
        pl.when(pl.col(col) < pl.col(col).quantile(lower))
          .then(pl.col(col).quantile(lower))
        .when(pl.col(col) > pl.col(col).quantile(upper))
          .then(pl.col(col).quantile(upper))
        .otherwise(pl.col(col))
        .alias(col)
    )
```

Applied only to metrics known to be volatile:

```python
OUTLIER_SENSITIVE = [
    "STL_pg",
    "BLK_pg",
    "FG_Impact_pg",
    "FT_Impact_pg",
]

df = df.with_columns([
    winsorize(col) for col in OUTLIER_SENSITIVE
])
```

---

## 5. Handling Percentage-Based Metrics

Some metrics represent **efficiency**, not volume (e.g. shooting accuracy).

### Why This Is Tricky

- A small number of attempts can produce extreme percentages
- Percentage metrics can dominate rankings if untreated

### Solution: Volume-Adjusted Impact + Weighting

We:
1. Convert percentages into **impact values** using attempt volume
2. Explicitly reduce their influence using weights

```python
CATEGORY_WEIGHTS = {
    "z_PTS_pg": 1.00,
    "z_Threes_pg": 1.00,
    "z_REB_pg": 1.00,
    "z_AST_pg": 1.00,
    "z_STL_pg": 0.95,
    "z_BLK_pg": 0.95,
    "z_FG_Impact_pg": 0.65,
    "z_FT_Impact_pg": 0.65,
}
```

This ensures efficiency matters — but does not overwhelm the model.

---

## 4. Creating a Base Composite Score

Each player's initial score is a **weighted sum of standardized metrics**.

```python
import polars as pl

weighted_sum = sum(
    pl.col(metric) * weight
    for metric, weight in CATEGORY_WEIGHTS.items()
)

df = df.with_columns(
    weighted_sum.alias("Weighted_Z_Score")
)
```

At this stage, the score represents **overall statistical contribution**.

---

## 5. Removing the Single Worst Metric

### Why?

Real-world performance evaluation should not be dominated by one flaw.

This idea comes from professional fantasy analysts but applies broadly:
- Strong candidates often have one weaker area
- That weakness should not invalidate the whole profile

### Implementation

For each player:
1. Identify the worst contributing metric
2. Remove it from the total score

```python
weighted_metrics = [
    pl.col(metric) * weight
    for metric, weight in CATEGORY_WEIGHTS.items()
]

df = df.with_columns(
    pl.concat_list(weighted_metrics)
      .list.min()
      .alias("Worst_Category_Value")
)

df = df.with_columns(
    (pl.col("Weighted_Z_Score") - pl.col("Worst_Category_Value"))
    .alias("Adjusted_Z_Score")
)
```

This produces a score that reflects **typical performance**, not edge-case weaknesses.

---

## 6. Detecting Over-Reliance on a Single Strength

### The Problem

Some players rank highly because of **one extreme metric**, while being average elsewhere.

This is undesirable in many ranking systems:
- A single spike should not outweigh broad competence

---

## 7. Measuring Metric Concentration

We measure how much of a player’s total value comes from their **best metric**.

```python
df = df.with_columns(
    pl.concat_list(weighted_metrics).alias("Weighted_List")
)

df = df.with_columns(
    pl.col("Weighted_List").list.max().alias("Best_Category_Value"),
    pl.col("Weighted_List").list.sum().alias("Total_Contribution")
)

df = df.with_columns(
    (pl.col("Best_Category_Value") / pl.col("Total_Contribution"))
    .alias("Metric_Dependency")
)
```

### Interpretation

| Dependency Ratio | Interpretation |
|------------------|----------------|
| < 0.30 | Well-balanced |
| 0.30–0.40 | Mild skew |
| > 0.40 | Heavily concentrated |

---

## 8. Applying a Soft Penalty

Instead of hard rules, we apply a **gradual penalty** only when dependency is high.

```python
df = df.with_columns(
    pl.when(pl.col("Metric_Dependency") > 0.40)
      .then((pl.col("Metric_Dependency") - 0.40) * 1.5)
      .otherwise(0)
      .alias("Dependency_Penalty")
)
```

Balanced profiles are unaffected.
Highly skewed profiles are gently adjusted downward.

---

## 9. Final Scoring Formula

```python
df = df.with_columns(
    (pl.col("Adjusted_Z_Score") - pl.col("Dependency_Penalty"))
    .alias("Final_Fantasy_Score")
)
```

### In Plain English

```
Final Score =
  weighted average performance
- worst individual weakness
- penalty for over-reliance on one metric
```

---

## 10. Ranking Output

```python
df = (
    df.sort("Final_Fantasy_Score", descending=True)
      .with_row_index(name="Rank", offset=1)
)
```

The result is a **clear, defensible leaderboard**.

---

## 11. Why This Model Is Useful Beyond Sports

This system demonstrates:
- Feature normalization
- Weighted scoring models
- Outlier handling
- Explainability
- Domain-driven constraints

It can be adapted to:
- Hiring scorecards
- Credit / risk models
- Product comparisons
- Performance dashboards

---

## 12. Tunable Parameters

```python
FG_FT_WEIGHT = 0.65
DEPENDENCY_THRESHOLD = 0.40
DEPENDENCY_MULTIPLIER = 1.5
```

These allow easy experimentation without structural changes.

---

## 13. Summary

This project balances:
- Statistical rigor
- Practical intuition
- Explainability

It produces rankings that are:
- Fair
- Robust
- Transparent
- Easy to reason about

Fantasy basketball is the application — **decision modeling is the skill**.

