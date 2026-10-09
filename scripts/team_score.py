"""Team score in the fantasy playoffs: the production of your starters on each playoff day.

  1. Production of a player: the weighted per-game stats, each divided by the standard deviation of the
     player pool, x (games / full_season). A player who misses games gives less in an average playoff game.
  2. Each playoff day, the best legal lineup of your core starts: the position slots (config.toml [league] slots)
     + Util. A player on the bench or a player whose team does not play adds nothing that day.
  3. Streamers: your stream spots (auction spots - [simulation] core) are empty at the start of each week.
     On a busy day, each add puts a free agent in an empty starting slot. He comes from the team that plays
     the most games in the rest of the week, and he replaces a streamer who does not play that day.
     A streamer stays until the end of the week. There are no adds on a quality day, because few free
     agents play. A streamer gives the production of an average waiver player (the first 14 after the pool).
  4. Absences (config.toml [risk]): a player with rests_b2b sits on the second night of a back-to-back with the
     chance rest_chance. In one simulated run (draw()), a player also misses each playoff week with the chance of
     his inj_risk tier. His production on the days that he plays goes up to keep his expected production the same,
     because the projected games already hold the average cost of injuries. The draw changes the spread only.
"""
import numpy as np
import pandas as pd


def make_playoffs(rankings, days, cfg):
    """(players, playoffs) from build_rankings() and the days of playoffs.playoff_schedule().

    players: rankings with prod and stats columns (see Playoffs). playoffs: a Playoffs for these players.
    """
    league, g = cfg["league"], cfg["games"]
    pool_size = league["teams"] * league["roster_spots"]
    ranked = rankings.sort_values("value", ascending=False)
    weights = pd.Series(cfg["weights"])
    std = ranked.iloc[:pool_size][weights.index].std()
    stats = rankings[weights.index].mul((rankings.games / g["full_season"]).clip(upper=1), axis=0)
    players = rankings.assign(prod=(stats / std * weights).sum(axis=1), stats=stats.values.tolist())
    waiver = ranked.index[pool_size:pool_size + league["teams"]]
    return players, Playoffs(days, players.loc[waiver, "prod"].mean(), cfg, stats.loc[waiver].mean().tolist())


