"""Write output/keeper_report.html: the auction simulator results as one page for the keeper choice.

Run auction.py first. This script reads the simulation_*.csv files in output/.
The page shows each keeper's title percent, the top 5 groups of 3 or 4 players, the best roster and the players
in your core. The best roster is the title-winning auction with the highest playoff score among the auctions
that have the top group in your core. It is the luckiest of those auctions, so use the groups and the median
prices to plan.
Each roster player gets his S and Q flags (as on the draft board) and one square for each playoff day: green = he
plays and starts, red = he plays but the best lineup of your core benches him, gray = a stream player who plays.
"""
import json

import pandas as pd

from common import OUT, load_config
from draft_board import load as load_board
from playoffs import playoff_schedule, read_schedule
from team_score import make_playoffs

TOP_GROUPS = 5  # groups of 3 or 4 for each keeper


def day_squares(roster, days, playoffs, cfg):
    """For each player in roster, one list of 7 squares for each playoff week (Monday to Sunday).

    roster: player, role, team, pos and prod. days: the days of playoffs.playoff_schedule().
    A square is "" (no game), "ok" (he starts), "jam" (he plays, but the best lineup of your core
    benches him) or "stream" (a stream player plays; the model drops stream players each week).
    """
    by_date = {d.date: set(d.teams) for d in days.itertuples()}
    core = [{**p, "pos": set(p["pos"].split("/"))} for p in roster if p["role"] != "Stream"]
    squares = {p["player"]: [] for p in roster}
    for week in cfg["playoffs"]["weeks"]:
        rows = {name: [] for name in squares}
        for date in pd.date_range(week["start"], week["end"]):
            teams = by_date.get(date, set())
            starters = {p["player"] for p in playoffs._lineup([p for p in core if p["team"] in teams])}
            for p in roster:
                plays = p["team"] in teams
                state = "stream" if p["role"] == "Stream" else "ok" if p["player"] in starters else "jam"
                rows[p["player"]].append(state if plays else "")
        for name, row in rows.items():
            squares[name].append(row)
    return squares


def best_rosters(runs, info, top_groups, days, playoffs, cfg):
    """For each keeper, the full roster of the title-winning auction with the highest playoff score.

    Only the auctions that have all the players of the keeper's top group in your core count.
    runs: simulation_runs.csv. info: the draft board players (draft_board.load() with prod), indexed by name.
    top_groups: the top group for each keeper, as "A + B + C". A keeper with no top group uses all auctions.
    """
    best = {}
    for keeper, data in runs[runs.title].groupby("keeper", sort=False):
        group = top_groups.get(keeper)
        if group:
            names = group.split(" + ")
            core = data[data.core & data.player.isin(names)].groupby("run").player.nunique()
            data = data[data.run.isin(core[core == len(names)].index)]
            if data.empty:
                continue
        top = data.loc[data.playoff_score.idxmax()]
        # dollars in runs is the team total. The player's own dollars come from info.
        roster = data[data.run == top.run].drop(columns="dollars").join(info, on="player")
        roster = roster.assign(role=roster.core.map({True: "Core", False: "Stream"}))
        roster.loc[roster.player == keeper, "role"] = "Keeper"
        squares = day_squares(roster.to_dict("records"), days, playoffs, cfg)
        roster = roster.assign(days=roster.player.map(squares))
        cols = ["player", "role", "pos", "team", "price", "dollars", "no_team", "two_game", "s_flag", "q_flag",
                "s_note", "q_note", "x_note", "days"]
        best[keeper] = {"group": group, "playoff_score": round(top.playoff_score), "rr_win_pct": round(top.rr_win_pct, 1),
                        "spent": int(roster.price.sum()), "players": roster[cols].round(1).to_dict("records")}
    return best


