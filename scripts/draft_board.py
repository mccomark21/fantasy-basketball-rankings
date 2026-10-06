"""Write the Playoff Draft Board: draft_board.md and draft_board.html.

The board is one table of all players from build_rankings() in rankings.py, sorted by rank ([board] in config.toml).
Each player gets an S flag (playoff games) and a Q flag (quality games): green = good, gray = average,
yellow = poor. A short playoff week shows a red X in place of both flags ([flags] in config.toml).
The stat columns are the categories in [weights]. Positions are the Yahoo positions.
"""
from datetime import date

from common import OUT, load_config, weeks
from rankings import build_rankings

TITLE = "Playoff Draft Board"
# Column label for a category. A category that is not here uses its name in capitals.
LABELS = {"threes": "3PM"}
POINTS = {"good": 1, "avg": 0, "warn": -1}


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

    # Flags: "good", "avg" or "warn". A short week replaces the S and Q flags with an X.
    def grade(n, good, poor):
        return "good" if n >= good else "warn" if n <= poor else "avg"

    df["two_game"] = df.short_weeks != ""
    df["s_flag"] = [grade(g, f["good_playoff_games"], f["poor_playoff_games"]) for g in df.playoff_games]
    df["q_flag"] = [grade(q, f["good_quality_games"], f["poor_quality_games"]) for q in df.quality_games]
    df["s_note"] = df.playoff_games.astype(str) + " playoff games"
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
        "Games": lambda r: r.games,
        "Stats": lambda r: r.stats,
        "Playoff games": lambda r: r.games_wk,
        "Quality games": lambda r: r.quality_wk,
        "Sched": lambda r: f"{r.sched_score:.2f}",
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
        f"- ⚠ = projected for fewer than {t['low_games']} games.",
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
    return f'<span class="flag {flag}" title="{note}">{letter}</span>'


def flags_cell(r):
    """Flag circles and a sort key: good flags minus poor flags, Q breaks ties. An X sorts last, then no team."""
    if r.no_team:
        return "", "-4.0"
    if r.two_game:
        return flag_html("X", "bad wide", r.x_note), "-3.0"
    key = POINTS[r.s_flag] + POINTS[r.q_flag] + 0.1 * POINTS[r.q_flag]
    return flag_html("S", r.s_flag, r.s_note) + flag_html("Q", r.q_flag, r.q_note), f"{key:.1f}"


def td(text, v=None, style=None, title=None, cls=None):
    """Table cell. v is the sort key when it is not the text."""
    attrs = (("class", cls), ("data-v", v), ("style", style), ("title", title))
    attrs = "".join(f' {k}="{x}"' for k, x in attrs if x is not None)
    return f"<td{attrs}>{text}</td>"


def html_columns(cfg):
    """(header, numeric sort, align left, cell function) for each column of the HTML table."""
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
        ("Pos", False, True, lambda r: td(r.pos)),        ("Games", True, False, lambda r: td(r.games, style=shade(r.games - t["low_games"], 15))),
        *[(label, True, False, stat(cat)) for cat, label in categories(cfg)],
        ("Playoff games", True, False, lambda r: td(r.games_wk, v=f"{r.week_score:.3f}",
                                                    style=shade(r.week_score - 1.2, 0.2), title=f"{r.playoff_games} games")),
        # Finals quality games break ties
        ("Quality games", True, False, lambda r: td(r.quality_wk, v=f"{r.quality_games + 0.01 * r.finals_quality:.2f}",
                                                    style=shade(r.quality_games - q_mid, q_scale),
                                                    title=f"{r.quality_games} quality games")),
        ("Sched", True, False, lambda r: td(f"{r.sched_score:.2f}", style=shade(r.sched_score - 1, 0.2))),
        ("Value", True, False, lambda r: td(f"{r.value:.2f}")),
    ]


