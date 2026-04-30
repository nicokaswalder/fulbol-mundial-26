#!/usr/bin/env python3
"""
Pull WC 2026 preliminary squad lists from Wikipedia.
Saves:
  data/raw/squads/wc2026_squads_raw.json   -- per-country raw tables
  data/derived/wc2026_squads.parquet       -- clean player roster
  data/derived/wc2026_squads.csv           -- same, human-readable

Usage:
  python3 tools/pull_wc2026_squads.py
"""
import json, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import requests
from bs4 import BeautifulSoup
import pandas as pd

ROOT    = Path(__file__).parent.parent
RAW     = ROOT / "data" / "raw" / "squads"
DERIVED = ROOT / "data" / "derived"
RAW.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)

URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"

CONFEDERATION_MAP = {
    "Argentina": "CONMEBOL", "Brazil": "CONMEBOL", "Colombia": "CONMEBOL",
    "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Canada": "CONCACAF", "Curaçao": "CONCACAF", "Haiti": "CONCACAF",
    "Mexico": "CONCACAF", "Panama": "CONCACAF", "United States": "CONCACAF",
    "Australia": "AFC", "Iran": "AFC", "Iraq": "AFC", "Japan": "AFC",
    "Jordan": "AFC", "Qatar": "AFC", "Saudi Arabia": "AFC",
    "South Korea": "AFC", "Uzbekistan": "AFC",
    "Algeria": "CAF", "Cape Verde": "CAF", "DR Congo": "CAF", "Egypt": "CAF",
    "Ghana": "CAF", "Ivory Coast": "CAF", "Morocco": "CAF", "Senegal": "CAF",
    "South Africa": "CAF", "Tunisia": "CAF",
    "New Zealand": "OFC",
    "Austria": "UEFA", "Belgium": "UEFA", "Bosnia and Herzegovina": "UEFA",
    "Croatia": "UEFA", "Czech Republic": "UEFA", "England": "UEFA",
    "France": "UEFA", "Germany": "UEFA", "Netherlands": "UEFA",
    "Norway": "UEFA", "Portugal": "UEFA", "Scotland": "UEFA",
    "Spain": "UEFA", "Sweden": "UEFA", "Switzerland": "UEFA", "Turkey": "UEFA",
}


def fetch_page():
    cache = RAW / "squads_wiki_raw.html"
    if cache.exists():
        print("[cache] Wikipedia squads page")
        return cache.read_text(encoding="utf-8")
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    cache.write_text(r.text, encoding="utf-8")
    print(f"[fetched] {len(r.text):,} bytes")
    return r.text


def parse_squads(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    players = []

    # Each country has an h3 heading followed by a wikitable
    headings = soup.find_all(["h2", "h3"])

    for heading in headings:
        nation = heading.get_text(strip=True).replace("[edit]", "").strip()
        if nation not in CONFEDERATION_MAP:
            continue

        conf = CONFEDERATION_MAP[nation]

        # Find the next wikitable after this heading
        table = heading.find_next("table", class_="wikitable")
        if not table:
            continue

        rows = table.find_all("tr")
        headers = []
        for th in rows[0].find_all(["th", "td"]):
            headers.append(th.get_text(strip=True).lower()
                          .replace(".", "").replace("#", "no")
                          .replace(" ", "_"))

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            row_data = [c.get_text(strip=True) for c in cells]

            # Build dict from headers
            d = {}
            for i, h in enumerate(headers):
                if i < len(row_data):
                    d[h] = row_data[i]

            # Normalise common column names
            player_name = (d.get("name") or d.get("player") or
                          d.get("name_1") or "")
            position    = (d.get("pos") or d.get("position") or "")
            club        = (d.get("club") or d.get("club_1") or "")
            caps        = (d.get("caps") or d.get("cap") or "")
            dob         = (d.get("date_of_birth_(age)") or
                          d.get("date_of_birth") or d.get("dob") or "")
            no          = (d.get("no") or d.get("kit_no") or "")

            if not player_name or player_name.lower() in ("name", "player", ""):
                continue

            players.append({
                "nation":       nation,
                "confederation": conf,
                "shirt_no":     no,
                "position":     position,
                "player":       player_name,
                "dob":          dob,
                "caps":         caps,
                "club":         club,
            })

        print(f"  {nation:<30} {len([p for p in players if p['nation']==nation]):>3} players")

    return players


def main():
    print("Fetching WC 2026 squad page from Wikipedia...")
    html = fetch_page()

    print("\nParsing squads...")
    players = parse_squads(html)

    # Save raw
    (RAW / "wc2026_squads_raw.json").write_text(
        json.dumps(players, indent=2, ensure_ascii=False))

    # Build DataFrame
    df = pd.DataFrame(players)
    df["caps"] = pd.to_numeric(df["caps"].str.replace(",", ""), errors="coerce")

    # Save
    df.to_parquet(DERIVED / "wc2026_squads.parquet", index=False)
    df.to_csv(DERIVED / "wc2026_squads.csv", index=False)

    print(f"\n{'='*55}")
    print(f"DONE — {len(df)} players across {df['nation'].nunique()} nations")
    print(f"{'='*55}")

    # Summary by confederation
    summary = (df.groupby("confederation")
                 .agg(nations=("nation","nunique"), players=("player","count"))
                 .reset_index())
    print(summary.to_string(index=False))

    print(f"\nSample — first 5 entries:")
    print(df[["nation","position","player","club","caps"]].head(5).to_string(index=False))

    print(f"\nSaved → data/derived/wc2026_squads.parquet")
    print(f"Saved → data/derived/wc2026_squads.csv")


if __name__ == "__main__":
    main()
