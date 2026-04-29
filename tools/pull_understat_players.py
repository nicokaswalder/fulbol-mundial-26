#!/usr/bin/env python3
"""
Pull club player xG from Understat for national team projection.
Covers: Premier League, Bundesliga, La Liga, Serie A, Ligue 1, RFPL
Seasons: 2022-23, 2023-24, 2024-25

This feeds the "club xG aggregated through projected lineups" approach:
  team_xg_attack ≈ sum(player_xg90 × projected_minutes) for XI

Saves:
  data/raw/understat/<league>_<season>_players.json
  data/derived/understat_player_xg.parquet

Usage:
  python3 tools/pull_understat_players.py
"""
import asyncio, json, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
import aiohttp
import understat

ROOT    = Path(__file__).parent.parent
RAW     = ROOT / "data" / "raw" / "understat"
DERIVED = ROOT / "data" / "derived"
RAW.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)

LEAGUES = ["EPL", "Bundesliga", "La_liga", "Serie_A", "Ligue_1", "RFPL"]
SEASONS = [2022, 2023, 2024]

# WC 2026 participating nations — for filtering/annotating
WC26_NATIONS = {
    "Argentina","Australia","Belgium","Bolivia","Brazil","Canada","Chile","China",
    "Colombia","Costa Rica","Croatia","Czech Republic","Ecuador","England","France",
    "Germany","Ghana","Honduras","Indonesia","Iran","Italy","Jamaica","Japan",
    "Jordan","Malaysia","Mexico","Morocco","Netherlands","New Zealand","Nigeria",
    "Panama","Paraguay","Peru","Poland","Portugal","Saudi Arabia","Senegal",
    "Serbia","Slovakia","Slovenia","South Africa","South Korea","Spain",
    "Switzerland","Turkey","Ukraine","United Arab Emirates","United States",
    "Uruguay","Uzbekistan","Venezuela","Wales",
}


async def pull_league_season(client, league: str, season: int) -> list[dict]:
    cache = RAW / f"{league}_{season}_players.json"
    if cache.exists():
        print(f"  [cache] {league} {season}")
        return json.loads(cache.read_text())

    print(f"  fetching {league} {season}...", end=" ", flush=True)
    try:
        players = await client.get_league_players(league, season)
        cache.write_text(json.dumps(players, indent=2))
        print(f"{len(players)} players")
        return players
    except Exception as e:
        print(f"error: {e}")
        return []


async def main():
    all_rows = []

    async with aiohttp.ClientSession() as session:
        client = understat.Understat(session)
        for league in LEAGUES:
            for season in SEASONS:
                players = await pull_league_season(client, league, season)
                for p in players:
                    row = {
                        "league":         league,
                        "season":         season,
                        "player_id":      p.get("id", ""),
                        "player":         p.get("player_name", ""),
                        "nationality":    p.get("nationality", ""),
                        "team":           p.get("team_title", ""),
                        "position":       p.get("position", ""),
                        "games":          int(p.get("games", 0) or 0),
                        "time":           int(p.get("time", 0) or 0),
                        "goals":          int(p.get("goals", 0) or 0),
                        "assists":        int(p.get("assists", 0) or 0),
                        "shots":          int(p.get("shots", 0) or 0),
                        "key_passes":     int(p.get("key_passes", 0) or 0),
                        "yellow_cards":   int(p.get("yellow_cards", 0) or 0),
                        "red_cards":      int(p.get("red_cards", 0) or 0),
                        "xg":             float(p.get("xG", 0) or 0),
                        "xa":             float(p.get("xA", 0) or 0),
                        "xg_chain":       float(p.get("xGChain", 0) or 0),
                        "xg_buildup":     float(p.get("xGBuildup", 0) or 0),
                    }
                    minutes = row["time"]
                    row["xg_per_90"]   = round(row["xg"] / minutes * 90, 4) if minutes > 0 else 0.0
                    row["xa_per_90"]   = round(row["xa"] / minutes * 90, 4) if minutes > 0 else 0.0
                    row["shots_per_90"] = round(row["shots"] / minutes * 90, 2) if minutes > 0 else 0.0
                    row["xg_chain_per_90"] = round(row["xg_chain"] / minutes * 90, 4) if minutes > 0 else 0.0
                    all_rows.append(row)

                await asyncio.sleep(1.5)

    df = pd.DataFrame(all_rows)

    # Best season per player (highest minutes)
    df_best = (
        df.sort_values("time", ascending=False)
          .drop_duplicates(subset=["player_id", "season"])
    )

    # Aggregate across seasons per player
    agg = (
        df_best.groupby(["player_id", "player", "nationality", "position"])
        .agg(
            total_games=("games", "sum"),
            total_minutes=("time", "sum"),
            total_goals=("goals", "sum"),
            total_assists=("assists", "sum"),
            total_shots=("shots", "sum"),
            total_key_passes=("key_passes", "sum"),
            total_xg=("xg", "sum"),
            total_xa=("xa", "sum"),
            total_xg_chain=("xg_chain", "sum"),
            seasons_covered=("season", "count"),
            last_team=("team", "last"),
        )
        .reset_index()
    )
    agg["xg_per_90"]   = (agg["total_xg"] / agg["total_minutes"].clip(lower=1) * 90).round(4)
    agg["xa_per_90"]   = (agg["total_xa"] / agg["total_minutes"].clip(lower=1) * 90).round(4)
    agg["shots_per_90"] = (agg["total_shots"] / agg["total_minutes"].clip(lower=1) * 90).round(2)

    # Save raw per-season rows
    raw_path = DERIVED / "understat_player_xg_raw.parquet"
    df.to_parquet(raw_path, index=False)

    # Save aggregated
    agg_path = DERIVED / "understat_player_xg.parquet"
    agg.to_parquet(agg_path, index=False)

    print(f"\n[saved] understat_player_xg_raw.parquet  {len(df)} rows")
    print(f"[saved] understat_player_xg.parquet      {len(agg)} unique players\n")

    # Top 25 by xG/90 (min 1000 mins)
    top = agg[agg["total_minutes"] >= 1000].nlargest(25, "xg_per_90")[
        ["player", "nationality", "last_team", "position",
         "total_minutes", "total_xg", "xg_per_90", "xa_per_90", "shots_per_90"]
    ]
    print("Top 25 players by xG/90 (≥1000 mins across 2022-2025):")
    print(top.to_string(index=False))

    # WC26 nations coverage
    wc_players = agg[agg["nationality"].isin(WC26_NATIONS)]
    print(f"\nPlayers from WC 2026 nations: {len(wc_players)}")
    nation_counts = wc_players.groupby("nationality").size().sort_values(ascending=False).head(20)
    print(nation_counts.to_string())


if __name__ == "__main__":
    asyncio.run(main())
