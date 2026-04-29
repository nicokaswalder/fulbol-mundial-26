#!/usr/bin/env python3
"""
Aggregate StatsBomb national team event data into player-level stats.

Reads from: data/raw/statsbomb/<slug>/events/<match_id>.json
Writes:
  data/derived/sb_player_stats.parquet   -- per-player per-match breakdown
  data/derived/sb_player_summary.parquet -- aggregated career stats (national team only)
  data/derived/sb_team_stats.parquet     -- team-level stats per match (expanded from pull_statsbomb)

Usage:
  python3 tools/aggregate_statsbomb_players.py
"""
import json, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT    = Path(__file__).parent.parent
RAW     = ROOT / "data" / "raw" / "statsbomb"
DERIVED = ROOT / "data" / "derived"

COMPS = [
    {"slug": "wc2022",   "label": "FIFA World Cup 2022"},
    {"slug": "euro2024", "label": "UEFA Euro 2024"},
    {"slug": "copa2024", "label": "Copa America 2024"},
]


def location_to_xy(loc):
    if isinstance(loc, list) and len(loc) == 2:
        return float(loc[0]), float(loc[1])
    return None, None


def is_progressive_carry(start, end):
    """A carry is progressive if it advances the ball ≥10 yards toward goal."""
    sx, sy = location_to_xy(start)
    ex, ey = location_to_xy(end)
    if sx is None or ex is None:
        return False
    return (ex - sx) >= 9.14  # 10 yards in StatsBomb 120x80 pitch coords


def is_progressive_pass(start, end):
    sx, _ = location_to_xy(start)
    ex, _ = location_to_xy(end)
    if sx is None or ex is None:
        return False
    return (ex - sx) >= 9.14


def passes_into_final_third(end_loc):
    ex, _ = location_to_xy(end_loc)
    if ex is None:
        return False
    return ex >= 80.0


def process_match(match_id: int, match_row: dict, slug: str, label: str) -> list[dict]:
    ev_path = RAW / slug / "events" / f"{match_id}.json"
    if not ev_path.exists():
        return []

    events = pd.read_json(ev_path)
    home = match_row.get("home_team", "")
    away = match_row.get("away_team", "")
    date = str(match_row.get("match_date", ""))

    player_stats = {}

    def get_player(team, player_name):
        key = (team, player_name)
        if key not in player_stats:
            player_stats[key] = {
                "competition": label,
                "season": slug,
                "match_id": match_id,
                "match_date": date,
                "team": team,
                "opponent": away if team == home else home,
                "is_home": team == home,
                "player": player_name,
                # Shooting
                "shots": 0, "shots_on_target": 0, "goals": 0,
                "xg": 0.0, "xg_np": 0.0,
                # Passing
                "passes": 0, "passes_completed": 0,
                "key_passes": 0, "shot_assists": 0,
                "crosses": 0, "crosses_completed": 0,
                "progressive_passes": 0, "passes_final_third": 0,
                "passes_into_penalty_area": 0,
                "long_passes": 0, "long_passes_completed": 0,
                "switches": 0,
                # Carrying
                "carries": 0, "progressive_carries": 0,
                "carries_into_final_third": 0,
                # Pressing / defense
                "pressures": 0, "pressure_regains": 0,
                "tackles": 0, "interceptions": 0,
                "blocks": 0, "clearances": 0,
                "duels": 0, "duels_won": 0,
                "aerial_duels": 0, "aerial_duels_won": 0,
                # Misc
                "fouls_committed": 0, "fouls_won": 0,
                "dribbles": 0, "dribbles_completed": 0,
                "ball_recoveries": 0,
                "minutes_played": 0,
            }
        return player_stats[key]

    for _, ev in events.iterrows():
        etype = ev.get("type", "")
        team  = ev.get("team", "")
        pname = ev.get("player", "")
        if not pname or not team:
            continue
        p = get_player(team, pname)

        if etype == "Shot":
            xg_val = float(ev.get("shot_statsbomb_xg", 0) or 0)
            outcome = ev.get("shot_outcome", "")
            technique = ev.get("shot_technique", "")
            p["shots"] += 1
            p["xg"] += xg_val
            if technique != "Penalty":
                p["xg_np"] += xg_val
            if outcome in ("Goal", "Saved", "Saved To Post", "Saved Off Target"):
                p["shots_on_target"] += 1
            if outcome == "Goal":
                p["goals"] += 1

        elif etype == "Pass":
            p["passes"] += 1
            outcome = ev.get("pass_outcome", "")
            if pd.isna(outcome) or outcome == "":
                p["passes_completed"] += 1
            length = ev.get("pass_length", 0) or 0
            if length >= 32:  # ~35 yards
                p["long_passes"] += 1
                if pd.isna(outcome) or outcome == "":
                    p["long_passes_completed"] += 1
            if ev.get("pass_shot_assist"):
                p["key_passes"] += 1
            if ev.get("pass_goal_assist"):
                p["shot_assists"] += 1
            if ev.get("pass_cross"):
                p["crosses"] += 1
                if pd.isna(outcome) or outcome == "":
                    p["crosses_completed"] += 1
            if ev.get("pass_switch"):
                p["switches"] += 1
            end_loc = ev.get("pass_end_location")
            start_loc = ev.get("location")
            if is_progressive_pass(start_loc, end_loc):
                p["progressive_passes"] += 1
            if passes_into_final_third(end_loc):
                p["passes_final_third"] += 1
            ex, ey = location_to_xy(end_loc)
            if ex is not None and ex >= 102 and 18 <= ey <= 62:
                p["passes_into_penalty_area"] += 1

        elif etype == "Carry":
            p["carries"] += 1
            start_loc = ev.get("location")
            end_loc   = ev.get("carry_end_location")
            if is_progressive_carry(start_loc, end_loc):
                p["progressive_carries"] += 1
            ex, _ = location_to_xy(end_loc)
            if ex is not None and ex >= 80:
                p["carries_into_final_third"] += 1

        elif etype == "Pressure":
            p["pressures"] += 1
            if ev.get("pressure_regain_possession"):
                p["pressure_regains"] += 1

        elif etype == "Duel":
            dtype = ev.get("duel_type", "")
            dout  = ev.get("duel_outcome", "")
            p["duels"] += 1
            if dout in ("Won", "Success In Play", "Success Out"):
                p["duels_won"] += 1
            if dtype == "Aerial Lost" or "Aerial" in str(dtype):
                p["aerial_duels"] += 1
                if dout in ("Won", "Success In Play"):
                    p["aerial_duels_won"] += 1

        elif etype == "Tackle":
            p["tackles"] += 1

        elif etype == "Interception":
            p["interceptions"] += 1

        elif etype == "Block":
            p["blocks"] += 1

        elif etype == "Clearance":
            p["clearances"] += 1

        elif etype == "Foul Committed":
            p["fouls_committed"] += 1

        elif etype == "Foul Won":
            p["fouls_won"] += 1

        elif etype == "Dribble":
            p["dribbles"] += 1
            if ev.get("dribble_outcome") == "Complete":
                p["dribbles_completed"] += 1

        elif etype == "Ball Recovery":
            p["ball_recoveries"] += 1

    # Estimate minutes from last event timestamp per player
    for (team, pname), stats in player_stats.items():
        player_events = events[events["player"] == pname]
        if not player_events.empty:
            last_min = int(player_events["minute"].max())
            first_min = int(player_events["minute"].min())
            stats["minutes_played"] = max(1, last_min - first_min + 1)

    return list(player_stats.values())