def report_data(cfg):
    """The data of the page, from the simulation_*.csv files."""
    summary = pd.read_csv(OUT / "simulation_summary.csv")
    players = pd.read_csv(OUT / "simulation_players.csv")
    groups = pd.read_csv(OUT / "simulation_groups.csv")
    runs = pd.read_csv(OUT / "simulation_runs.csv")
    days = playoff_schedule(read_schedule(), cfg)[1]
    board, playoffs = make_playoffs(load_board(cfg), days, cfg)
    info = board.set_index("name")[["pos", "team", "dollars", "prod", "no_team", "two_game", "s_flag", "q_flag",
                                    "s_note", "q_note", "x_note"]]
    top_groups = {k: g[g["size"] >= 3].head(TOP_GROUPS) for k, g in groups.groupby("keeper", sort=False)}
    return {
        "runs": int(runs.groupby("keeper").run.nunique().iloc[0]),
        "summary": summary.round(1).to_dict("records"),
        "players": {k: g.drop(columns="keeper").round(1).to_dict("records")
                    for k, g in players.groupby("keeper", sort=False)},
        "best": best_rosters(runs, info, {k: g.group.iloc[0] for k, g in top_groups.items() if len(g)},
                             days, playoffs, cfg),
        "dates": [[f"{d:%a %b} {d.day}" for d in pd.date_range(w["start"], w["end"])] for w in cfg["playoffs"]["weeks"]],
        "groups": {k: g.drop(columns="keeper").round(1).to_dict("records") for k, g in top_groups.items()},
    }


def main():
    missing = [f for f in ["summary", "players", "groups", "runs"] if not (OUT / f"simulation_{f}.csv").exists()]
    if missing:
        raise SystemExit("output/ does not have the auction simulator files. Run python scripts/auction.py first.")
    data = report_data(load_config())
    (OUT / "keeper_report.html").write_text(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)),
                                            encoding="utf-8")
    print(f"Wrote keeper_report.html to {OUT}")