def html_table(df, cfg):
    cols = html_columns(cfg)
    # Text alignment comes from the column list, so a new column does not need new CSS
    left = [i + 1 for i, (_, _, is_left, _) in enumerate(cols) if is_left]
    style = ", ".join(f"th:nth-child({i}), td:nth-child({i})" for i in left) + " { text-align: left; }"
    ths = "".join(f'<th data-num="{int(num)}">{h}</th>' for h, num, _, _ in cols)
    # The filter bar reads the team and positions from these attributes
    rows = [f'<tr data-team="{r.team}" data-pos="{r.pos}">' + "".join(fn(r) for *_, fn in cols) + "</tr>"
            for r in df.itertuples()]
    return (f"<style>{style}</style>\n"
            f'<div class="wrap"><table>\n<thead><tr>{ths}</tr></thead>\n<tbody>\n'
            + "\n".join(rows) + "\n</tbody>\n</table></div>")


def filter_bar(df):
    """Search box, position buttons (pick 0 or more) and team list above the table."""
    pos = "".join(f'<button type="button" data-pos="{p}" aria-pressed="false">{p}</button>'
                  for p in ("PG", "SG", "SF", "PF", "C"))
    # "—" (no team) goes last
    teams = sorted(df.team.unique(), key=lambda x: (x == "—", x))
    opts = '<option value="">All teams</option>' + "".join(f'<option value="{x}">{x}</option>' for x in teams)
    return (f'<div class="filters"><input id="search" type="search" placeholder="Search players" aria-label="Search players">'
            f'<span class="pos" role="group" aria-label="Positions">{pos}</span>'
            f'<select id="team" aria-label="Team">{opts}</select><span id="count"></span></div>')


def write_html(df, cfg):
    t = cfg["board"]
    note = f"All {len(df)} players in the projections, sorted by custom rank. Made {date.today():%Y-%m-%d}."
    flags = "<br>".join(f"{flag_html(letter, cls)} {text}" for letter, cls, text in legend(cfg))
    html = (HTML.replace("__TITLE__", TITLE).replace("__NOTE__", note).replace("__FLAGS__", flags)
            .replace("__WEEKS__", ", ".join(weeks(cfg))).replace("__LOW__", str(t["low_games"]))
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
.filters .pos { display: inline-flex; gap: 4px; }
.filters button { cursor: pointer; min-width: 36px; }
.filters button[aria-pressed="true"] { background: var(--q); border-color: var(--q); color: #fff; }
#count { color: var(--muted); }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<p>__NOTE__</p>
<p>__FLAGS__</p>
<p>Stats are per game, colored by z-score. Playoff games and quality games are shown for each week (__WEEKS__).
Playoff games is colored by week value: 2-game weeks cost the most. Quality games is colored by the total.
Pos: Yahoo positions (— = not in the Yahoo top 500).Sched: 1.00 = league average. Games is red below __LOW__. ⚠ = fewer than __LOW__ games.
Point to a flag to see the reason. Click a column header to sort.
Pick one or more positions to show players who can play any of them.</p>
__FILTERS__
__BODY__
<script>
// Search ignores case and accents, so "jokic" finds "Jokić"
const fold = s => s.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase();
const search = document.getElementById("search"), team = document.getElementById("team");
const posButtons = [...document.querySelectorAll(".filters button")];
const allRows = [...document.querySelectorAll("tbody tr")];
allRows.forEach(tr => tr.dataset.name = fold(tr.querySelector(".name").textContent));
function applyFilters() {
  const q = fold(search.value.trim());
  const picked = posButtons.filter(b => b.getAttribute("aria-pressed") === "true").map(b => b.dataset.pos);
  let shown = 0;
  allRows.forEach(tr => {
    const ok = tr.dataset.name.includes(q)
      && (!team.value || tr.dataset.team === team.value)
      && (!picked.length || tr.dataset.pos.split("/").some(p => picked.includes(p)));
    tr.hidden = !ok;
    shown += ok;
  });
  document.getElementById("count").textContent = `${shown} of ${allRows.length} players`;
}
posButtons.forEach(b => b.addEventListener("click", () => {
  b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") === "true" ? "false" : "true");
  applyFilters();
}));
search.addEventListener("input", applyFilters);
team.addEventListener("change", applyFilters);
applyFilters();

document.querySelectorAll("th").forEach(th => {
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


def main():
    cfg = load_config()
    df = load(cfg)
    write_markdown(df, cfg)
    write_html(df, cfg)
    print(f"Wrote {len(df)} players to draft_board.md and draft_board.html")


if __name__ == "__main__":
    main()
