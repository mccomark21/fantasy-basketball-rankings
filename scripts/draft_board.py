"""Write the Playoff Draft Board: draft_board.md and draft_board.html.

The board is one table of all players from build_rankings() in rankings.py, sorted by rank ([board] in config.toml).
Each player gets an S flag (playoff games) and a Q flag (quality games): green = good, gray = average,
yellow = poor. A short playoff week shows a red X in place of both flags ([flags] in config.toml).
A player who rests on back-to-backs has fewer playoff games than his team (playoffs.join_teams()).
The Risk column shows the injury risk tier. It does not change the value.
The stat columns are the categories in [weights]. Positions are the Yahoo positions.
The HTML page also has the team builder (#8): the team bar, the + and Fit columns and the My team tab.
"""
import json
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd

from common import OUT, load_config, weeks
from playoffs import playoff_schedule, read_schedule
from rankings import build_rankings

TITLE = "Playoff Draft Board"
# Column label for a category. A category that is not here uses its name in capitals.
LABELS = {"threes": "3PM"}
POINTS = {"good": 1, "avg": 0, "warn": -1}
# Sort key for each injury risk tier. A player with no tier sorts last.
RISK = {"low": 0, "med": 1, "high": 2, "extreme": 3}


def categories(cfg):
    """(column, label) for each category in [weights]."""
    return [(cat, LABELS.get(cat, cat.upper())) for cat in cfg["weights"]]


def load(cfg):
    t, f = cfg["board"], cfg["flags"]
    df = build_rankings(cfg)
    # A player with no team has no playoff schedule, so the player gets no flags
    df["no_team"] = df.team.isna()
    df["team"] = df.team.fillna("—")

    df["player"] = df.name + df.games.lt(t["low_games"]).map({True: " ⚠", False: ""})
    df["stats"] = df[[cat for cat, _ in categories(cfg)]].apply(lambda r: " / ".join(f"{v:.1f}" for v in r), axis=1)

    # Flags: grade(). A short week replaces the S and Q flags with an X.
    df["two_game"] = df.short_weeks != ""
    df["s_flag"] = [grade(g, f["good_playoff_games"], f["poor_playoff_games"]) for g in df.playoff_games]
    df["q_flag"] = [grade(q, f["good_quality_games"], f["poor_quality_games"]) for q in df.quality_games]
    rests = df.get("rests_b2b", pd.Series(0, index=df.index)).fillna(0).astype(bool)
    df["s_note"] = df.playoff_games.astype(str) + " playoff games" + rests.map({True: " (rests on back-to-backs)", False: ""})
    df["q_note"] = df.quality_games.astype(str) + " quality games"
    df["x_note"] = df.short_weeks
    return df


def legend(cfg):
    """(letter, CSS class, rule) for each flag, for the page notes."""
    f = cfg["flags"]

    def rule(name, good, poor):
        avg = f"{poor + 1}" if good - poor == 2 else f"{poor + 1}–{good - 1}"
        return f"{name}. Green: {good}+. Gray: {avg}. Yellow: {poor} or fewer."

    lg = [("S", "good", rule("playoff games", f["good_playoff_games"], f["poor_playoff_games"])),
          ("Q", "good", rule("quality games", f["good_quality_games"], f["poor_quality_games"]))]
    if f["avoid_week_games"]:
        lg.append(("X", "bad", f"a playoff week with {f['avoid_week_games']} games or fewer. "
                               "The X replaces the S and Q flags."))
    return lg


def short_legend(cfg):
    """(letter, CSS class, short rule) for each flag, for the legend next to the team table."""
    f = cfg["flags"]

    def rule(name, good, poor):
        return f"{name}: green {good}+, yellow ≤{poor}"

    lg = [("S", "good", rule("Games", f["good_playoff_games"], f["poor_playoff_games"])),
          ("Q", "good", rule("Quality", f["good_quality_games"], f["poor_quality_games"]))]
    if f["avoid_week_games"]:
        lg.append(("X", "bad", f"A week of ≤{f['avoid_week_games']} games"))
    return lg


