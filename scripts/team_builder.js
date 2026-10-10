// Team builder engine: the game counts of your core in the fantasy playoffs (issue #8, Rules and Contracts).
//
//   1. Each playoff day, the core players whose teams play go into the position slots (data.slots) and Util.
//      The engine adds them in value order, highest first. It accepts a player only when the slots and Util can
//      still hold all accepted players (bipartite matching). This is Playoffs._lineup in scripts/team_score.py.
//   2. A player with rests_b2b = 1 does not play on the second night of a back-to-back (day.b2b).
//   3. Started = the accepted players. Lost = the players who play but get no slot.
//      Holes = the empty starting slots on quality days. The engine counts no streamers.
//
// The file has no DOM code. draft_board.py inlines it in the page as a plain script, and Node loads it with require().
// The page gets the globals scoreCore, fit and TeamBuilder. The helpers stay inside the closure.

const TeamBuilder = (() => {
  // Per-day team sets for each data object, so that a call does not make them again.
  const _daySets = new WeakMap();

  function _sets(data) {
    let sets = _daySets.get(data);
    if (!sets) {
      sets = data.days.map(d => ({ teams: new Set(d.teams), b2b: new Set(d.b2b || []) }));
      _daySets.set(data, sets);
    }
    return sets;
  }

  function _utilNames(data) {
    const n = data.util === undefined ? 1 : data.util;
    return Array.from({ length: n }, (_, i) => (i === 0 ? "Util" : "Util" + (i + 1)));
  }

  // Maximum matching of players to position slots (open_slots in team_score.py).
  // Returns holder: slot -> index in lineup. A player with no slot goes to Util.
  function _match(lineup, slots) {
    const holder = {};
    function place(i, tried) {
      for (const slot of slots) {
        if (lineup[i].pos.includes(slot) && !tried.has(slot)) {
          tried.add(slot);
          if (!(slot in holder) || place(holder[slot], tried)) {
            holder[slot] = i;
            return true;
          }
        }
      }
      return false;
    }
    for (let i = 0; i < lineup.length; i++) place(i, new Set());
    return holder;
  }

  // One playoff day. ordered: the core in value order, highest first.
  function _day(ordered, day, sets, data) {
    const slots = data.slots, utils = _utilNames(data);
    const lineup = [], sat = [], rested = [];
    for (const p of ordered) {
      if (!sets.teams.has(p.team)) continue;
      if (p.rests_b2b && sets.b2b.has(p.team)) {
        rested.push(p.name);
        continue;
      }
      const trial = lineup.concat([p]);
      const placed = Object.keys(_match(trial, slots)).length;
      // The players with no position slot go to Util
      if (trial.length - placed <= utils.length) lineup.push(p);
      else sat.push(p.name);
    }

    const holder = _match(lineup, slots), starters = {}, empty = [], inSlot = new Set();
    for (const slot of slots) {
      if (slot in holder) {
        starters[slot] = lineup[holder[slot]].name;
        inSlot.add(holder[slot]);
      } else {
        empty.push(slot);
      }
    }
    const util = lineup.filter((_, i) => !inSlot.has(i));
    utils.forEach((name, i) => {
      if (i < util.length) starters[name] = util[i].name;
      else empty.push(name);
    });
    return {
      date: day.date, week: day.week, quality: !!day.quality, starters, sat, rested, empty,
      started: lineup.length, holes: day.quality ? empty.length : 0,
    };
  }

  function _ordered(core) {
    // A stable sort: two players with the same value keep the order of core
    return core.slice().sort((a, b) => b.value - a.value);
  }

  function _totals(dayResults, data) {
    const weeks = {}, total = { started: 0, lost: 0, holes: 0 };
    for (const w of data.weeks) weeks[w] = { started: 0, lost: 0, lost_by: {}, holes: 0 };
    for (const d of dayResults) {
      const w = weeks[d.week] || (weeks[d.week] = { started: 0, lost: 0, lost_by: {}, holes: 0 });
      w.started += d.started;
      w.lost += d.sat.length;
      w.holes += d.holes;
      for (const name of d.sat) w.lost_by[name] = (w.lost_by[name] || 0) + 1;
    }
    for (const w of Object.values(weeks)) {
      total.started += w.started;
      total.lost += w.lost;
      total.holes += w.holes;
    }
    const last = weeks[data.weeks[data.weeks.length - 1]];
    const finals = { started: last.started, lost: last.lost, holes: last.holes };
    return { weeks, total, finals };
  }

  // The engine result in #8: weeks, total, finals and days. core is a list of players from data.players.
  function scoreCore(core, data) {
    const ordered = _ordered(core), sets = _sets(data);
    const days = data.days.map((day, i) => _day(ordered, day, sets[i], data));
    const result = _totals(days, data);
    result.days = days.map(d => ({
      date: d.date, quality: d.quality, starters: d.starters, sat: d.sat, rested: d.rested, empty: d.empty,
    }));
    return result;
  }

  // The last base score, so that fit() for each row of the board scores the core one time only.
  let _base = null;

  function _baseDays(core, data) {
    const key = core.map(p => p.id + ":" + p.value + ":" + p.team + ":" + p.rests_b2b + ":" + p.pos.join("/")).join("|");
    if (!_base || _base.data !== data || _base.key !== key) {
      const ordered = _ordered(core), sets = _sets(data);
      _base = { data, key, ordered, days: data.days.map((day, i) => _day(ordered, day, sets[i], data)) };
    }
    return _base;
  }

  // Δ against scoreCore(core, data) when player joins the core:
  // {started, finals, holes_removed, games, quality, quality_started}.
  // games and quality: the games and quality-day games that the player can play (no rest nights).
  // quality_started: Δ started games on quality days. started < games means that his games push out other players
  // or that he sits, so the ratio started / games shows a logjam.
  // Only the days on which the team of the player plays can change, so fit() scores those days again.
  function fit(core, player, data) {
    const base = _baseDays(core, data), sets = _sets(data);
    const finalsWeek = data.weeks[data.weeks.length - 1];
    const ordered = _ordered(base.ordered.concat([player]));
    let started = 0, finals = 0, holes = 0, games = 0, quality = 0, qualityStarted = 0;
    data.days.forEach((day, i) => {
      if (!sets[i].teams.has(player.team)) return;
      if (!(player.rests_b2b && sets[i].b2b.has(player.team))) {
        games += 1;
        if (day.quality) quality += 1;
      }
      const before = base.days[i], after = _day(ordered, day, sets[i], data);
      const delta = after.started - before.started;
      started += delta;
      if (day.week === finalsWeek) finals += delta;
      if (day.quality) qualityStarted += delta;
      holes += before.holes - after.holes;
    });
    return { started, finals, holes_removed: holes, games, quality, quality_started: qualityStarted };
  }

  return { scoreCore, fit };
})();

const { scoreCore, fit } = TeamBuilder;

if (typeof module !== "undefined") module.exports = TeamBuilder;
