"""Download Yahoo positions, auction prices and ADP from the public Yahoo draft analysis pages.

The pages do not need a login. They show data from all Yahoo leagues, not only our league.
Requirement: pip install playwright, then playwright install chromium.
Output:
  data/yahoo_players.csv - one row for each player in the top 500 of Yahoo
"""
import csv

from playwright.sync_api import sync_playwright

from common import DATA

PAGE = "https://basketball.fantasysports.yahoo.com/nba/draftanalysis?type={type}&pos=ALL&sort=DA_AP&count=500"

# Reads each table row that has a player: Yahoo ID, name, team, positions, injury status and the number cells.
READ_ROWS = """rows => rows.filter(row => row.querySelector('[data-tst=player-name]')).map(row => {
    const name = row.querySelector('[data-tst=player-name]');
    const info = name.parentElement;
    const [team] = info.children[1].innerText.split(' - ');
    const lines = row.querySelector('[data-tst=player]').innerText.split('\\n').map(s => s.trim()).filter(Boolean);
    return {
        id: row.querySelector('[data-ys-playerid]')?.dataset.ysPlayerid ?? '',
        name: name.innerText.trim(),
        team: team.trim(),
        positions: row.querySelector('[data-tst=player-position]')?.innerText.trim() ?? '',
        status: lines.slice(2).join(' '),
        cells: [...row.cells].slice(1).map(c => c.innerText.trim()),
    };
})"""


def number(text):
    text = text.replace("%", "").replace("$", "").strip()
    return "" if text in ("", "-") else text


def read_table(page, kind):
    page.goto(PAGE.format(type=kind), wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("tr[data-tst^=table-row] [data-tst=player-name]", timeout=60000)
    return page.eval_on_selector_all("tr[data-tst^=table-row]", READ_ROWS)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # Auction columns: Rank, Pos Rank, CER, %Drafted, Avg $, Proj $
        auction = read_table(page, "salcap")
        # Snake columns: Rank, Pos Rank, CER, %Drafted, Preseason ADP, All Drafts ADP, ...
        snake = read_table(page, "standard")
        browser.close()

    adp = {r["id"]: number(r["cells"][4]) for r in snake}
    players = []
    for r in auction:
        cells = r["cells"]
        players.append({
            "yahoo_id": r["id"],
            "name": r["name"],
            "team": r["team"],
            "positions": r["positions"],
            "status": r["status"],
            "yahoo_rank": number(cells[0]),
            "pct_drafted": number(cells[3]),
            "yahoo_cost": number(cells[4]),
            "yahoo_value": number(cells[5]),
            "adp": adp.get(r["id"], ""),
        })

    DATA.mkdir(exist_ok=True)
    with open(DATA / "yahoo_players.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=players[0].keys())
        writer.writeheader()
        writer.writerows(players)
    print(f"Wrote {len(players)} players to {DATA / 'yahoo_players.csv'}")


if __name__ == "__main__":
    main()
