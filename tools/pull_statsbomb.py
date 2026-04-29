#!/usr/bin/env python3
"""
Pull StatsBomb open data for national team competitions.
Targets: FIFA World Cup 2022, UEFA Euro 2024, Copa America 2024.

Saves:
  data/raw/statsbomb/<slug>/matches.json
  data/raw/statsbomb/<slug>/events/<match_id>.json
  data/derived/statsbomb_team_xg.parquet   (team-level xG summary per match)
  data/derived/statsbomb_player_xg.parquet (player-level xG across all comps)

Usage:
  python3 tools/pull_statsbomb.py
"""
import json, os, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
from statsbombpy import sb

ROOT = Path(__file__).parent.parent
RAW  = ROOT / "data" / "raw" / "statsbomb"
DERIVED = ROOT / "data" / "derived"
DERIVED.mkdir(parents=True, exist_ok=True)

# National team competitions in the free open data
TARGETS = [
    {"slug": "wc2022",       "competition_id": 43,  "season_id": 106, "label": "FIFA World Cup 2022"},
    {"slug": "euro2024",     "competition_id": 55,  "season_id": 282, "label": "UEFA Euro 2024"},
    {"slug": "copa2024",     "competition_id": 223, "season_id": 282, "label": "Copa America 2024"},
]

SHOT_TYPES = {"Shot"}


def pull_matches(comp_id, season_id):
    return sb.matches(competition_id=comp_id, season_id=season_id)


def pull_events(match_id):
    return sb.events(match_id=match_id)


def extract_team_xg(events_df, match_row):
    """Return two rows (home, away) with shot/xG/pass/pressure aggregates."""
    home = match_row["home_team"]
    away = match_row["away_team"]
    rows = []
    for team, is_home in [(home, True), (away, False)]:
        tm = events_df[events_df["team"] == team]
        shots = tm[tm["type"] == "Shot"]
        passes = tm[tm["type"] == "Pass"]
        pressures = tm[tm["type"] == "Pressure"]
        carries = tm[tm["type"] == "Carry"]

        xg_total = shots["shot_statsbomb_xg"].sum() if "shot_statsbomb_xg" in shots.columns else 0.0
        xg_total = float(xg_total) if pd.notna(xg_total) else 0.0

        # xA from passes that led to shots (key passes)
        xa = 0.0
        if "pass_goal_assist" in passes.columns:
            xa = float(passes["pass_goal_assist"].sum()) if pd.notna(passes["pass_goal_assist"].sum()) else 0.0

        shots_on_target = 0
        if "shot_outcome" in shots.columns:
            shots_on_target = int(shots["shot_outcome"].isin(["Goal", "Saved", "Saved To Post"]).sum())

        prog_passes = 0
        if "pass_length" in passes.columns and "pass_end_location" in passes.columns:
            try:
                prog_passes = int((passes["pass_length"] > 10).sum())
            except Exception:
                pass

        rows.append({
            "competition": match_row.get("competition", ""),
            "season": match_row.get("season", ""),
            "match_id": int(match_row["match_id"]),
            "match_date": str(match_row.get("match_date", "")),
            "team": team,
            "opponent": away if is_home else home,
            "is_home": is_home,
            "goals": int(match_row["home_score"] if is_home else match_row["away_score"]),
            "goals_conceded": int(match_row["away_score"] if is_home else match_row["home_score"]),
            "xg": round(xg_total, 4),
            "xa": round(xa, 4),
            "shots": len(shots),
            "shots_on_target": shots_on_target,
            "passes": len(passes),
            "pressures": len(pressures),
            "carries": len(carries),
        })
    return rows


def extract_player_xg(events_df, match_row):
    """Return per-player shot rows with xG."""
    shots = events_df[events_df["type"] == "Shot"].copy()
    if shots.empty:
        return []
    rows = []
    for _, s in shots.iterrows():
        rows.append({
            "competition": match_row.get("competition", ""),
            "season": match_row.get("season", ""),
            "match_id": int(match_row["match_id"]),
            "match_date": str(match_row.get("match_date", "")),
            "team": s.get("team", ""),
            "player": s.get("player", ""),
            "minute": s.get("minute", 0),
            "xg": round(float(s["shot_statsbomb_xg"]) if pd.notna(s.get("shot_statsbomb_xg")) else 0.0, 4),
            "outcome": s.get("shot_outcome", ""),
            "technique": s.get("shot_technique", ""),
            "body_part": s.get("shot_body_part", ""),
        })
    return rows


def main():
    all_team_xg = []
    all_player_xg = []

    for target in TARGETS:
        slug = target["slug"]
        label = target["label"]
        comp_dir = RAW / slug
        events_dir = comp_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")

        # Matches
        matches_path = comp_dir / "matches.json"
        if matches_path.exists():
            print(f"  [cache] matches.json already exists, loading...")
            matches = pd.read_json(matches_path)
        else:
            print(f"  Pulling matches...")
            matches = pull_matches(target["competition_id"], target["season_id"])
            matches.to_json(matches_path, orient="records", indent=2)
            print(f"  Saved {len(matches)} matches → {matches_path.relative_to(ROOT)}")

        print(f"  {len(matches)} matches found")

        # Enrich match rows with competition/season labels
        matches["competition"] = label
        matches["season"] = target["slug"]

        # Events per match
        for _, match_row in matches.iterrows():
            mid = int(match_row["match_id"])
            ev_path = events_dir / f"{mid}.json"

            if ev_path.exists():
                events = pd.read_json(ev_path)
            else:
                try:
                    events = pull_events(mid)
                    events.to_json(ev_path, orient="records")
                except Exception as e:
                    print(f"  [warn] match {mid} failed: {e}")
                    continue

            home = match_row.get("home_team", "?")
            away = match_row.get("away_team", "?")
            hs   = match_row.get("home_score", "?")
            as_  = match_row.get("away_score", "?")
            print(f"  {home} {hs}-{as_} {away}  ({len(events)} events)")

            team_rows = extract_team_xg(events, match_row)
            all_team_xg.extend(team_rows)

            player_rows = extract_player_xg(events, match_row)
            all_player_xg.extend(player_rows)

    # Save derived parquets
    team_df = pd.DataFrame(all_team_xg)
    player_df = pd.DataFrame(all_player_xg)

    team_path = DERIVED / "statsbomb_team_xg.parquet"
    player_path = DERIVED / "statsbomb_player_xg.parquet"

    team_df.to_parquet(team_path, index=False)
    player_df.to_parquet(player_path, index=False)

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  Team xG rows:   {len(team_df)}  → {team_path.relative_to(ROOT)}")
    print(f"  Player xG rows: {len(player_df)} → {player_path.relative_to(ROOT)}")
    print(f"\n  Top teams by avg xG per match:")
    avg = team_df.groupby("team")["xg"].mean().sort_values(ascending=False).head(10)
    for team, val in avg.items():
        print(f"    {team:<30} {val:.3f} xG/game")


if __name__ == "__main__":
    main()
