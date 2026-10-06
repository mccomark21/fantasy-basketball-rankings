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
"""
import pandas as pd


def make_playoffs(rankings, days, cfg):
    """(players, playoffs) from build_rankings() and the days of playoffs.playoff_schedule().

    players: rankings with a prod column. playoffs: a Playoffs for these players.
    """
    league, g = cfg["league"], cfg["games"]
    pool_size = league["teams"] * league["roster_spots"]
    ranked = rankings.sort_values("value", ascending=False)
    weights = pd.Series(cfg["weights"])
    std = ranked.iloc[:pool_size][weights.index].std()
    played = (rankings.games / g["full_season"]).clip(upper=1)
    players = rankings.assign(prod=(rankings[weights.index] / std * weights).sum(axis=1) * played)
    waiver = players.loc[ranked.index[pool_size:pool_size + league["teams"]]]
    bought = ranked.iloc[:league["teams"] * cfg["auction"]["spots"]]
    return players, Playoffs(days, waiver["prod"].mean(), bought.playoff_games.mean(), cfg)


class Playoffs:
    """The playoff days, with the rules to score a roster.

    days: one row for each playoff day with week, quality and teams (playoffs.playoff_schedule()).
    streamer: production of a free agent for one game. avg_games: playoff games of an average bought player.
    """

    def __init__(self, days, streamer, avg_games, cfg):
        self.days = [(d.week, d.quality, set(d.teams)) for d in days.itertuples()]
        self.streamer, self.avg_games = streamer, avg_games
        self.stream_spots = cfg["auction"]["spots"] - cfg["simulation"]["core"]
        self.cfg = cfg

    def score(self, roster):
        """Total production of the roster and the streamers in the playoffs.

        roster is your core players: a list of dicts with team, prod and pos.
        """
        roster = [{**p, "pos": set(p["pos"].split("/"))} for p in roster]
        total, week, held, adds = 0.0, None, [], 0
        for i, (name, quality, teams) in enumerate(self.days):
            if name != week:
                week, held, adds = name, [], self.cfg["league"]["adds"]
            lineup = self._lineup([p for p in roster if p["team"] in teams])
            empty = len(self.cfg["league"]["slots"]) + 1 - len(lineup)  # + 1 for Util
            total += sum(p["prod"] for p in lineup)

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
            total += streams * self.streamer
        return total

    def fit(self, core, player):
        """What the player adds to your core, divided by what an average schedule gives (prod x avg_games).

        1 = an average fit. The value stays inside [simulation] fit_limits.
        """
        gain = self.score(core + [player]) - self.score(core)
        low, high = self.cfg["simulation"]["fit_limits"]
        return min(high, max(low, gain / (player["prod"] * self.avg_games))) if player["prod"] > 0 else 1.0

    def _games_left(self, i):
        """Games for each team from day i to the end of its week."""
        week, left = self.days[i][0], {}
        for name, _, teams in self.days[i:]:
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
