"""Write the Playoff Draft Board: draft_board.md and draft_board.html.

The board is one table of all players from build_rankings() in rankings.py, sorted by rank ([board] in config.toml).
Each player gets an S flag (playoff games) and a Q flag (quality games): green = good, gray = average,
yellow = poor. A short playoff week shows a red X in place of both flags ([flags] in config.toml).
A player who rests on back-to-backs has fewer playoff games than his team (playoffs.join_teams()).
The Risk column shows the injury risk tier. It does not change the value.
The stat columns are the categories in [weights]. Positions are the Yahoo positions.
"""
import json
from datetime import date
from html import escape

import pandas as pd

from common import OUT, load_config, weeks
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
        ("Rank", True, False, lambda r: td(r.rank)),
        ("Player", False, True, lambda r: td(r.player, cls="name")),
        ("Flags", True, True, lambda r: td(*flags_cell(r))),
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
    style = ", ".join(f"th:nth-child({i}), td:nth-child({i})" for i in left) + " { text-align: left; }"
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
            '<span id="count"></span></div>')


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


def tab_bar(keepers):
    """Board and Core combos tabs, and the keeper list. The keeper list sets the Lift column and the combo list."""
    opts = "".join(f'<option value="{escape(k)}">{escape(k)}</option>' for k in keepers)
    return ('<nav class="tabs"><span role="tablist">'
            '<button type="button" role="tab" data-tab="board" aria-selected="true">Board</button>'
            '<button type="button" role="tab" data-tab="combos" aria-selected="false">Core combos</button></span>'
            f'<label>Keeper <select id="keeper" aria-label="Keeper">{opts}</select></label></nav>')


def write_html(df, cfg, sim=None):
    """sim: (combos, summary) from load_simulation(), or None if the auction simulator has not run."""
    t = cfg["board"]
    note = f"All {len(df)} players in the projections, sorted by custom rank. Made {date.today():%Y-%m-%d}."
    flags = "".join(f"<span>{flag_html(letter, cls)} {text}</span>" for letter, cls, text in legend(cfg))
    if sim is None:
        tabs = combos = ""
    else:
        tabs = tab_bar(list(sim[0].keeper.unique()))
        combos = combo_panel(*sim, df, cfg)
    html = (HTML.replace("__TITLE__", TITLE).replace("__NOTE__", note).replace("__FLAGS__", flags)
            .replace("__WEEKS__", ", ".join(weeks(cfg))).replace("__LOW__", str(t["low_games"]))
            .replace("__TABS__", tabs).replace("__COMBOS__", combos)
            .replace("__FILTERS__", filter_bar(df)).replace("__BODY__", html_table(df, cfg)))
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
.filters .pos, .filters .flags { display: inline-flex; gap: 4px; }
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
[hidden] { display: none !important; }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<p>__NOTE__</p>
<p class="legend">__FLAGS__</p>
<details class="notes"><summary>How to read this board</summary>
<p>Stats are per game, colored by z-score. Playoff games and quality games are shown for each week (__WEEKS__).
Playoff games is colored by week value: 2-game weeks cost the most. Quality games is colored by the total.</p>
<p>Pos: Yahoo positions (— = not in the Yahoo top 500). Sched: 1.00 = league average. A player who rests on back-to-backs misses the second nights in the playoff columns, the S flag and Sched.</p>
<p>$: auction dollars. League $: expected price in this league. Diff: $ − League $ (green = bargain). Lift: your title % with the player minus without him, for the keeper in the keeper list (only when the auction simulator has run).</p>
<p>Games is red below __LOW__. ⚠ = fewer than __LOW__ games.
Risk: injury risk tier (— = no tier). The value already holds the average cost of injuries. A high tier means a larger chance to miss a whole playoff week.</p>
<p>Point to a flag to see the reason. Click a column header to sort.
Pick one or more positions to show players who can play any of them.
Pick one or more S or Q colors to show players with those flags. A player with an X or no team has no S or Q flags.</p>
</details>
__TABS__
<section id="board" role="tabpanel">
__FILTERS__
__BODY__
</section>
<section id="combos" role="tabpanel" hidden>
__COMBOS__
</section>
<script>
// Search ignores case and accents, so "jokic" finds "Jokić"
const fold = s => s.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase();
const search = document.getElementById("search"), team = document.getElementById("team");
const posButtons = [...document.querySelectorAll(".filters .pos button")];
const flagButtons = [...document.querySelectorAll(".filters .flags button")];
const pressed = bs => bs.filter(b => b.getAttribute("aria-pressed") === "true");
const allRows = [...document.querySelectorAll("#board tbody tr")];
allRows.forEach(tr => tr.dataset.name = fold(tr.querySelector(".name").textContent));
function applyFilters() {
  const q = fold(search.value.trim());
  const picked = pressed(posButtons).map(b => b.dataset.pos);
  // For each flag (S, Q) with a color picked, the row flag must be one of the picked colors
  const grades = Object.fromEntries(["s", "q"].map(f =>
    [f, pressed(flagButtons).filter(b => b.dataset.flag === f).map(b => b.dataset.grade)]));
  const flagOk = tr => Object.entries(grades).every(([f, g]) => !g.length || g.includes(tr.dataset[f]));
  let shown = 0;
  allRows.forEach(tr => {
    const ok = tr.dataset.name.includes(q)
      && (!group || group.has(tr.dataset.name.replace(" ⚠", "")))
      && (!team.value || tr.dataset.team === team.value)
      && (!picked.length || tr.dataset.pos.split("/").some(p => picked.includes(p)))
      && flagOk(tr);
    tr.hidden = !ok;
    shown += ok;
  });
  document.getElementById("count").textContent = `${shown} of ${allRows.length} players`;
}
[...posButtons, ...flagButtons].forEach(b => b.addEventListener("click", () => {
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

document.querySelectorAll("#board th, .combo-table th").forEach(th => {
  th.addEventListener("click", () => {
    const table = th.closest("table"), body = table.tBodies[0], i = th.cellIndex;
    const desc = !th.classList.contains("desc");
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
  });
});
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
    write_html(df, cfg, sim)
    print(f"Wrote {len(df)} players to draft_board.md and draft_board.html")


if __name__ == "__main__":
    main()