def write_markdown(df, cfg):
    t = cfg["board"]
    dot = {"good": "🟢", "avg": "⚪", "warn": "🟡"}
    cols = {
        "Rank": lambda r: r.rank,
        "Player": lambda r: r.player,
        "Flags": lambda r: "—" if r.no_team else "❌" if r.two_game else f"{dot[r.s_flag]}S {dot[r.q_flag]}Q",
        "Team": lambda r: r.team,
        "Pos": lambda r: r.pos,
        "$": lambda r: f"${r.dollars:.0f}",
        "League $": lambda r: "—" if pd.isna(r.league_price) else f"${r.league_price:.0f}",
        "Diff": lambda r: "—" if pd.isna(r.surplus) else f"{r.surplus:+.0f}",
        "Sched": lambda r: f"{r.sched_score:.2f}",
        "Playoff games": lambda r: r.games_wk,
        "Quality games": lambda r: r.quality_wk,
        "Games": lambda r: r.games,
        "Risk": lambda r: risk_text(r),
        "Stats": lambda r: r.stats,
    }
    head = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]

    lines = [
        f"# {TITLE}", "",
        f"All {len(df)} players in the projections, sorted by custom rank. Made {date.today():%Y-%m-%d} by `draft_board.py`.", "",
        *[f"- {letter} = {text}" for letter, _, text in legend(cfg)],
        f"- **Stats:** {' / '.join(label for _, label in categories(cfg))} for each game.",
        f"- **Playoff games** and **quality games:** for each week ({', '.join(weeks(cfg))}). The last week is the finals.",
        "- **Pos:** Yahoo positions. — = not in the Yahoo top 500.",
        "- **Sched:** playoff schedule score of the team (1.00 = league average).",
        f"- **$:** auction dollars (${cfg['auction']['budget']} budget). $0 = not in the top {cfg['league']['teams'] * cfg['auction']['spots']}.",
        "- **League $:** expected price in this league's auction. $0 = not expected to be bought. — = no Yahoo data.",
        "- **Diff:** $ − League $. A positive number is a bargain for you.",
        f"- ⚠ = projected for fewer than {t['low_games']} games.",
        "- **Risk:** injury risk tier from the projections page. — = no tier. The value already holds the average "
        "cost of injuries. A high tier means a larger chance to miss a whole playoff week.",
        "- A player who rests on back-to-backs misses the second night in the playoff columns, the S flag and Sched.",
    ]
    start = 1
    for end in [*t["tiers"], df["rank"].max()]:
        tier = df[(df["rank"] >= start) & (df["rank"] <= end)]
        if len(tier):
            lines += ["", f"## Ranks {start}–{end}", "", *head]
            lines += ["| " + " | ".join(str(fn(r)) for fn in cols.values()) + " |" for r in tier.itertuples()]
        start = end + 1
    (OUT / "draft_board.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def shade(x, scale):
    """Cell background: green for a positive x, red for a negative x. Full color at x = scale."""
    alpha = min(abs(x) / scale, 1) * 0.55
    color = "var(--good)" if x > 0 else "var(--bad)"
    return f"background: color-mix(in srgb, {color} {alpha * 100:.0f}%, transparent)"


def flag_html(letter, flag, note=""):
    title = f' title="{note}"' if note else ""
    return f'<span class="flag {flag}"{title}>{letter}</span>'


def flags_cell(r):
    """Flag circles and a sort key: good flags minus poor flags, Q breaks ties. An X sorts last, then no team."""
    if r.no_team:
        return "", "-4.0"
    if r.two_game:
        return flag_html("X", "bad wide", r.x_note), "-3.0"
    key = POINTS[r.s_flag] + POINTS[r.q_flag] + 0.1 * POINTS[r.q_flag]
    return flag_html("S", r.s_flag, r.s_note) + flag_html("Q", r.q_flag, r.q_note), f"{key:.1f}"


def risk_text(r):
    """Injury risk tier, or "—" for a player who is not in the risk file."""
    tier = getattr(r, "inj_risk", None)
    return tier if isinstance(tier, str) else "—"


def risk_cell(r):
    """Risk tier: green for low, red for high and extreme. A player with no tier sorts last."""
    tier = risk_text(r)
    if tier not in RISK:
        return td("—", v="-1")
    return td(tier, v=RISK[tier], style=shade(1 - RISK[tier], 2))


def td(text, v=None, style=None, title=None, cls=None):
    """Table cell. v is the sort key when it is not the text."""
    attrs = (("class", cls), ("data-v", v), ("style", style), ("title", title))
    attrs = "".join(f' {k}="{x}"' for k, x in attrs if x is not None)
    return f"<td{attrs}>{text}</td>"


def html_columns(cfg, lift=False):
    """(header, numeric sort, align left, cell function) for each column of the HTML table.

    lift: add the Lift column (the board has the auction simulator results).
    """
    t, f = cfg["board"], cfg["flags"]
    # Quality games: white at the middle of the gray band, full color one band width away
    q_mid = (f["good_quality_games"] + f["poor_quality_games"]) / 2
    q_scale = f["good_quality_games"] - f["poor_quality_games"]

    def stat(cat):
        return lambda r: td(f"{getattr(r, cat):.1f}", v=f"{getattr(r, 'z_' + cat):.3f}",
                            style=shade(getattr(r, "z_" + cat), 2.5), title=f"z = {getattr(r, 'z_' + cat):+.2f}")

    return [
        ("+", False, False, add_cell),
        ("Rank", True, False, lambda r: td(r.rank)),
        ("Player", False, True, lambda r: td(r.player, cls="name")),
        ("Flags", True, True, lambda r: td(*flags_cell(r))),
        # The page fills the Fit cells from your team. Δ finals breaks ties.
        ("Fit", True, False, lambda r: td("", v="-999", cls="fit")),
        # Fit $ = $ x the started games that the player adds / the games of an average core player
        ("Fit $", True, False, lambda r: td("", v="-999", cls="fitd")),
        ("Team", False, True, lambda r: td(r.team)),
        ("Pos", False, True, lambda r: td(r.pos)),
        ("Value", True, False, lambda r: td(f"{r.value:.2f}")),
        ("$", True, False, lambda r: td(f"${r.dollars:.0f}", v=f"{r.dollars:.2f}")),
        ("League $", True, False, lambda r: td("—", v="-999") if pd.isna(r.league_price)
         else td(f"${r.league_price:.0f}", v=f"{r.league_price:.2f}")),
        ("Diff", True, False, lambda r: td("—", v="-999") if pd.isna(r.surplus)
         else td(f"{r.surplus:+.0f}", v=f"{r.surplus:.2f}", style=shade(r.surplus, 15))),
        *([("Lift", True, False, lift_cell)] if lift else []),
        ("Sched", True, False, lambda r: td(f"{r.sched_score:.2f}", style=shade(r.sched_score - 1, 0.2))),
        ("Playoff games", True, False, lambda r: td(r.games_wk, v=f"{r.week_score:.3f}",
                                                    style=shade(r.week_score - 1.2, 0.2), title=f"{r.playoff_games} games")),
        # Finals quality games break ties
        ("Quality games", True, False, lambda r: td(r.quality_wk, v=f"{r.quality_games + 0.01 * r.finals_quality:.2f}",
                                                    style=shade(r.quality_games - q_mid, q_scale),
                                                    title=f"{r.quality_games} quality games")),
        ("Games", True, False, lambda r: td(r.games, style=shade(r.games - t["low_games"], 15))),
        ("Risk", True, True, risk_cell),
        *[(label, True, False, stat(cat)) for cat, label in categories(cfg)],
    ]


def add_cell(r):
    """The + button that adds the player to your team and the X button that marks him taken by another team.

    The page turns off + for a player on your team, and X for a player on your team.
    """
    i, name = int(r.player_id), escape(r.name)
    return td(f'<button type="button" class="add" data-id="{i}" aria-label="Add {name} to my team">+</button>'
              f'<button type="button" class="take" data-id="{i}" aria-label="Mark {name} taken">×</button>', cls="add")


def lift_cell(r):
    """Lift for the first keeper. data-lift has the lift for each keeper, so the keeper list can change the cell."""
    lifts = r.lift if isinstance(r.lift, dict) else {}
    first = next(iter(lifts.values()), None)
    data = escape(json.dumps({k: round(v, 1) for k, v in lifts.items()}))
    text, v = ("—", "-999") if first is None else (f"{first:+.0f}", f"{first:.2f}")
    style = "" if first is None else f' style="{shade(first, 15)}"'
    return f'<td class="lift" data-lift="{data}" data-v="{v}"{style}>{text}</td>'


def row_open(r):
    """Row start tag. The filter bar reads the team, positions and S and Q flags from it.

    A player with an X or no team has no S or Q flags.
    """
    s, q = ("", "") if r.no_team or r.two_game else (r.s_flag, r.q_flag)
    return f'<tr data-team="{r.team}" data-pos="{r.pos}" data-s="{s}" data-q="{q}">'


def html_table(df, cfg):
    cols = html_columns(cfg, lift="lift" in df)
    # Text alignment comes from the column list, so a new column does not need new CSS
    left = [i + 1 for i, (_, _, is_left, _) in enumerate(cols) if is_left]
    style = ", ".join(f".wrap th:nth-child({i}), .wrap td:nth-child({i})" for i in left) + " { text-align: left; }"
    ths = "".join(f'<th data-num="{int(num)}">{h}</th>' for h, num, _, _ in cols)
    rows = [row_open(r) + "".join(fn(r) for *_, fn in cols) + "</tr>" for r in df.itertuples()]
    return (f"<style>{style}</style>\n"
            f'<div class="wrap"><table>\n<thead><tr>{ths}</tr></thead>\n<tbody>\n'
            + "\n".join(rows) + "\n</tbody>\n</table></div>")


def filter_bar(df):
    """Search box, position buttons, team list and S and Q flag buttons above the table. Pick 0 or more buttons."""
    pos = "".join(f'<button type="button" data-pos="{p}" aria-pressed="false">{p}</button>'
                  for p in ("PG", "SG", "SF", "PF", "C"))
    names = {"s": "Playoff games", "q": "Quality games"}
    colors = {"good": "green", "avg": "gray", "warn": "yellow"}
    flags = "".join(
        f'<span class="flags" role="group" aria-label="{names[f]} flag">' + "".join(
            f'<button type="button" data-flag="{f}" data-grade="{g}" aria-pressed="false" '
            f'aria-label="{names[f]}: {c}" title="{names[f]}: {c}">{flag_html(f.upper(), g)}</button>'
            for g, c in colors.items()) + "</span>"
        for f in names)
    # "—" (no team) goes last
    teams = sorted(df.team.unique(), key=lambda x: (x == "—", x))
    opts = '<option value="">All teams</option>' + "".join(f'<option value="{x}">{x}</option>' for x in teams)
    return (f'<div class="filters"><input id="search" type="search" placeholder="Search players" aria-label="Search players">'
            f'<span class="pos" role="group" aria-label="Positions">{pos}</span>'
            f'<select id="team" aria-label="Team">{opts}</select>{flags}'
            '<span id="combo" hidden><span></span><button type="button" aria-label="Clear the combo">Clear</button></span>'
            '<span class="fits" role="group" aria-label="Fit">'
            '<button type="button" data-fit="good" aria-pressed="false" title="Fit: 90% or more of his games add to your starts">'
            '<span class="fit-key g-good">≥90%</span></button>'
            '<button type="button" data-fit="warn" aria-pressed="false" title="Fit: 70% to 89%">'
            '<span class="fit-key g-warn">70–89%</span></button>'
            '<button type="button" data-fit="bad" aria-pressed="false" title="Fit: less than 70%">'
            '<span class="fit-key g-bad">&lt;70%</span></button>'
            '<button type="button" data-fit="hole" aria-pressed="false" title="Fills a hole">⚑</button></span>'
            '<button type="button" id="show-taken" aria-pressed="false" title="Show the players that you marked taken">'
            'Show taken</button><span id="count"></span></div>')


def top_combos(groups, top=10):
    """The top combos of each size for each keeper, in the order of groups.

    groups is sorted by low, as simulation_groups.csv is, so the top combos have the best low end.
    """
    return groups.groupby(["keeper", "size"], sort=False).head(top).reset_index(drop=True)


def combo_stats(combos, runs, summary):
    """Add base (the keeper title % in all auctions), edge (title % - base) and price to each combo.

    price: the median total price of the combo players in the auctions where all of them are in your core.
    runs: simulation_runs.csv. summary: simulation_summary.csv, indexed by keeper.
    """
    core = runs[runs.core]
    prices = {keeper: [dict(zip(r.player, r.price)) for _, r in rows.groupby("run")]
              for keeper, rows in core.groupby("keeper")}

    def price(keeper, group):
        names = group.split(" + ")
        totals = [sum(run[n] for n in names) for run in prices.get(keeper, []) if all(n in run for n in names)]
        return float(pd.Series(totals).median()) if totals else float("nan")

    base = combos.keeper.map(summary.title_pct)
    return combos.assign(base=base, edge=combos.title_pct - base,
                         price=[price(k, g) for k, g in zip(combos.keeper, combos.group)])


POSITIONS = ("PG", "SG", "SF", "PF", "C")
# Combo sizes that the size filter shows when the page opens
SIZES_SHOWN = (3, 4)


def combo_cells(names, df, cfg):
    """Cells for the combo totals: positions, $, League $, playoff games and quality games.

    A combo player who is not in df adds nothing. The games colors use the S and Q flag rules on the games
    for each player, so a combo of 3 and a combo of 4 get the same colors.
    """
    f, wks = cfg["flags"], weeks(cfg)
    rows = df[df.name.isin(names)]
    n = max(len(rows), 1)
    covered = {p for pos in rows.pos for p in str(pos).split("/")}
    pills = "".join(f'<span class="pill{" on" if p in covered else ""}">{p}</span>' for p in POSITIONS)
    games, quality = [int(rows[w].sum()) for w in wks], [int(rows["q_" + w].sum()) for w in wks]

    def totals(counts, good, poor):
        cls = "g-" + grade(sum(counts) / n, good, poor)
        return td(f'{"-".join(map(str, counts))} <b>{sum(counts)}</b>', v=sum(counts), cls=cls)

    league = rows.league_price.sum(min_count=1)
    return [td(pills, v=len(covered & set(POSITIONS)), cls="pos"),
            td(f"${rows.dollars.sum():.0f}", v=f"{rows.dollars.sum():.2f}"),
            td("—", v="-999") if pd.isna(league) else td(f"${league:.0f}", v=f"{league:.2f}"),
            totals(games, f["good_playoff_games"], f["poor_playoff_games"]),
            totals(quality, f["good_quality_games"], f["poor_quality_games"])]


def grade(n, good, poor):
    """Flag grade of a game count: "good", "avg" or "warn"."""
    return "good" if n >= good else "warn" if n <= poor else "avg"


COMBO_HEADS = [("Combo", False), ("Size", True), ("Positions", True), ("Title %", True), ("Edge", True),
               ("Auctions", True), ("Median price", True), ("$", True), ("League $", True),
               ("Playoff games", True), ("Quality games", True)]


def keeper_line(keeper, summary):
    """The simulator results for one keeper, from simulation_summary.csv."""
    if keeper not in summary.index:
        return ""
    k = summary.loc[keeper]
    cost = "" if keeper == "No keeper" else f"Keeper cost ${k.cost:.0f} · "
    return (f'<p class="summary">{cost}Title {k.title_pct:.1f}% · Playoffs {k.playoffs_pct:.1f}% · '
            f"Round-robin win {k.rr_win_pct:.1f}% in all auctions with this keeper.</p>")


def combo_panel(combos, summary, df, cfg):
    """The Core combos tab: for each keeper, the keeper results and one table row for each combo in combos.

    combos: top_combos() with combo_stats(). Click a combo to show only its players on the board.
    """
    heads = "".join(f'<th data-num="{int(num)}">{h}</th>' for h, num in COMBO_HEADS)
    blocks = []
    for i, (keeper, rows) in enumerate(combos.groupby("keeper", sort=False)):
        body = []
        for g in rows.itertuples():
            names = g.group.split(" + ")
            button = (f'<button type="button" data-players="{escape("|".join(names))}" aria-pressed="false">'
                      f"{escape(g.group)}</button>")
            pos, *totals = combo_cells(names, df, cfg)
            cells = [td(button), td(g.size), pos,
                     td(f"{g.title_pct:.0f}% ±{g.se:.0f}", v=f"{g.low:.2f}", title=f"Low end: {g.low:.0f}%"),
                     td("—", v="-999") if pd.isna(g.edge) else td(f"{g.edge:+.0f}", v=f"{g.edge:.2f}", style=shade(g.edge, 20)),
                     td(g.runs),
                     td("—", v="-999") if pd.isna(g.price) else td(f"${g.price:.0f}", v=f"{g.price:.2f}"),
                     *totals]
            hidden = "" if g.size in SIZES_SHOWN else " hidden"
            body.append(f'<tr data-size="{g.size}"{hidden}>{"".join(cells)}</tr>')
        blocks.append(f'<div data-keeper="{escape(keeper)}"{" hidden" if i else ""}>{keeper_line(keeper, summary)}'
                      f'<div class="scroll"><table class="combo-table"><thead><tr>{heads}</tr></thead>'
                      f'<tbody>{"".join(body)}</tbody></table></div></div>')
    sizes = sorted(combos["size"].unique())
    buttons = "".join(f'<button type="button" data-size="{n}" aria-pressed="{str(n in SIZES_SHOWN).lower()}">{n}</button>'
                      for n in sizes)
    return ('<div class="combos"><p>Combos of 2 to 4 players in your core in the auction simulator (auction.py). '
            "Title %: your title percent in the auctions with the combo, ± its standard error. "
            "The list is sorted by the low end (title % − 2 × error). Edge: title % minus the keeper title % in all "
            "auctions. Median price: the total price that you pay for the combo in the simulator. "
            "$ and League $: the totals for the combo players. Positions: the positions that the combo players cover. "
            "Games are colored by the S and Q flag rules for each player. "
            "A combo goes with titles. It does not cause them. Click a combo to show only its players on the board.</p>"
            f'<div class="filters"><span class="sizes" role="group" aria-label="Combo size">Size {buttons}</span></div>'
            + "".join(blocks) + "</div>")


def tab_bar(keepers=None):
    """The Board tab. With the simulator files, also the Core combos tab and the keeper list.

    keepers: the keeper names from the simulator, or None. The keeper list sets the Lift column, the combo list
    and the keeper on your team.
    """
    if not keepers:
        return ""
    tabs = [("board", "Board"), ("combos", "Core combos")]
    buttons = "".join(f'<button type="button" role="tab" data-tab="{k}" aria-selected="{str(not i).lower()}">{name}</button>'
                      for i, (k, name) in enumerate(tabs))
    opts = "".join(f'<option value="{escape(k)}">{escape(k)}</option>' for k in keepers)
    keeper = f'<label>Keeper <select id="keeper" aria-label="Keeper">{opts}</select></label>'
    return f'<nav class="tabs"><span role="tablist">{buttons}</span>{keeper}</nav>'


def positions(pos, slots):
    """The Yahoo positions of a player as a list of slots: "PG/SG" gives ["PG", "SG"]. "—" gives []."""
    return [p for p in str(pos).split("/") if p in slots]


def team_data(df, days, cfg):
    """The page data for the team builder (#8 Contracts): the config values, the playoff days and the players.

    days: the days of playoffs.playoff_schedule(), or None (no days). A player with no team gets team None.
    [team_builder] in config.toml is optional: core_max_rank 75 and weak_week_started 0 are the defaults.
    """
    tb, slots = cfg.get("team_builder", {}), cfg["league"]["slots"]
    rests = df.get("rests_b2b", pd.Series(0, index=df.index)).fillna(0).astype(int)
    players = [{"id": int(r.player_id), "name": r.name, "team": None if getattr(r, "no_team", False) else r.team,
                "pos": positions(r.pos, slots), "rank": int(r.rank), "value": round(float(r.value), 4),
                "rests_b2b": int(rest),
                "league_price": None if pd.isna(r.league_price) else int(round(r.league_price)),
                "dollars": round(float(r.dollars), 2)}
               for r, rest in zip(df.itertuples(), rests)]
    day_list = [] if days is None else [
        {"date": f"{d.date:%Y-%m-%d}", "week": d.week, "nba_games": int(d.nba_games), "quality": bool(d.quality),
         "teams": list(d.teams), "b2b": list(d.b2b)} for d in days.itertuples()]
    return {"slots": list(slots), "util": 1, "budget": cfg["auction"]["budget"], "spots": cfg["auction"]["spots"],
            "core_max_rank": tb.get("core_max_rank", 75), "weak_week_started": tb.get("weak_week_started", 0),
            "weeks": weeks(cfg), "days": day_list, "players": players}


# The team engine (#8 Contracts): scoreCore(core, data) and fit(core, player, data).
# The page inlines scripts/team_builder.js (#36) when the file is there. Else it uses STUB_ENGINE.
ENGINE = Path(__file__).parent / "team_builder.js"
STUB_ENGINE = """// Stub engine: the result shapes of #8 with zeros, until scripts/team_builder.js is there.
function scoreCore(core, data) {
  const zero = () => ({started: 0, lost: 0, holes: 0});
  return {
    weeks: Object.fromEntries(data.weeks.map(w => [w, {...zero(), lost_by: {}}])),
    total: zero(),
    finals: zero(),
    days: data.days.map(d => ({date: d.date, quality: d.quality, starters: {}, sat: [], rested: [], empty: []})),
  };
}
function fit(core, player, data) {
  return {started: 0, finals: 0, holes_removed: 0, games: 0, quality: 0, quality_started: 0};
}
function slotRoster(players, data) {
  return {slots: {}, bench: players};
}
module.exports = {scoreCore, fit, slotRoster};
"""


def engine_js():
    """The JavaScript of the team engine: scripts/team_builder.js, or STUB_ENGINE if the file is not there."""
    return ENGINE.read_text(encoding="utf-8") if ENGINE.exists() else STUB_ENGINE


def script_json(data):
    """JSON for a <script type="application/json"> block. "</" cannot close the block."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def write_html(df, cfg, sim=None, days=None):
    """sim: (combos, summary) from load_simulation(), or None if the auction simulator has not run.

    days: the days of playoffs.playoff_schedule() for the team builder, or None.
    """
    t = cfg["board"]
    note = f"All {len(df)} players in the projections, sorted by custom rank. Made {date.today():%Y-%m-%d}."
    flags = "".join(f"<span>{flag_html(letter, cls)}{text}</span>" for letter, cls, text in short_legend(cfg))
    if sim is None:
        tabs, combos = tab_bar(), ""
    else:
        tabs = tab_bar(list(sim[0].keeper.unique()))
        combos = combo_panel(*sim, df, cfg)
    html = (HTML.replace("__TITLE__", TITLE).replace("__NOTE__", note).replace("__FLAGS__", flags)
            .replace("__WEEKS__", ", ".join(weeks(cfg))).replace("__LOW__", str(t["low_games"]))
            .replace("__TABS__", tabs).replace("__COMBOS__", combos)
            .replace("__FILTERS__", filter_bar(df)).replace("__BODY__", html_table(df, cfg))
            # Last, so that no other placeholder can match text in the data or in the engine
            .replace("__TEAM_DATA__", script_json(team_data(df, days, cfg))).replace("__ENGINE__", engine_js()))
    (OUT / "draft_board.html").write_text(html, encoding="utf-8")


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg: #fafaf9; --fg: #1c1917; --muted: #78716c; --line: #e7e5e4; --head: #f5f5f4;
        --good: #16a34a; --bad: #dc2626; --warn: #eab308; --avg: #d6d3d1; --q: #7c3aed; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #1c1917; --fg: #f5f5f4; --muted: #a8a29e; --line: #44403c;
        --head: #292524; --good: #22c55e; --bad: #ef4444; --warn: #facc15; --avg: #57534e; --q: #a78bfa; }
}
:root[data-theme="dark"] { --bg: #1c1917; --fg: #f5f5f4; --muted: #a8a29e; --line: #44403c;
        --head: #292524; --good: #22c55e; --bad: #ef4444; --warn: #facc15; --avg: #57534e; --q: #a78bfa; }
body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
       font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 22px; margin: 0 0 4px; }
p { margin: 0 0 8px; color: var(--muted); }
.wrap { overflow: auto; max-height: calc(100vh - 32px); border: 1px solid var(--line); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 10px; text-align: right; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { position: sticky; top: 0; background: var(--head); cursor: pointer; user-select: none; font-weight: 600; }
th:hover { color: var(--q); }
th.asc::after { content: " ▲"; } th.desc::after { content: " ▼"; }
td.name { font-weight: 600; }
tr:last-child td { border-bottom: 0; }
.flag { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
        margin-right: 3px; border-radius: 50%; color: #fff; font-size: 11px; font-weight: 700;
        vertical-align: middle; cursor: default; }
.flag.good { background: var(--good); } .flag.warn { background: var(--warn); color: #1c1917; } .flag.bad { background: var(--bad); }
.flag.avg { background: var(--avg); color: var(--fg); }
.flag.wide { width: 39px; border-radius: 9px; }
p .flag { margin-right: 6px; }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0 8px; }
.filters input, .filters select, .filters button { font: inherit; color: var(--fg); background: var(--bg);
        border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
.filters input { width: 200px; }
.filters .pos, .filters .flags, .filters .fits { display: inline-flex; gap: 4px; }
.filters .fits button { padding: 0 4px; }
.filters .fits .fit-key { margin: 0; }
.filters .flags { align-self: stretch; }
.filters .flags button { min-width: 0; padding: 0 4px; display: inline-flex; align-items: center; }
.filters .flags .flag { margin: 0; }
.filters button { cursor: pointer; min-width: 36px; }
.filters button[aria-pressed="true"] { background: var(--q); border-color: var(--q); color: #fff; }
#count { color: var(--muted); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; }
.legend .flag { margin-right: 4px; }
details.notes { margin: 0 0 8px; color: var(--muted); }
details.notes summary { cursor: pointer; color: var(--fg); width: fit-content; }
details.notes p { margin: 6px 0 0; }
.tabs { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 12px 0 0;
        border-bottom: 1px solid var(--line); }
.tabs [role="tab"] { font: inherit; font-weight: 600; color: var(--muted); background: none; border: 0;
        border-bottom: 2px solid transparent; padding: 6px 2px; margin-right: 12px; cursor: pointer; }
.tabs [role="tab"][aria-selected="true"] { color: var(--fg); border-bottom-color: var(--q); }
.tabs label { color: var(--muted); padding-bottom: 4px; }
.tabs select, .combos button, #combo button { font: inherit; color: var(--fg); background: var(--bg);
        border: 1px solid var(--line); border-radius: 6px; padding: 2px 8px; cursor: pointer; }
#combo { display: inline-flex; align-items: center; gap: 6px; padding: 2px 4px 2px 10px; border-radius: 6px;
        background: color-mix(in srgb, var(--q) 15%, transparent); }
.combos { margin-top: 12px; }
.combos .summary { color: var(--fg); font-weight: 600; }
.combos button[aria-pressed="true"] { background: var(--q); border-color: var(--q); color: #fff; }
.muted { color: var(--muted); }
.scroll { max-width: 100%; overflow-x: auto; }
table.combo-table { width: auto; border: 1px solid var(--line); border-radius: 8px; border-collapse: separate;
        border-spacing: 0; }
table.combo-table th { position: static; }
table.combo-table th:first-child, table.combo-table td:first-child { text-align: left; }
table.combo-table td.pos { text-align: left; }
table.combo-table td:first-child { white-space: normal; min-width: 220px; }
table.combo-table td:first-child button { text-align: left; }
table.combo-table tr:last-child td { border-bottom: 0; }
.pill { display: inline-block; min-width: 22px; margin-right: 2px; padding: 0 3px; border-radius: 4px;
        font-size: 11px; font-weight: 600; text-align: center; color: var(--muted); border: 1px dashed var(--line); }
.pill.on { color: #fff; background: var(--q); border: 1px solid var(--q); }
.combos .filters { margin: 8px 0; }
.combos .sizes { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); }
.g-good { background: color-mix(in srgb, var(--good) 35%, transparent); }
.g-avg { background: color-mix(in srgb, var(--avg) 50%, transparent); }
.g-warn { background: color-mix(in srgb, var(--warn) 45%, transparent); }
.team { margin: 12px 0 0; }
.team-head { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 16px; margin-bottom: 6px; }
.team-head h2 { font-size: 16px; margin: 0; }
.team-head .warning { color: var(--bad); font-weight: 600; }
.team-body { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 12px 16px; }
.team-main { min-width: 0; max-width: 100%; }
.team-legend { flex: 0 0 auto; padding: 6px 10px; border: 1px solid var(--line); border-radius: 8px; white-space: nowrap; }
.team-legend.two { column-count: 2; column-gap: 20px; }
.team-legend h2 { font-size: 14px; margin: 0 0 4px; column-span: all; }
.team-legend .lg { break-inside: avoid; margin-bottom: 4px; }
.team-legend h3 { font-size: 12px; margin: 0 0 3px; color: var(--muted); font-weight: 600; }
.team-legend .legend { display: flex; flex-direction: column; gap: 1px; margin: 0; color: var(--fg); font-size: 12px; }
.team-legend .flag { width: 15px; height: 15px; font-size: 10px; margin-right: 6px; }
.team-legend table.key td { border: 0; text-align: left; padding: 1px 6px 1px 0; font-size: 12px; }
.team-legend table.key td.d { text-align: center; padding: 1px; }
.fit-key { display: inline-block; padding: 0 4px; margin-right: 4px; border-radius: 4px; }
.team button, td.add button, #show-taken { font: inherit; color: var(--fg); background: var(--bg);
        border: 1px solid var(--line); border-radius: 6px; padding: 0 8px; cursor: pointer; }
.team button[aria-pressed="true"], #show-taken[aria-pressed="true"] { background: var(--q); border-color: var(--q); color: #fff; }
.team-head button[data-act="reset"] { border-color: var(--bad); color: var(--bad); font-weight: 600; }
.kmark { display: inline-block; padding: 0 4px; margin-right: 4px; border-radius: 4px; background: var(--q); color: #fff;
        font-size: 11px; font-weight: 700; }
td.add { padding: 2px 6px; }
td.add button { min-width: 26px; font-weight: 700; margin-right: 3px; }
td.add button.take { color: var(--bad); }
td.add button:disabled { opacity: 0.35; cursor: default; }
tr.mine { background: color-mix(in srgb, var(--q) 12%, transparent); }
tr.taken { opacity: 0.45; }
input.price { width: 40px; font: inherit; color: var(--fg); background: var(--bg); border: 1px solid var(--line);
        border-radius: 6px; padding: 0 4px; }
table.plain { width: auto; border: 1px solid var(--line); border-radius: 8px; border-collapse: separate; border-spacing: 0; }
table.plain th { position: static; cursor: default; }
table.plain th:hover { color: inherit; }
table.team-table th, table.team-table td { padding: 3px 4px; }
table.team-table td.l, table.team-table th.l { text-align: left; }
table.team-table tr.open td { color: var(--muted); }
table.team-table .d { width: 16px; min-width: 16px; padding: 3px 1px; text-align: center; font-size: 12px; }
table.team-table th.d { font-size: 11px; font-weight: 600; line-height: 1.15; }
table.team-table .wk { border-left: 2px solid var(--line); }
table.team-table .qcol { background: color-mix(in srgb, var(--q) 10%, transparent); }
table.team-table th.qcol { color: var(--q); }
table.team-table tfoot td { border-bottom: 0; font-weight: 600; }
table.team-table tfoot tr:first-child td { border-top: 2px solid var(--line); }
table.team-table tfoot td.pct { text-align: center; font-size: 12px; }
td.d.on { background: color-mix(in srgb, var(--good) 40%, transparent); }
td.d.on.qcol { background: color-mix(in srgb, var(--q) 45%, transparent); color: #fff; }
td.d.sat, td.d.hole { background: color-mix(in srgb, var(--bad) 45%, transparent); }
td.d.rest { color: var(--muted); }
td.d.stream { color: var(--muted); }
td.fit span { display: inline-block; padding: 0 4px; border-radius: 4px; }
.g-bad { background: color-mix(in srgb, var(--bad) 35%, transparent); }
[hidden] { display: none !important; }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<p>__NOTE__</p>
<details class="notes"><summary>How to read this board</summary>
<p>Stats are per game, colored by z-score. Playoff games and quality games are shown for each week (__WEEKS__).
Playoff games is colored by week value: 2-game weeks cost the most. Quality games is colored by the total.</p>
<p>Pos: Yahoo positions (— = not in the Yahoo top 500). Sched: 1.00 = league average. A player who rests on back-to-backs misses the second nights in the playoff columns, the S flag and Sched.</p>
<p>$: auction dollars. League $: expected price in this league. Diff: $ − League $ (green = bargain). Lift: your title % with the player minus without him, for the keeper in the keeper list (only when the auction simulator has run).</p>
<p>Games is red below __LOW__. ⚠ = fewer than __LOW__ games.
Risk: injury risk tier (— = no tier). The value already holds the average cost of injuries. A high tier means a larger chance to miss a whole playoff week.</p>
<p>My team: + adds a player to the table at the top. × in the table removes him. × on a board row marks a player
taken by another team and hides him (Show taken shows him again, ↺ undoes it). Reset clears your team and the taken
players. The keeper stays. Slot: your players fill PG, SG, SF, PF, C and Util in value order, highest first.
A player with no open slot goes to the bench. An empty slot shows a position that you still need. The day columns show your core in the best lineup on each day: green = starts, purple = starts
on a quality day, red ✕ = sits in a logjam, r = rests on a back-to-back, ○ = a stream player who plays. The last row shows
the starters on each day, red for a hole (an empty slot on a quality day).</p>
<p>Team table footer: Started = the starters in the best lineup that day: green = all slots, yellow = 4 or 5,
red = 3 or fewer or a hole on a quality day. Used = started / the games of your core for each week: 100% means that
no game sits in a logjam (point to the cell to see who sits). vs ideal = started / the games of a core of the same
size in which each player has the most games of the week (at most 6 starters a day). Green = 90% or more.</p>
<p>Fit: the games that the player adds to your started games / his playoff games, then the same for quality games.
Green = 90% or more, yellow = 70% to 89%, red = less than 70%. A low share means a logjam: he sits, or he pushes out
one of your players. ⚑ = he fills at least one hole. The Fit buttons in the filter bar show the players with a
Fit color (the games part) or with ⚑. Click the Fit header to sort by the started games that a player adds.
Fit $ = $ × the started games that he adds / the playoff games of an average top-75 player. Green = his schedule
makes him worth more than his $ to your team, red = less. Sort by Fit $ to balance value and schedule. The page keeps your team in this browser.</p>
<p>Point to a flag to see the reason. Click a column header to sort.
Pick one or more positions to show players who can play any of them.
Pick one or more S or Q colors to show players with those flags. A player with an X or no team has no S or Q flags.</p>
</details>
__TABS__
<section id="board" role="tabpanel">
<div class="team" aria-label="My team">
<div class="team-head"><h2>My team</h2><span id="budget"></span><span id="team-warn" class="warning"></span>
<button type="button" data-act="reset" title="Clear your team and the taken players. The keeper stays.">Reset</button></div>
<div class="team-body"><div class="team-main">
<div class="scroll"><table id="roster" class="plain team-table"><thead></thead><tbody></tbody><tfoot></tfoot></table></div>
</div>
<aside class="team-legend" aria-labelledby="legend-title">
<h2 id="legend-title">Legend</h2>
<div class="lg"><h3>Flags</h3><p class="legend">__FLAGS__</p></div>
<div class="lg"><h3>Playoff days</h3><table class="team-table key"><tbody>
<tr><td class="d on">●</td><td>Starts</td></tr>
<tr><td class="d on qcol">◆</td><td>Starts, quality day</td></tr>
<tr><td class="d sat">✕</td><td>Sits (logjam)</td></tr>
<tr><td class="d rest">r</td><td>Rest night</td></tr>
<tr><td class="d stream">○</td><td>Streamer plays</td></tr>
<tr><td class="d qcol"></td><td>Quality day</td></tr>
<tr><td class="d g-good">6</td><td>Started: all slots</td></tr>
<tr><td class="d g-warn">5</td><td>Started: 4 or 5</td></tr>
<tr><td class="d hole">3</td><td>Started: ≤3, or a hole</td></tr>
</tbody></table></div>
<div class="lg"><h3>Fit and %</h3><p class="legend">
<span><span class="fit-key g-good">≥90%</span><span class="fit-key g-warn">70–89%</span><span class="fit-key g-bad">&lt;70%</span></span>
<span>Fit: games &amp; quality games added</span>
<span>⚑ Fills a hole</span></p></div>
</aside>
</div>
</div>
__FILTERS__
__BODY__
</section>
<section id="combos" role="tabpanel" hidden>
__COMBOS__
</section>
<script type="application/json" id="team-data">__TEAM_DATA__</script>
<script>
// Team engine (#8 Contracts): scoreCore(core, data) and fit(core, player, data). The engine file can declare the
// functions or export them with module.exports.
const engine = (() => {
  const module = {exports: {}};
  const exports = module.exports;
__ENGINE__
  return {scoreCore: module.exports.scoreCore || scoreCore, fit: module.exports.fit || fit,
          slotRoster: module.exports.slotRoster || slotRoster};
})();
</script>
<script>
// Search ignores case and accents, so "jokic" finds "Jokić"
const fold = s => s.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase();
const search = document.getElementById("search"), team = document.getElementById("team");
const posButtons = [...document.querySelectorAll(".filters .pos button")];
const flagButtons = [...document.querySelectorAll(".filters .flags button")];
const pressed = bs => bs.filter(b => b.getAttribute("aria-pressed") === "true");
const showTaken = document.getElementById("show-taken");
const fitButtons = [...document.querySelectorAll(".filters .fits button")];
const allRows = [...document.querySelectorAll("#board .wrap tbody tr")];
allRows.forEach(tr => tr.dataset.name = fold(tr.querySelector(".name").textContent));
function applyFilters() {
  const q = fold(search.value.trim());
  const picked = pressed(posButtons).map(b => b.dataset.pos);
  // For each flag (S, Q) with a color picked, the row flag must be one of the picked colors
  const grades = Object.fromEntries(["s", "q"].map(f =>
    [f, pressed(flagButtons).filter(b => b.dataset.flag === f).map(b => b.dataset.grade)]));
  const flagOk = tr => Object.entries(grades).every(([f, g]) => !g.length || g.includes(tr.dataset[f]));
  // Fit: the row grade must be one of the picked colors. With ⚑ on, the player must fill a hole.
  const fits = pressed(fitButtons).map(b => b.dataset.fit), colors = fits.filter(f => f !== "hole");
  const fitOk = tr => (!colors.length || colors.includes(tr.dataset.fit)) && (!fits.includes("hole") || tr.dataset.hole === "1");
  let shown = 0;
  allRows.forEach(tr => {
    const ok = tr.dataset.name.includes(q)
      && (!group || group.has(tr.dataset.name.replace(" ⚠", "")))
      && (!team.value || tr.dataset.team === team.value)
      && (!picked.length || tr.dataset.pos.split("/").some(p => picked.includes(p)))
      && flagOk(tr)
      && (showTaken.getAttribute("aria-pressed") === "true" || !tr.classList.contains("taken"))
      && fitOk(tr);
    tr.hidden = !ok;
    shown += ok;
  });
  const taken = allRows.filter(tr => tr.classList.contains("taken")).length;
  document.getElementById("count").textContent = `${shown} of ${allRows.length} players` + (taken ? ` · ${taken} taken` : "");
}
[...posButtons, ...flagButtons, ...fitButtons, showTaken].forEach(b => b.addEventListener("click", () => {
  b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") === "true" ? "false" : "true");
  applyFilters();
}));
search.addEventListener("input", applyFilters);
team.addEventListener("change", applyFilters);

// Tabs and core combos (only when the auction simulator has run): the keeper list and the combo filter
const tabs = [...document.querySelectorAll('[role="tab"]')];
function showTab(name) {
  tabs.forEach(t => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  document.querySelectorAll('[role="tabpanel"]').forEach(p => p.hidden = p.id !== name);
}
tabs.forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));

let group = null;
const keeper = document.getElementById("keeper");
const chip = document.getElementById("combo");
const groupButtons = [...document.querySelectorAll(".combos button[data-players]")];
function setCombo(button) {
  groupButtons.forEach(b => b.setAttribute("aria-pressed", String(b === button)));
  group = button ? new Set(button.dataset.players.split("|").map(fold)) : null;
  chip.hidden = !button;
  chip.firstElementChild.textContent = button ? `Combo: ${button.textContent}` : "";
  applyFilters();
}
function showKeeper() {
  document.querySelectorAll(".combos [data-keeper]").forEach(d => d.hidden = d.dataset.keeper !== keeper.value);
  document.querySelectorAll("td.lift").forEach(td => {
    const v = JSON.parse(td.dataset.lift)[keeper.value];
    td.textContent = v == null ? "—" : (v > 0 ? "+" : "") + Math.round(v);
    td.dataset.v = v == null ? -999 : v;
    const alpha = v == null ? 0 : Math.min(Math.abs(v) / 15, 1) * 55;
    td.style.background = `color-mix(in srgb, var(${v > 0 ? "--good" : "--bad"}) ${alpha}%, transparent)`;
  });
  setCombo(null);
}
// A click on a combo shows the board with only the combo players. A second click clears it.
groupButtons.forEach(b => b.addEventListener("click", () => {
  const on = b.getAttribute("aria-pressed") !== "true";
  setCombo(on ? b : null);
  if (on) showTab("board");
}));
chip.lastElementChild.addEventListener("click", () => setCombo(null));
// Size buttons: show the combos of the picked sizes. With no size picked, show all combos.
const sizeButtons = [...document.querySelectorAll(".combos .sizes button")];
function showSizes() {
  const picked = pressed(sizeButtons).map(b => b.dataset.size);
  document.querySelectorAll(".combo-table tbody tr").forEach(tr =>
    tr.hidden = picked.length > 0 && !picked.includes(tr.dataset.size));
}
sizeButtons.forEach(b => b.addEventListener("click", () => {
  b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") === "true" ? "false" : "true");
  showSizes();
}));
if (keeper) keeper.addEventListener("change", showKeeper);
applyFilters();

function sortTable(th, desc) {
  const table = th.closest("table"), body = table.tBodies[0], i = th.cellIndex;
  const num = th.dataset.num === "1";
  const key = tr => { const c = tr.cells[i]; return num ? parseFloat(c.dataset.v ?? c.textContent) : c.textContent; };
  const rows = [...body.rows].sort((a, b) => {
    const x = key(a), y = key(b);
    const cmp = num ? x - y : x.localeCompare(y);
    return desc ? -cmp : cmp;
  });
  table.querySelectorAll("th").forEach(h => h.classList.remove("asc", "desc"));
  th.classList.add(desc ? "desc" : "asc");
  body.append(...rows);
}
document.querySelectorAll("#board .wrap th, .combo-table th").forEach(th =>
  th.addEventListener("click", () => sortTable(th, !th.classList.contains("desc"))));

// Team builder (#8): your team, the budget, the playoff games of your core and the Fit column
const data = JSON.parse(document.getElementById("team-data").textContent);
const byId = new Map(data.players.map(p => [String(p.id), p]));
const byName = new Map(data.players.map(p => [p.name, p]));
const STORE = "draft-board-team";
// Storage can be off (a private window or blocked site data). The page then keeps the team until a refresh.
function loadTeam() {
  try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { return {}; }
}
function saveTeam() {
  try {
    localStorage.setItem(STORE, JSON.stringify({keeper: keeper ? keeper.value : null, keeperCore, picks, taken: [...taken]}));
  } catch (e) { /* no storage */ }
}
const saved = loadTeam();
// picks: the players that you add with +, in the order that you add them: {id, price, core}.
// core is true or false after a Core/Stream toggle, or null for the default (rank <= core_max_rank).
let picks = Array.isArray(saved.picks) ? saved.picks.filter(t => t && byId.has(String(t.id))) : [];
let keeperCore = typeof saved.keeperCore === "boolean" ? saved.keeperCore : null;
// taken: the ids of the players that other teams bought (× on a board row)
const taken = new Set(Array.isArray(saved.taken) ? saved.taken.map(String).filter(id => byId.has(id)) : []);
if (keeper && [...keeper.options].some(o => o.value === saved.keeper)) {
  keeper.value = saved.keeper;
  showKeeper();
}

// A DOM element. A prop name with "-" (aria-label, data-id) is an attribute.
function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => { if (k.includes("-")) e.setAttribute(k, v); else e[k] = v; });
  e.append(...kids.filter(k => k != null));
  return e;
}
// "Giannis Antetokounmpo" gives "G. Antetokounmpo"
const shortName = name => name.includes(" ") ? `${name[0]}. ${name.split(" ").slice(1).join(" ")}` : name;
const lastName = name => name.split(" ").slice(1).join(" ") || name;
const money = v => v == null ? "—" : `$${Math.round(v)}`;
const sameId = (a, b) => String(a) === String(b);

// Your team: the keeper first (price = league_price, no ×), then the picks
function myTeam() {
  const k = keeper ? byName.get(keeper.value) : undefined;
  const rows = picks.filter(t => !k || !sameId(t.id, k.id)).map(t => ({...t, player: byId.get(String(t.id))}));
  return k ? [{id: k.id, price: k.league_price ?? 0, core: keeperCore, keeper: true, player: k}, ...rows] : rows;
}
const isCore = t => t.core ?? t.player.rank <= data.core_max_rank;

const priceInput = t => el("input", {type: "number", min: 0, step: 1, inputMode: "numeric", className: "price",
  value: t.price, "data-act": "price", "data-id": t.id, "aria-label": `Price of ${t.player.name}`});
const coreButton = t => el("button", {type: "button", "data-act": "core", "data-id": t.id,
  "aria-pressed": String(isCore(t)), title: "Switch between Core and Stream", textContent: isCore(t) ? "Core" : "Stream"});
const removeButton = t => el("button", {type: "button", "data-act": "remove", "data-id": t.id,
  "aria-label": `Remove ${t.player.name}`, textContent: "×"});
const kMark = () => el("span", {className: "kmark", title: "Keeper", textContent: "K"});

// The playoff days. first = the first day of a week (a border in the table).
const dayInfo = data.days.map((d, i) => {
  const [y, m, day] = d.date.split("-").map(Number);
  const weekday = new Date(y, m - 1, day).toLocaleDateString("en-US", {weekday: "short"});
  return {...d, teams: new Set(d.teams), b2b: new Set(d.b2b), label: `${weekday} ${m}/${day}`, letter: weekday[0],
          first: i === 0 || data.days[i - 1].week !== d.week};
});
const dayClass = d => ["d", d.first ? "wk" : "", d.quality ? "qcol" : ""].filter(Boolean).join(" ");
const plays = (p, d) => d.teams.has(p.team) && !(p.rests_b2b && d.b2b.has(p.team));
// Games (or quality games) of a player in each playoff week, with no rest nights. For example "4-3-4".
function weekGames(p, quality) {
  return data.weeks.map(w => dayInfo.filter(d => d.week === w && (!quality || d.quality) && plays(p, d)).length).join("-");
}

const boardRows = allRows.map(tr => ({tr, add: tr.querySelector("button.add"), take: tr.querySelector("button.take"),
                                      fit: tr.querySelector("td.fit"), fitd: tr.querySelector("td.fitd")}));
// The playoff games of an average core-quality player (rank <= core_max_rank), for Fit $
const coreGames = (() => {
  const top = data.players.filter(p => p.rank <= data.core_max_rank && p.team);
  return top.length ? top.reduce((n, p) => n + dayInfo.filter(d => plays(p, d)).length, 0) / top.length : 1;
})();
const boardHeads = [...document.querySelectorAll("#board .wrap thead th")];
const fitHead = boardHeads.find(th => th.textContent === "Fit");
// The Flags cell of a player in the team table: a copy of his board cell
const rowById = new Map(boardRows.map(r => [r.add.dataset.id, r.tr]));
const flagsIndex = boardHeads.findIndex(th => th.textContent === "Flags");
function flagsCell(id) {
  const tr = rowById.get(String(id));
  const td = tr && flagsIndex >= 0 ? tr.cells[flagsIndex].cloneNode(true) : el("td");
  td.className = "l";
  return td;
}

let last = null;
function render() {
  const rows = myTeam();
  const core = rows.filter(isCore).map(t => t.player).sort((a, b) => b.value - a.value);
  last = {core, result: engine.scoreCore(core, data)};
  renderHead(rows);
  renderTeam(rows);
  renderBoard(rows, core);
  applyFilters();
  fitLegend();
  saveTeam();
}

// The legend is no taller than the team table. If one column is taller, the legend uses two columns.
const legendBox = document.querySelector(".team-legend");
function fitLegend() {
  const table = document.querySelector(".team-main");
  legendBox.classList.remove("two");
  legendBox.classList.toggle("two", legendBox.offsetHeight > table.offsetHeight);
}
window.addEventListener("resize", fitLegend);

// Budget line and warnings
function renderHead(rows) {
  const {core} = last;
  const spent = rows.reduce((s, t) => s + (Number(t.price) || 0), 0), left = data.budget - spent;
  const empty = data.spots - rows.length;
  document.getElementById("budget").textContent = `$${spent} spent · $${left} left · max bid `
    + (empty > 0 ? "$" + (left - (empty - 1)) : "—") + ` · Core ${core.length} · Stream ${rows.length - core.length}`;
  const warnings = [];
  if (core.length > data.spots - 2) warnings.push(`A core of ${core.length} leaves fewer than 2 stream spots.`);
  if (rows.length >= data.spots) warnings.push("The roster is full.");
  document.getElementById("team-warn").textContent = warnings.join(" ");
}

// The team table: one row for each roster spot, with a cell for each playoff day
function renderTeam(rows) {
  const {result} = last;
  const table = document.getElementById("roster");
  const info = ["Slot", "Player", "Flags", "Pos", "Paid", "Value", "Gms", "Q", "Core", ""];
  const left = new Set(["Slot", "Player", "Flags", "Pos"]);
  const heads = {"Gms": "Playoff games in each week", "Q": "Quality games in each week"};
  const weekHeads = data.weeks.map((w, i) => el("th", {colSpan: dayInfo.filter(d => d.week === w).length, className: "wk",
    textContent: i === data.weeks.length - 1 ? `${w} (finals)` : w}));
  table.tHead.replaceChildren(
    el("tr", {}, ...info.map(h => el("th", {rowSpan: 2, className: left.has(h) ? "l" : "", textContent: h,
      title: heads[h] || ""})), ...weekHeads),
    el("tr", {}, ...dayInfo.map(d => el("th", {className: dayClass(d), textContent: d.letter,
      title: `${d.label} · ${d.nba_games} NBA games${d.quality ? " · quality day" : ""}`}))));

  // The state of each core player on each day, from the engine result
  const state = result.days.map(d => {
    const m = new Map();
    Object.values(d.starters || {}).forEach(n => m.set(n, "on"));
    (d.sat || []).forEach(n => m.set(n, "sat"));
    (d.rested || []).forEach(n => m.set(n, "rest"));
    return m;
  });
  const dayCell = (t, i) => {
    const d = dayInfo[i], p = t.player, cls = dayClass(d);
    if (!d.teams.has(p.team)) return el("td", {className: cls});
    if (!isCore(t)) return el("td", {className: cls + " stream", textContent: "○", title: `${d.label}: plays (stream player)`});
    const s = state[i].get(p.name);
    if (s === "on") return el("td", {className: cls + " on", textContent: d.quality ? "◆" : "●", title: `${d.label}: starts`});
    if (s === "sat") return el("td", {className: cls + " sat", textContent: "✕", title: `${d.label}: sits in a logjam`});
    return el("td", {className: cls + " rest", textContent: "r", title: `${d.label}: rests on a back-to-back`});
  };
  // Slot rows: the position slots and Util, then the bench. All players go in by value, highest first, also stream
  // players. So the starting slots hold the highest-value legal lineup, and each change slots the team again.
  // An open slot is an empty row, so the table shows the positions that you still need.
  const order = [...rows].sort((a, b) => b.player.value - a.player.value);
  const slotted = engine.slotRoster(order.map(t => t.player), data);
  const rowOf = new Map(order.map(t => [t.player, t]));
  const starting = [...data.slots, ...Array.from({length: data.util ?? 1}, (_, i) => i ? `Util${i + 1}` : "Util")];
  const benchSize = Math.max(data.spots - starting.length, slotted.bench.length);
  const lines = [...starting.map(s => [s, slotted.slots[s]]),
                 ...Array.from({length: benchSize}, (_, i) => ["Bench", slotted.bench[i]])];
  const filled = lines.map(([slot, p]) => p ? teamRow(slot, rowOf.get(p)) : el("tr", {className: "open"},
    el("td", {className: "l", textContent: slot}), el("td", {className: "l", colSpan: info.length - 1, textContent: "— empty —"}),
    ...dayInfo.map(d => el("td", {className: dayClass(d)}))));
  table.tBodies[0].replaceChildren(...filled);

  function teamRow(slot, t) {
    return el("tr", {className: isCore(t) ? "" : "stream"},
    el("td", {className: "l", textContent: slot}),
    el("td", {className: "l name", title: t.player.name}, t.keeper ? kMark() : null, shortName(t.player.name)),
    flagsCell(t.id),
    el("td", {className: "l", textContent: t.player.pos.join("/") || "—"}),
    el("td", {}, t.keeper ? money(t.price) : priceInput(t)),
    el("td", {textContent: t.player.value.toFixed(2)}),
    el("td", {textContent: weekGames(t.player, false)}),
    el("td", {textContent: weekGames(t.player, true)}),
    el("td", {}, coreButton(t)),
    el("td", {}, t.keeper ? null : removeButton(t)),
    ...dayInfo.map((_, i) => dayCell(t, i)));
  }

  renderFooter(rows, result);
}

// Max games in a week for the "vs ideal" row: each core player gets the most games that any NBA team plays that week,
// and a day has at most one starter for each slot.
const idealWeek = Object.fromEntries(data.weeks.map(w => {
  const days = dayInfo.filter(d => d.week === w), games = {};
  days.forEach(d => d.teams.forEach(t => games[t] = (games[t] || 0) + 1));
  return [w, {most: Math.max(0, ...Object.values(games)), days: days.length}];
}));
const pctClass = r => r >= 0.9 ? "g-good" : r >= 0.7 ? "g-warn" : "g-bad";

// The footer of the team table: one cell for each day (started) and one cell for each week (Used and
// vs ideal). Used = started / the games of your core (the cost of logjams). vs ideal = started / the ideal week.
function renderFooter(rows, result) {
  const core = rows.filter(isCore).map(t => t.player), slots = data.slots.length + (data.util ?? 1);
  const span = document.getElementById("roster").tHead.rows[0].cells.length - data.weeks.length;
  const games = dayInfo.map(d => core.filter(p => plays(p, d)).length);
  const started = result.days.map(d => slots - (d.empty || []).length);
  const weeks = data.weeks.map(w => {
    const r = result.weeks[w], idx = dayInfo.flatMap((d, i) => d.week === w ? [i] : []);
    const ideal = Math.min(core.length * idealWeek[w].most, slots * idealWeek[w].days);
    return {...r, games: idx.reduce((n, i) => n + games[i], 0), ideal, days: idx.length};
  });
  const total = k => weeks.reduce((n, w) => n + w[k], 0);
  const pct = (got, all) => all ? `${got}/${all} · ${Math.round(100 * got / all)}%` : "—";
  const label = (text, title) => el("td", {className: "l", colSpan: span, textContent: text, title});

  // Started: green when all slots start, yellow at 4 or 5, red at 3 or fewer. On a quality day, an empty slot is red.
  const startClass = (n, d) => d.quality && n < slots ? "hole" : n >= slots ? "g-good" : n >= slots - 2 ? "g-warn" : "g-bad";
  const dayRow = (text, title, cell) => el("tr", {}, label(text, title), ...dayInfo.map(cell));
  const weekRow = (text, title, cell) => el("tr", {}, label(text, title), ...weeks.map((w, i) => {
    const td = cell(w, i);
    td.colSpan = w.days;
    td.className = ["wk", "pct", td.className].join(" ");
    return td;
  }));
  const share = (got, all, title) => el("td", {className: all ? pctClass(got / all) : "muted", textContent: pct(got, all), title});

  document.getElementById("roster").tFoot.replaceChildren(
    dayRow(`Started (of ${slots}) · ${total("started")} · ${total("holes")} holes`,
      "Starters in the best lineup that day. Red on a quality day: a hole.",
      (d, i) => el("td", {className: ["d", d.first ? "wk" : "", rows.length ? startClass(started[i], d) : ""].join(" "),
        textContent: started[i],
        title: `${d.label}: ${started[i]} of ${slots} slots` + (d.quality && started[i] < slots ? `, ${slots - started[i]} holes` : "")})),
    weekRow(`Used (started / games) · ${pct(total("started"), total("games"))}`,
      "The share of your core's games that start. Logjams lower it.",
      w => {
        const lost = Object.entries(w.lost_by || {}).map(([n, k]) => `${n} ×${k}`).join(", ");
        const td = share(w.started, w.games, `${w.started} of ${w.games} games start` + (lost ? `. Logjam: ${lost}` : ""));
        if (core.length && w.started < data.weak_week_started) {
          td.textContent += " ⚠";
          td.title += `. Fewer than ${data.weak_week_started} started games.`;
        }
        return td;
      }),
    weekRow(`vs ideal · ${pct(total("started"), total("ideal"))}`,
      `Started / ideal: each core player with the most games of the week, at most ${slots} starters a day`,
      w => share(w.started, w.ideal, `${w.started} of ${w.ideal} ideal games`)));
}

// A part of the Fit cell: "9/12", colored by the share of his games that your started games get
function share(got, all) {
  const cls = all ? pctClass(got / all) : "muted";
  return el("span", {className: cls, textContent: `${got}/${all}`});
}

// The + and × buttons and the Fit column
function renderBoard(rows, core) {
  const mine = new Set(rows.map(t => String(t.id))), full = rows.length >= data.spots;
  boardRows.forEach(({tr, add, take, fit, fitd}) => {
    const id = add.dataset.id, on = mine.has(id), gone = taken.has(id), p = byId.get(id);
    tr.classList.toggle("mine", on);
    tr.classList.toggle("taken", gone);
    add.disabled = on || full || gone;
    add.title = on ? "On your team" : gone ? "Taken" : full ? "The roster is full" : "Add to my team";
    take.disabled = on;
    take.textContent = gone ? "↺" : "×";
    take.title = on ? "On your team" : gone ? "Not taken (undo)" : "Taken by another team";
    if (!rows.length || on || !p) {
      tr.dataset.fit = tr.dataset.hole = "";
      fitd.textContent = "";
      fitd.dataset.v = -999;
      fitd.removeAttribute("style");
      fitd.removeAttribute("title");
      fit.replaceChildren();
      fit.dataset.v = -999;
      fit.removeAttribute("title");
      return;
    }
    const d = engine.fit(core, p, data);
    fit.replaceChildren(share(d.started, d.games), " & ", share(d.quality_started, d.quality),
                        d.holes_removed > 0 ? " ⚑" : "");
    fit.dataset.v = d.started + d.quality_started / 100;
    tr.dataset.fit = d.games ? pctClass(d.started / d.games).slice(2) : "";
    tr.dataset.hole = d.holes_removed > 0 ? "1" : "";
    // Fit $: green when the schedule gives more than his $, red when it gives less
    const fd = p.dollars * d.started / coreGames, gain = fd - p.dollars;
    fitd.textContent = `$${Math.round(fd)}`;
    fitd.dataset.v = fd.toFixed(2);
    fitd.title = `$${Math.round(p.dollars)} × ${d.started} added games / ${coreGames.toFixed(1)} games of an average core player`;
    fitd.style.background = `color-mix(in srgb, var(${gain >= 0 ? "--good" : "--bad"}) ${Math.min(Math.abs(gain) / 8, 1) * 55}%, transparent)`;
    fit.title = `Adds ${d.started} of his ${d.games} playoff games and ${d.quality_started} of his ${d.quality} quality games`
      + ` (${d.finals} in the finals). ${d.holes_removed} holes filled.`;
  });
  // Keep the sort by Fit when the values change
  if (fitHead.classList.contains("asc") || fitHead.classList.contains("desc")) sortTable(fitHead, fitHead.classList.contains("desc"));
}

function addPlayer(id) {
  const p = byId.get(id), rows = myTeam();
  if (!p || rows.length >= data.spots || rows.some(t => sameId(t.id, id))) return;
  taken.delete(String(id));
  // The first price is League $ (at least $1). Change it in the price box.
  picks.push({id: p.id, price: Math.max(1, Math.round(p.league_price ?? 1)), core: null});
  render();
}
document.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.classList.contains("add")) return addPlayer(b.dataset.id);
  if (b.classList.contains("take")) {
    if (!taken.delete(b.dataset.id)) taken.add(b.dataset.id);
    return render();
  }
  const act = b.dataset.act, id = b.dataset.id;
  if (act === "remove") picks = picks.filter(t => !sameId(t.id, id));
  else if (act === "core") {
    const t = myTeam().find(t => sameId(t.id, id));
    if (!t) return;
    if (t.keeper) keeperCore = !isCore(t);
    else picks.find(x => sameId(x.id, id)).core = !isCore(t);
  } else if (act === "reset") {
    if (!confirm("Clear your team and the taken players? The keeper stays.")) return;
    picks = [];
    keeperCore = null;
    taken.clear();
  } else return;
  render();
});
// A price changes the budget only. The full render waits for the change event, so the price box keeps the focus.
document.addEventListener("input", e => {
  if (e.target.dataset.act !== "price") return;
  const t = picks.find(x => sameId(x.id, e.target.dataset.id));
  if (!t) return;
  t.price = Math.max(0, Math.round(Number(e.target.value) || 0));
  renderHead(myTeam());
  saveTeam();
});
document.addEventListener("change", e => { if (e.target.dataset.act === "price") render(); });
if (keeper) keeper.addEventListener("change", () => { keeperCore = null; render(); });
render();
</script>
</body>
</html>
"""


def load_simulation(df):
    """(df with a lift column, (combos, summary)) from the auction simulator files, or (df, None) if they are not there.

    combos: top_combos() with combo_stats(). summary: simulation_summary.csv, indexed by keeper.
    """
    files = {name: OUT / f"simulation_{name}.csv" for name in ("players", "groups", "runs", "summary")}
    if not all(f.exists() for f in files.values()):
        return df, None
    table = pd.read_csv(files["players"])
    lifts = {name: dict(zip(rows.keeper, rows.lift)) for name, rows in table.groupby("player")}
    groups = pd.read_csv(files["groups"])
    keepers = list(dict.fromkeys(groups.keeper))
    # The same keeper order in each cell as in the keeper list, so the first value is the first keeper
    lift = [{k: lifts.get(name, {}).get(k) for k in keepers} for name in df.name]
    df = df.assign(lift=[{k: v for k, v in d.items() if v is not None} for d in lift])
    summary = pd.read_csv(files["summary"], index_col="keeper")
    combos = combo_stats(top_combos(groups), pd.read_csv(files["runs"]), summary)
    return df, (combos, summary)


def main():
    cfg = load_config()
    df, sim = load_simulation(load(cfg))
    write_markdown(df, cfg)
    write_html(df, cfg, sim, playoff_schedule(read_schedule(), cfg)[1])
    print(f"Wrote {len(df)} players to draft_board.md and draft_board.html")


if __name__ == "__main__":
    main()