HTML = """<title>Which Keeper Wins Titles?</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@600;800&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a scoreboard strip for the keepers, then one keeper's detail (groups beside players), then the method notes. */
:root {
  --bg: #f3f5f7; --panel: #ffffff; --ink: #14202b; --muted: #5b6b78; --line: #d8dee4;
  --accent: #1d5fd1; --accent-soft: #dce7fb; --good: #15803d; --bad: #c2410c;
  --flag-good: #16a34a; --flag-bad: #dc2626; --flag-warn: #eab308; --flag-avg: #d6d3d1;
  --display: "Saira Condensed", "Arial Narrow", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --data: "IBM Plex Mono", ui-monospace, "Cascadia Mono", monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f161d; --panel: #16212b; --ink: #e6edf3; --muted: #93a3b1; --line: #2a3946;
    --accent: #6ea0ff; --accent-soft: #1d2e4a; --good: #4ade80; --bad: #fb923c; color-scheme: dark;
    --flag-good: #22c55e; --flag-bad: #ef4444; --flag-warn: #facc15; --flag-avg: #57534e;
  }
}
:root[data-theme="dark"] {
  --bg: #0f161d; --panel: #16212b; --ink: #e6edf3; --muted: #93a3b1; --line: #2a3946;
  --accent: #6ea0ff; --accent-soft: #1d2e4a; --good: #4ade80; --bad: #fb923c; color-scheme: dark;
  --flag-good: #22c55e; --flag-bad: #ef4444; --flag-warn: #facc15; --flag-avg: #57534e;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 16px/1.5 var(--body); }
.page { max-width: 1120px; margin: 0 auto; padding-inline: 16px; padding-block: 28px 48px; display: grid; gap: 28px; }
h1, h2, h3 { font-family: var(--display); line-height: 1.05; text-wrap: balance; margin: 0; }
h1 { font-size: clamp(2.2rem, 6vw, 3.4rem); font-weight: 800; letter-spacing: 0.01em; text-transform: uppercase; }
h2 { font-size: 1.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.02em; }
h3 { font-size: 1.15rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
p { margin: 0; max-width: 68ch; }
.lede { font-size: 1.15rem; }
.lede strong { color: var(--accent); }
.meta { color: var(--muted); font-size: 0.9rem; }
.num { font-family: var(--data); font-variant-numeric: tabular-nums; }
header { display: grid; gap: 10px; }

/* Scoreboard */
.board { display: grid; gap: 10px; }
.keeper { display: grid; grid-template-columns: minmax(9rem, 13rem) 1fr; gap: 6px 18px; align-items: center;
          background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; }
.keeper.best { border-color: var(--accent); box-shadow: inset 4px 0 0 var(--accent); }
.keeper .name { font-family: var(--display); font-size: 1.5rem; font-weight: 800; text-transform: uppercase; line-height: 1; }
.keeper .cost { color: var(--muted); font-size: 0.85rem; }
.bar { position: relative; height: 34px; background: var(--accent-soft); border-radius: 3px; overflow: hidden; }
.bar span { position: absolute; inset: 0 auto 0 0; background: var(--accent); }
.bar b { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-family: var(--data);
         font-weight: 500; color: #fff; mix-blend-mode: normal; text-shadow: 0 0 6px rgba(0,0,0,.35); }
.stats { grid-column: 2; display: flex; flex-wrap: wrap; gap: 4px 22px; font-size: 0.88rem; color: var(--muted); }
.stats .num { color: var(--ink); }
@media (max-width: 560px) { .keeper { grid-template-columns: 1fr; } .stats { grid-column: 1; } }

/* Detail */
.tabs { display: flex; flex-wrap: wrap; gap: 6px; }
.tabs button { font: 600 1rem var(--display); text-transform: uppercase; letter-spacing: 0.04em; cursor: pointer;
               color: var(--ink); background: var(--panel); border: 1px solid var(--line); border-radius: 4px; padding: 6px 14px; }
.tabs button[aria-selected="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.tabs button:focus-visible, th button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.detail { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 16px; display: grid; gap: 10px; min-width: 0; }
ol.groups { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
ol.groups li { display: grid; grid-template-columns: 1fr auto; gap: 2px 12px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
ol.groups li:last-child { border-bottom: 0; padding-bottom: 0; }
.who { font-weight: 600; }
.pct { font-family: var(--data); font-weight: 500; text-align: right; }
.sub { grid-column: 1 / -1; color: var(--muted); font-size: 0.85rem; }
.range { height: 6px; grid-column: 1 / -1; position: relative; background: var(--accent-soft); border-radius: 3px; }
.range i { position: absolute; top: 0; bottom: 0; background: var(--accent); opacity: 0.45; border-radius: 3px; }
.range em { position: absolute; top: -3px; width: 3px; height: 12px; background: var(--accent); border-radius: 1px; }
.range .base { position: absolute; top: -4px; width: 1px; height: 14px; background: var(--ink); opacity: 0.6; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th { font-family: var(--display); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
th button { all: unset; cursor: pointer; }
th button:hover { color: var(--accent); }
td:first-child, th:first-child, td.l, th.l { text-align: left; }
td.num { font-family: var(--data); }
/* Best roster: S and Q flags as on the draft board, then 3 rows (weeks) of 7 squares (days). */
.sched { display: flex; align-items: center; gap: 8px; }
.flag { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
        margin-right: 3px; border-radius: 50%; color: #fff; font-size: 11px; font-weight: 700; cursor: default; }
.flag.good { background: var(--flag-good); } .flag.warn { background: var(--flag-warn); color: #1c1917; }
.flag.bad { background: var(--flag-bad); } .flag.avg { background: var(--flag-avg); color: var(--ink); }
.flag.wide { width: 39px; border-radius: 9px; }
.days { display: grid; grid-template-columns: repeat(7, 9px); gap: 2px; }
.days i { width: 9px; height: 9px; border: 1px solid var(--line); border-radius: 2px; }
.days i.ok { background: var(--flag-good); border-color: var(--flag-good); }
.days i.jam { background: var(--flag-bad); border-color: var(--flag-bad); }
.days i.stream { background: var(--muted); border-color: var(--muted); }
.legend { display: inline-flex; gap: 12px; flex-wrap: wrap; }
.legend span { display: inline-flex; align-items: center; gap: 4px; }
.chip { display: inline-block; min-width: 3.2em; padding: 1px 6px; border-radius: 3px; font-family: var(--data); text-align: right; }
.chip.up { color: var(--good); background: color-mix(in srgb, var(--good) 14%, transparent); }
.chip.down { color: var(--bad); background: color-mix(in srgb, var(--bad) 14%, transparent); }
.notes { display: grid; gap: 8px; color: var(--muted); font-size: 0.95rem; }
.notes ul { margin: 0; padding-left: 20px; display: grid; gap: 6px; max-width: 75ch; }
</style>

<main class="page">
  <header>
    <h1>Which keeper wins titles?</h1>
    <p class="lede" id="lede"></p>
    <p class="meta" id="meta"></p>
  </header>

  <section class="board" id="board" aria-label="Keeper comparison"></section>

  <section style="display:grid; gap:14px">
    <h2>What you buy with each keeper</h2>
    <div class="tabs" role="tablist" id="tabs"></div>
    <div class="detail">
      <div class="card">
        <h3>Top 5 groups of 3 or 4</h3>
        <p class="meta">Players in your core together, with your title % in those auctions. Bar: ± 2 standard errors. Line: your title % in all auctions. Sorted by the low end of the range.</p>
        <ol class="groups" id="groups"></ol>
      </div>
      <div class="card">
        <h3>Best roster with the top group</h3>
        <p class="meta" id="best-meta"></p>
        <p class="meta legend"><span><span class="days"><i class="ok"></i></span>Plays and starts</span>
          <span><span class="days"><i class="jam"></i></span>Plays, but your core has no open slot</span>
          <span><span class="days"><i class="stream"></i></span>Stream player plays</span>
          <span><span class="days"><i></i></span>No game</span></p>
        <div class="scroll"><table id="best"></table></div>
      </div>
      <div class="card">
        <h3>Players in your core</h3>
        <p class="meta">Players in your core in 3% of auctions or more. Min, Median and Max $: the prices that you pay for him. Value: his dollar value. Lift: your title % with the player minus without him. Click a header to sort.</p>
        <div class="scroll"><table id="players"></table></div>
      </div>
    </div>
  </section>

  <section class="notes">
    <h2>How the simulation works</h2>
    <ul>
      <li>Each auction has 14 teams with $200 and 10 spots. 13 bots bid near this league's past prices, and the prices move toward the Yahoo averages as rosters fill. Your keeper costs his league price.</li>
      <li>Your bot buys 7 core players and pays $1 for 3 stream spots. It bids your dollar value, scaled up with the money that the stream spots save, and adjusted for playoff fit (schedule and positions in weeks 19–21).</li>
      <li>Each team starts its best legal lineup each playoff day and streams free agents into empty slots on busy days, with 5 adds a week. The 8 teams with the best season value make the playoffs.</li>
      <li>In each auction, every player misses each playoff week with the chance of his injury tier (low 5%, medium 12%, high 19%, extreme 27%). His production on the days that he plays goes up to keep his expected production the same, so the risk changes the spread only. A player who rests on back-to-backs sits on the second night.</li>
      <li>Each playoff week gets random category totals (PTS, REB, AST, 3PM, STL, BLK). The playoff teams play a round robin each week and the real bracket: quarterfinals in week 19, semifinals in week 20 and the final in week 21.</li>
      <li>The bots do not plan for the playoffs, so the title percents are higher than in a real league. Compare the keepers with them. Do not read them as a forecast.</li>
      <li>Groups and lift show what goes with titles. They do not prove cause: a cheap player also leaves money for the rest of the core. A group seen in few auctions has a wide range.</li>
    </ul>
  </section>
</main>

<script>
const DATA = __DATA__;
const fmt = (v, d = 0) => v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const NO_KEEPER = "No keeper";
const last = n => n.split(" ").slice(-1)[0];
const tabLabel = k => k === NO_KEEPER ? k : `Keep ${last(k)}`;
const withKeeper = k => k === NO_KEEPER ? "with no keeper" : `with ${esc(k)}`;
const keepers = DATA.summary.map(s => s.keeper);
const best = DATA.summary.reduce((a, b) => (b.title_pct > a.title_pct ? b : a));
const second = DATA.summary.filter(s => s !== best).reduce((a, b) => (b.title_pct > a.title_pct ? b : a));

document.getElementById("lede").innerHTML =
  (best.keeper === NO_KEEPER ? `Keep <strong>no one</strong>. Your team wins the title in ${fmt(best.title_pct)}% of simulated auctions with no keeper, `
    : `Keep <strong>${esc(best.keeper)}</strong>. Your team wins the title in ${fmt(best.title_pct)}% of simulated auctions with him, `) +
  `against ${fmt(second.title_pct)}% ${withKeeper(second.keeper)}.` +
  (best.keeper === NO_KEEPER ? "" : ` He costs $${fmt(best.cost)}, so more of your $200 goes to the auction.`);
document.getElementById("meta").textContent =
  `${DATA.runs.toLocaleString()} simulated auctions for each keeper. 14 teams, $200 auction, H2H categories (PTS, REB, AST, 3PM, STL, BLK), playoffs in weeks 19–21.`;

const maxTitle = Math.max(...DATA.summary.map(s => s.title_pct));
document.getElementById("board").innerHTML = DATA.summary.map(s => `
  <article class="keeper${s === best ? " best" : ""}">
    <div><div class="name">${esc(s.keeper)}</div><div class="cost">Keeper cost <span class="num">$${fmt(s.cost)}</span></div></div>
    <div class="bar" role="img" aria-label="${esc(s.keeper)}: ${fmt(s.title_pct, 1)} percent titles">
      <span style="width:${(100 * s.title_pct / Math.max(maxTitle * 1.15, 1)).toFixed(1)}%"></span><b>${fmt(s.title_pct, 1)}% titles</b></div>
    <div class="stats">
      <span>Makes playoffs <span class="num">${fmt(s.playoffs_pct)}%</span></span>
      <span>Weekly win % vs playoff teams <span class="num">${fmt(s.rr_win_pct, 1)}%</span></span>
      <span>Playoff score <span class="num">${fmt(s.playoff_score)}</span></span>
      <span>Roster dollars <span class="num">$${fmt(s.dollars)}</span></span>
    </div>
  </article>`).join("");

const tabs = document.getElementById("tabs");
tabs.innerHTML = keepers.map((k, i) =>
  `<button type="button" role="tab" id="tab-${i}" aria-selected="${k === best.keeper}" data-k="${esc(k)}">${esc(tabLabel(k))}</button>`).join("");

const COLS = [
  ["player", "Player", "l"], ["pos", "Pos", "l"], ["team", "Team", "l"], ["core_pct", "In core", ""],
  ["min_price", "Min $", ""], ["median_price", "Median $", ""], ["max_price", "Max $", ""], ["dollars", "Value", ""], ["playoff_games", "Playoff G", ""],
  ["quality_games", "Quality G", ""], ["lift", "Lift", ""],
];
let sortKey = "core_pct", sortDesc = true, current = best.keeper;

function renderPlayers() {
  const rows = [...(DATA.players[current] || [])].sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    const cmp = typeof x === "string" ? x.localeCompare(y) : (x ?? -1e9) - (y ?? -1e9);
    return sortDesc ? -cmp : cmp;
  });
  const cell = (r, k) => {
    if (k === "lift") return `<span class="chip ${r.lift >= 0 ? "up" : "down"}">${r.lift > 0 ? "+" : ""}${fmt(r.lift)}</span>`;
    if (k.endsWith("price") || k === "dollars") return `$${fmt(r[k])}`;
    if (k === "core_pct") return `${fmt(r[k])}%`;
    return esc(r[k] ?? "—");
  };
  document.getElementById("players").innerHTML =
    `<thead><tr>${COLS.map(([k, h, c]) => `<th class="${c}" aria-sort="${k === sortKey ? (sortDesc ? "descending" : "ascending") : "none"}"><button type="button" data-k="${k}">${h}${k === sortKey ? (sortDesc ? " ▼" : " ▲") : ""}</button></th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map(r => `<tr>${COLS.map(([k, , c]) => `<td class="${c || "num"}">${cell(r, k)}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

function renderGroups() {
  const base = DATA.summary.find(s => s.keeper === current).title_pct;
  document.getElementById("groups").innerHTML = (DATA.groups[current] || []).map(g => {
    const lo = Math.max(0, g.title_pct - 2 * g.se), hi = Math.min(100, g.title_pct + 2 * g.se);
    return `<li><span class="who">${g.group.split(" + ").map(n => esc(n)).join(" · ")}</span>
      <span class="pct">${fmt(g.title_pct)}%</span>
      <span class="range" aria-hidden="true"><i style="left:${lo}%;width:${hi - lo}%"></i><em style="left:calc(${g.title_pct}% - 1px)"></em><span class="base" style="left:${base}%"></span></span>
      <span class="sub">${g.runs} auctions · ±${fmt(g.se)} points</span></li>`;
  }).join("") || `<li class="sub">No group of 3 or 4 appears often enough for this keeper.</li>`;
}

function renderBest() {
  const b = DATA.best[current];
  if (!b) { document.getElementById("best-meta").textContent = "No title-winning auction has the top group for this keeper."; document.getElementById("best").innerHTML = ""; return; }
  const from = b.group ? `of the auctions with ${b.group.split(" + ").join(", ")} in your core` : "";
  document.getElementById("best-meta").textContent =
    `The title-winning auction with the highest playoff score${from ? " " + from : ""}. Spent $${b.spent} of $200. ` +
    `Playoff score ${b.playoff_score}. Weekly win % vs playoff teams ${fmt(b.rr_win_pct, 1)}%. Stream spots get new players each week.`;
  const cols = [["player", "Player", "l"], ["role", "Role", "l"], ["pos", "Pos", "l"], ["team", "Team", "l"],
                ["price", "Price", ""], ["dollars", "Value", ""], ["days", "Playoff days", "l"]];
  const cell = (r, k) => k === "days" ? schedCell(r) : (k === "price" || k === "dollars") ? `$${fmt(r[k])}` : esc(r[k] ?? "—");
  document.getElementById("best").innerHTML =
    `<thead><tr>${cols.map(([, h, c]) => `<th class="${c}">${h}</th>`).join("")}</tr></thead>` +
    `<tbody>${b.players.map(r => `<tr>${cols.map(([k, , c]) => `<td class="${c || "num"}">${cell(r, k)}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

// The S and Q flags of the draft board, then one row of 7 squares (Monday to Sunday) for each playoff week.
const flag = (letter, grade, note, wide) => `<span class="flag ${grade}${wide ? " wide" : ""}" title="${esc(note)}">${letter}</span>`;
const SQUARE = { ok: "plays and starts", jam: "plays, but is on the bench", stream: "stream player plays", "": "no game" };
function schedCell(r) {
  const flags = r.no_team ? "—" : r.two_game ? flag("X", "bad", r.x_note, true)
    : flag("S", r.s_flag, r.s_note) + flag("Q", r.q_flag, r.q_note);
  const days = r.days.map((week, w) => week.map((d, i) =>
    `<i class="${d}" title="${esc(DATA.dates[w][i])}: ${SQUARE[d]}"></i>`).join("")).join("");
  return `<span class="sched"><span>${flags}</span><span class="days" role="img" aria-label="Playoff days">${days}</span></span>`;
}

function select(k) {
  current = k;
  tabs.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.k === k)));
  renderGroups(); renderBest(); renderPlayers();
}
tabs.addEventListener("click", e => { const b = e.target.closest("button"); if (b) select(b.dataset.k); });
document.getElementById("players").addEventListener("click", e => {
  const b = e.target.closest("th button"); if (!b) return;
  if (sortKey === b.dataset.k) sortDesc = !sortDesc; else { sortKey = b.dataset.k; sortDesc = !["player", "pos", "team"].includes(sortKey); }
  renderPlayers();
});
select(best.keeper);
</script>
"""


if __name__ == "__main__":
    main()
