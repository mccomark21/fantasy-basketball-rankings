"""Download NBA rosters and the regular-season schedule from ESPN.

Run this script again when rosters change (trades, signings).
Output:
  data/rosters.csv   - one row for each player on an NBA roster
  data/schedule.csv  - one row for each team in each regular-season game
"""
import csv
import json
import time
import urllib.request
from datetime import datetime, timedelta

from common import DATA, load_config

API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def get_json(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.load(resp)
        except Exception as err:
            if attempt == 2:
                raise RuntimeError(f"Download failed: {url}") from err
            time.sleep(2)


def local_date(utc_text):
    # ESPN gives UTC times. All NBA games start after 18:00 UTC, so
    # 6 hours earlier gives the US calendar date of the game.
    utc = datetime.strptime(utc_text, "%Y-%m-%dT%H:%MZ")
    return (utc - timedelta(hours=6)).date().isoformat()


def main():
    season = load_config()["league"]["espn_season"]
    DATA.mkdir(exist_ok=True)

    league = get_json(f"{API}/teams")
    teams = [t["team"] for t in league["sports"][0]["leagues"][0]["teams"]]

    rosters, games = [], []
    for team in teams:
        abbr = team["abbreviation"]
        roster = get_json(f"{API}/teams/{team['id']}/roster")
        for athlete in roster["athletes"]:
            rosters.append({"espn_name": athlete["fullName"], "team": abbr})

        schedule = get_json(f"{API}/teams/{team['id']}/schedule?season={season}&seasontype=2")
        for event in schedule["events"]:
            sides = event["competitions"][0]["competitors"]
            opponent = next(s["team"]["abbreviation"] for s in sides if s["team"]["id"] != team["id"])
            games.append({"date": local_date(event["date"]), "team": abbr, "opponent": opponent})
        print(f"{abbr}: {len(roster['athletes'])} players, {len(schedule['events'])} games")

    for name, rows in (("rosters.csv", rosters), ("schedule.csv", games)):
        with open(DATA / name, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print(f"Wrote {len(rosters)} players and {len(games)} team-games to {DATA}")


if __name__ == "__main__":
    main()
