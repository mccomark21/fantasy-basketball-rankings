"""Price of each player in this league's auction: the Yahoo order of players with this league's prices.

Yahoo average costs come from all Yahoo leagues. This league spends more (teams x budget), mostly in ranks 1 to 80.
  1. Rank the Yahoo players by the higher of yahoo_cost (average salary) and yahoo_value (Yahoo's projected $).
     At the top, the average salary is higher. In ranks 30 to 100, the average salary is often far below
     the projected $ (Dejounte Murray: $3.6 and $18), and managers do not let those players go that cheap.
     Ties go to the better yahoo_rank.
  2. Price curve: sort each past draft by price, and read it at the same relative place
     (rank / players drafted). A draft with 16 teams then fits a league with 14 teams. Average the drafts.
  3. Scale the curve so that the bought players (teams x spots) add up to teams x budget.
     Players below the bought players get $0.
  4. A bought player does not go below his Yahoo number (step 1): Yahoo shows it at each nomination, and
     managers anchor on it. From about rank 60 down, the curve is often lower (Paul George: $8, Yahoo $12).
     So the bought players add up to more than teams x budget (about $2,970, not $2,800).
The past drafts are in data/draft_results.csv (columns year and cost). Keeper rows are in the curve.
"""
import numpy as np
import pandas as pd


def price_curve(drafts, cfg):
    """League price for ranks 1 to teams x spots, as an array. The prices add up to teams x budget."""
    teams, a = cfg["league"]["teams"], cfg["auction"]
    n = teams * a["spots"]
    place = (np.arange(n) + 0.5) / n
    curves = []
    for _, draft in drafts.groupby("year"):
        costs = np.sort(draft.cost.to_numpy(dtype=float))[::-1]
        curves.append(np.interp(place, (np.arange(len(costs)) + 0.5) / len(costs), costs))
    curve = np.mean(curves, axis=0)
    return np.maximum(a["min_bid"], curve * teams * a["budget"] / curve.sum())


def league_prices(yahoo, drafts, cfg):
    """League price for each row of yahoo (data/yahoo_players.csv), with the same index.

    A bought player gets the higher of the curve price and his Yahoo number.
    A player with no yahoo_cost and no yahoo_value, or below the bought players, gets $0.
    """
    curve = price_curve(drafts, cfg)
    anchor = np.fmax(yahoo.yahoo_cost, yahoo.yahoo_value)
    ranked = yahoo.assign(anchor=anchor)[anchor.notna()].sort_values(["anchor", "yahoo_rank"], ascending=[False, True])
    prices = pd.Series(0.0, index=yahoo.index)
    top = ranked.index[:len(curve)]
    prices[top] = np.fmax(curve[:len(top)], anchor[top])
    return prices