class Playoffs:
    """The playoff days, with the rules to score a roster.

    days: one row for each playoff day with week, quality, teams and b2b (playoffs.playoff_schedule()).
          b2b is the list of teams on the second night of a back-to-back. Without the column, no team is.
    streamer: production of a free agent for one game.
    streamer_stats: the stats of a free agent for one game, for week_totals().
    """

    def __init__(self, days, streamer, cfg, streamer_stats=None):
        b2b = days["b2b"] if "b2b" in days else [[]] * len(days)
        self.days = [(d.week, d.quality, set(d.teams), set(rest)) for d, rest in zip(days.itertuples(), b2b)]
        self.weeks = list(dict.fromkeys(week for week, *_ in self.days))
        self.teams = sorted(set().union(*(teams for _, _, teams, _ in self.days)))
        self.streamer, self.streamer_stats = streamer, streamer_stats
        self.stream_spots = cfg["auction"]["spots"] - cfg["simulation"]["core"]
        self.cfg = cfg

    def score(self, roster):
        """Total production of the roster and the streamers in the playoffs.

        roster is your core players: a list of dicts with team, prod and pos. Optional: rests_b2b (1 if the player
        rests on back-to-backs) and out (the set of days that he misses, from draw()).
        """
        return sum(sum(p["prod"] for p in lineup) + streams * self.streamer for _, lineup, streams in self._days(roster))

    def week_totals(self, roster):
        """Expected category totals for each playoff week: one row for each week, one column for each category.

        Each player in roster also needs stats: his per-game stats x (games / full_season), in [weights] order.
        """
        totals = {}
        for week, lineup, streams in self._days(roster):
            day = np.sum([p["stats"] for p in lineup], axis=0) + streams * np.asarray(self.streamer_stats)
            totals[week] = totals.get(week, 0) + day
        return pd.DataFrame(totals, index=list(self.cfg["weights"])).T

    def draw(self, roster, rng):
        """The roster in one simulated run: each player gets out, the set of days that he misses.

        He misses a whole playoff week with the chance of his inj_risk tier ([risk] missed_week). A player with
        no tier gets [risk] missing_tier. With rests_b2b, he also sits on a second night with [risk] rest_chance.
        His prod and stats go up by 1 / (1 - chance), so his expected production is the same as without the draw.
        """
        risk = self.cfg["risk"]
        drawn = []
        for p in roster:
            tier = p.get("inj_risk")
            chance = risk["missed_week"][tier if isinstance(tier, str) else risk["missing_tier"]]
            weeks = {w for w in self.weeks if rng.random() < chance}
            out = {i for i, (week, _, _, rest) in enumerate(self.days)
                   if week in weeks or (self._rests(p, rest) and rng.random() < risk["rest_chance"])}
            scale = 1 / (1 - chance)
            player = {**p, "out": out, "prod": p["prod"] * scale}
            if "stats" in p:
                player["stats"] = [s * scale for s in p["stats"]]
            drawn.append(player)
        return drawn

    def _days(self, roster):
        """For each playoff day: (week, the players who start, the number of streamers who start)."""
        roster = [{**p, "pos": set(p["pos"].split("/"))} for p in roster]
        week, held, adds = None, [], 0
        for i, (name, quality, teams, rest) in enumerate(self.days):
            if name != week:
                week, held, adds = name, [], self.cfg["league"]["adds"]
            playing = [p for p in roster if p["team"] in teams and i not in p.get("out", ())]
            lineup = self._lineup([self._rested(p, rest) for p in playing])
            empty = len(self.cfg["league"]["slots"]) + 1 - len(lineup)  # + 1 for Util

            # Streamers: the ones that you hold play first. Then, on a busy day, each add fills one more slot.
            streams = min(empty, sum(team in teams for team in held))
            if not quality:
                left = self._games_left(i)
                while streams < empty and adds > 0 and (len(held) < self.stream_spots or any(t not in teams for t in held)):
                    if len(held) == self.stream_spots:
                        held.remove(min((t for t in held if t not in teams), key=lambda t: left.get(t, 0)))
                    held.append(max(sorted(teams), key=lambda t: left[t]))
                    adds -= 1
                    streams += 1
            yield name, lineup, streams

    def fit(self, core, player):
        """What the player adds to your core, divided by what a player on an average schedule adds.

        The other player has the same production and any position, and he does not rest on back-to-backs. His gain
        is the average for the schedules of all teams. So a weak schedule, a crowded position or rest days give a
        fit below 1, and a fit of 1 is average. The value stays inside [simulation] fit_limits.
        """
        base = self.score(core)
        gain = self.score(core + [player]) - base
        anyone = {**player, "pos": "/".join(self.cfg["league"]["slots"]), "rests_b2b": 0}
        average = np.mean([self.score(core + [{**anyone, "team": t}]) for t in self.teams]) - base
        low, high = self.cfg["simulation"]["fit_limits"]
        return min(high, max(low, gain / average)) if average > 0 else low

    def _rests(self, p, rest):
        """True if the player rests on back-to-backs and his team is on the second night (rest = those teams)."""
        return bool(p.get("rests_b2b")) and p["team"] in rest

    def _rested(self, p, rest):
        """The player with the expected production for the day: x (1 - rest_chance) on a second night that he can rest.

        A drawn player (one with out) is not scaled. His rest days are in out.
        """
        if "out" in p or not self._rests(p, rest):
            return p
        scale = 1 - self.cfg["risk"]["rest_chance"]
        player = {**p, "prod": p["prod"] * scale}
        if "stats" in p:
            player["stats"] = [s * scale for s in p["stats"]]
        return player

    def _games_left(self, i):
        """Games for each team from day i to the end of its week."""
        week, left = self.days[i][0], {}
        for name, _, teams, _ in self.days[i:]:
            if name != week:
                break
            for t in teams:
                left[t] = left.get(t, 0) + 1
        return left

    def _lineup(self, playing):
        """The best legal lineup. Adding players by production is the best order: legal lineups are a matroid."""
        slots, lineup = self.cfg["league"]["slots"], []
        for p in sorted(playing, key=lambda p: -p["prod"]):
            pos = [q["pos"] for q in lineup] + [p["pos"]]
            # A player who gets no position slot goes to Util. There is one Util slot.
            if len(pos) - (len(slots) - open_slots(pos, slots)) <= 1:
                lineup.append(p)
        return lineup


def open_slots(roster, slots):
    """Number of slots that the roster cannot fill. Each player fills one slot (bipartite matching)."""
    holder = {}

    def place(player, tried):
        for slot in slots:
            if slot in roster[player] and slot not in tried:
                tried.add(slot)
                if slot not in holder or place(holder[slot], tried):
                    holder[slot] = player
                    return True
        return False

    for player in range(len(roster)):
        place(player, set())
    return len(slots) - len(holder)
