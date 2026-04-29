#!/usr/bin/env python3
"""
Pull FBref national team stats via soccerdata.
Targets: WC 2026 qualified nations across recent qualifying cycles,
         UEFA Nations League, CONMEBOL qualifiers, etc.

Saves:
  data/raw/fbref/<league>_<season>_<stat_type>.parquet
  data/derived/fbref_team_stats.parquet   (team-level per match stats)
  data/derived/fbref_player_xg.parquet    (player-level xG, national team comps only)

Usage:
  python3 tools/pull_fbref.py
"""
import time, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
import soccerdata as sd

ROOT    = Path(__file__).parent.parent
RAW     = ROOT / "data" / "raw" / "fbref"
DERIVED = ROOT / "data" / "derived"
RAW.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)

# FBref league keys for national team competitions
# These are the competitions soccerdata/FBref supports for national teams
NATIONAL_LEAGUES = [
    # UEFA competitions
    {"league": "UEFA-EURO",            "seasons": [2024]},
    {"league": "UEFA-Nations-League",  "seasons": [2024, 2022]},
    # FIFA World Cup qualifiers by confederation
    {"league": "FIFA-World-Cup",       "seasons": [2022]},
    # CONMEBOL World Cup Qualifying
    {"league": "CONMEBOL-WC-Qual",     "seasons": [2026]},
    # CONCACAF
    {"league": "CONCACAF-Nations-League", "seasons": [2024]},
    # Copa America
    {"league": "Copa-America",         "seasons": [2024]},
    # AFC
    {"league": "AFC-Asian-Cup",        "seasons": [2023]},
]

# Stat types to pull per competition
STAT_TYPES = ["schedule", "shooting", "passing", "defense"]


def pull_league_stats(league: str, season: int) -> dict[str, pd.DataFrame]:
    """Pull all stat types for a league/season. Returns dict of DataFrames."""
    results = {}
    try:
        fbref = sd.FBref(leagues=league, seasons=season)
    except Exception as e:
        print(f"  [warn] could not init FBref for {league} {season}: {e}")
        return results

    for stat in STAT_TYPES:
        cache_path = RAW / f"{league}_{season}_{stat}.parquet"
        if cache_path.exists():
            print(f"  [cache] {league} {season} {stat}")
            try:
                results[stat] = pd.read_parquet(cache_path)
            except Exception:
                pass
            continue

        try:
            if stat == "schedule":
                df = fbref.read_schedule()
            elif stat == "shooting":
                df = fbref.read_team_season_stats(stat_type="shooting")
            elif stat == "passing":
                df = fbref.read_team_season_stats(stat_type="passing")
            elif stat == "defense":
                df = fbref.read_team_season_stats(stat_type="defense")
            else:
                continue

            if df is not None and not df.empty:
                df.to_parquet(cache_path)
                results[stat] = df
                print(f"  [ok] {league} {season} {stat}: {len(df)} rows")
            else:
                print(f"  [empty] {league} {season} {stat}")

            time.sleep(5)  # FBref rate limit

        except Exception as e:
            print(f"  [warn] {league} {season} {stat}: {e}")
            time.sleep(3)

    return results


def build_team_summary(all_shooting: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine shooting stats across competitions into a team summary."""
    if not all_shooting:
        return pd.DataFrame()

    combined = pd.concat(all_shooting, ignore_index=True)

    # Normalize column names (FBref uses MultiIndex sometimes)
    if isinstance(combined.columns, pd.MultiIndex):
        combined.columns = ["_".join(c).strip("_") for c in combined.columns]

    combined.columns = [str(c).lower().replace(" ", "_") for c in combined.columns]
    return combined


def main():
    all_shooting = []
    all_passing  = []

    for target in NATIONAL_LEAGUES:
        league = target["league"]
        for season in target["seasons"]:
            print(f"\n--- {league} {season} ---")
            stats = pull_league_stats(league, season)
            if "shooting" in stats:
                df = stats["shooting"].copy()
                df["_league"]  = league
                df["_season"]  = season
                all_shooting.append(df)
            if "passing" in stats:
                df = stats["passing"].copy()
                df["_league"]  = league
                df["_season"]  = season
                all_passing.append(df)

    # Persist combined team stats
    if all_shooting:
        shooting_df = build_team_summary(all_shooting)
        out = DERIVED / "fbref_team_shooting.parquet"
        shooting_df.to_parquet(out, index=False)
        print(f"\n[saved] fbref_team_shooting.parquet  {len(shooting_df)} rows")

    if all_passing:
        passing_df = build_team_summary(all_passing)
        out = DERIVED / "fbref_team_passing.parquet"
        passing_df.to_parquet(out, index=False)
        print(f"[saved] fbref_team_passing.parquet   {len(passing_df)} rows")

    print("\nDone.")


if __name__ == "__main__":
    main()