def main():
    all_player_match_stats = []

    for comp in COMPS:
        slug  = comp["slug"]
        label = comp["label"]
        matches_path = RAW / slug / "matches.json"
        if not matches_path.exists():
            print(f"[skip] {slug} — no matches.json")
            continue

        matches = pd.read_json(matches_path)
        print(f"\n{label}: {len(matches)} matches")

        for _, row in matches.iterrows():
            mid = int(row["match_id"])
            rows = process_match(mid, row.to_dict(), slug, label)
            all_player_match_stats.extend(rows)
            h, a = row.get("home_team","?"), row.get("away_team","?")
            print(f"  {h} vs {a}  — {len(rows)} player records")

    df = pd.DataFrame(all_player_match_stats)

    # Per-match player stats
    per_match_path = DERIVED / "sb_player_stats.parquet"
    df.to_parquet(per_match_path, index=False)
    print(f"\n[saved] sb_player_stats.parquet  {len(df)} rows")

    # Aggregate across all national team appearances
    agg_cols = [c for c in df.columns if c not in
                ("competition","season","match_id","match_date","team","opponent","is_home","player")]
    summary = (
        df.groupby(["player", "team"])[agg_cols]
        .sum()
        .reset_index()
    )
    # Add per-90 xG
    summary["matches"] = df.groupby(["player","team"])["match_id"].nunique().values
    summary["xg_per_90"] = (summary["xg"] / summary["minutes_played"].clip(lower=1) * 90).round(4)
    summary["xg_np_per_90"] = (summary["xg_np"] / summary["minutes_played"].clip(lower=1) * 90).round(4)
    summary["shots_per_90"] = (summary["shots"] / summary["minutes_played"].clip(lower=1) * 90).round(2)
    summary["key_passes_per_90"] = (summary["key_passes"] / summary["minutes_played"].clip(lower=1) * 90).round(2)
    summary["prog_passes_per_90"] = (summary["progressive_passes"] / summary["minutes_played"].clip(lower=1) * 90).round(2)
    summary["prog_carries_per_90"] = (summary["progressive_carries"] / summary["minutes_played"].clip(lower=1) * 90).round(2)
    summary["pressures_per_90"] = (summary["pressures"] / summary["minutes_played"].clip(lower=1) * 90).round(2)
    summary["crosses_per_90"] = (summary["crosses"] / summary["minutes_played"].clip(lower=1) * 90).round(2)
    summary["pass_completion_pct"] = (summary["passes_completed"] / summary["passes"].clip(lower=1) * 100).round(1)

    summary_path = DERIVED / "sb_player_summary.parquet"
    summary.to_parquet(summary_path, index=False)
    print(f"[saved] sb_player_summary.parquet {len(summary)} unique players\n")

    # Top attackers by national team xG
    print("Top 20 players by total national team xG:")
    top = summary.nlargest(20, "xg")[["player","team","matches","xg","xg_np","shots","goals","xg_per_90","key_passes_per_90","crosses_per_90"]]
    print(top.to_string(index=False))

    print("\nTop teams by avg xG/90 across all comps (from player sum):")
    team_xg = summary.groupby("team")[["xg","matches"]].sum()
    team_xg["xg_per_match"] = (team_xg["xg"] / team_xg["matches"].clip(lower=1)).round(3)
    print(team_xg.nlargest(15,"xg_per_match")["xg_per_match"].to_string())


if __name__ == "__main__":
    main()
