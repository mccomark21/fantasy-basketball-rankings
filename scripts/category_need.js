// Category need engine: the category gaps of your core and the Need of a candidate (issue #39, Filler and Contracts).
//
//   1. Core total = the sum of wz (weighted z-score) over the core players and the fillers, for each category.
//   2. Gap = max(0, benchmark - core total). Label: behind, even or ahead (data.category.bands, one value for each category).
//   3. Each empty core spot gets a filler. Its price is the core budget left, divided by the empty core spots.
//      The filler is the row of data.category.filler_curve with the nearest price. The engine clamps the price.
//   4. Need = sum of gaps before - sum of gaps after, when the candidate joins the core at his price.
//
// The file has no DOM code. draft_board.py inlines it in the page as a plain script, and Node loads it with require().
// The page gets the globals categoryGap, need and CategoryNeed.

const CategoryNeed = (() => {
  // The filler row with the price nearest to p. The curve is short, so a scan is enough. A tie takes the lower price.
  function _fillerRow(curve, p) {
    let best = curve[0];
    for (const row of curve) {
      const d = Math.abs(row.price - p), bd = Math.abs(best.price - p);
      if (d < bd || (d === bd && row.price < best.price)) best = row;
    }
    return best;
  }

  // The filler price for the empty core spots, as in Filler. roster: [{player, price, core}].
  // Returns {price, empty}. price is null when no core spot is empty.
  function _filler(roster, data) {
    const cat = data.category;
    let core = 0, coreSpent = 0, otherSpent = 0, other = 0;
    for (const r of roster) {
      if (r.core) {
        core += 1;
        coreSpent += r.price;
      } else {
        other += 1;
        otherSpent += r.price;
      }
    }
    const empty = Math.max(0, cat.core_size - core);
    if (empty === 0) return { price: null, empty };
    const streamEmpty = Math.max(0, data.spots - cat.core_size - other);
    const coreMoney = data.budget - otherSpent - cat.min_bid * streamEmpty;
    return { price: (coreMoney - coreSpent) / empty, empty };
  }

  // Core totals, gaps and labels. roster: [{player, price, core}]. A player with core = false is not counted,
  // but his price lowers the money for the core. Returns {totals, gaps, labels, filler_price}.
  function categoryGap(roster, data) {
    const cat = data.category, totals = {}, gaps = {}, labels = {};
    for (const c of cat.cats) totals[c] = 0;
    for (const r of roster) {
      if (!r.core) continue;
      for (const c of cat.cats) totals[c] += r.player.wz[c];
    }
    const filler = _filler(roster, data);
    if (filler.empty > 0) {
      const row = _fillerRow(cat.filler_curve, filler.price);
      for (const c of cat.cats) totals[c] += filler.empty * row.wz[c];
    }
    for (const c of cat.cats) {
      const gap = Math.max(0, cat.benchmark[c] - totals[c]);
      const band = cat.bands[c];
      gaps[c] = gap;
      labels[c] = gap >= band ? "behind" : totals[c] < cat.benchmark[c] + band ? "even" : "ahead";
    }
    return { totals, gaps, labels, filler_price: filler.price };
  }

  function _sum(gaps) {
    let s = 0;
    for (const c in gaps) s += gaps[c];
    return s;
  }

  // The Need of candidate {player, price}: the fall in the sum of gaps when he joins the core at his price.
  // The fillers are built again from the lower budget. Positive = the pick moves you toward the benchmark.
  // Returns {need, gaps_after}. A full core has no filler to remove, so the candidate adds to the core.
  function need(roster, candidate, data) {
    const before = categoryGap(roster, data);
    const after = categoryGap(roster.concat([{ player: candidate.player, price: candidate.price, core: true }]), data);
    return { need: _sum(before.gaps) - _sum(after.gaps), gaps_after: after.gaps };
  }

  return { categoryGap, need };
})();

const { categoryGap, need } = CategoryNeed;

if (typeof module !== "undefined") module.exports = CategoryNeed;
