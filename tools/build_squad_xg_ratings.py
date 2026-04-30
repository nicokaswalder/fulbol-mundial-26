#!/usr/bin/env python3
"""
Build WC 2026 likely squad xG ratings by joining:
  - StatsBomb national team player history (WC22 / Euro24 / Copa24)
  - Understat 2024-25 club xG (most recent season)

For each nation, produces a ranked player list with:
  - national team xG/90 (from StatsBomb tournaments)
  - club xG/90 2024-25 (from Understat — current form)
  - blended rating = 0.4 * national_xg90 + 0.6 * club_xg90

Saves:
  data/derived/squad_xg_ratings.parquet
  data/derived/squad_xg_ratings.csv
  data/derived/team_attack_ratings.parquet   (aggregated team-level)

Usage:
  python3 tools/build_squad_xg_ratings.py
"""
import warnings
from pathlib import Path
from rapidfuzz import fuzz, process

warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

ROOT    = Path(__file__).parent.parent
DERIVED = ROOT / "data" / "derived"


def simplify_name(name: str) -> str:
    """Strip accents and common suffixes for fuzzy matching."""
    import unicodedata
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Take last 2 words (first + last usually enough)
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}".lower()
    return name.lower()


def fuzzy_match(sb_name: str, und_names: list, threshold: int = 75):
    """Return best Understat name match above threshold, or None."""
    simple_sb = simplify_name(sb_name)
    result = process.extractOne(simple_sb, und_names, scorer=fuzz.token_sort_ratio)
    if result and result[1] >= threshold:
        return result[0]
    return None


def main():
    # Load data
    sb  = pd.read_parquet(DERIVED / "sb_player_summary.parquet")
    und_raw = pd.read_parquet(DERIVED / "understat_player_xg_raw.parquet")

    # Most recent Understat season (2024-25)
    und = und_raw[und_raw["season"] == 2024].copy()
    und = und[und["time"] >= 200]  # min 200 minutes to be meaningful

    # Build simplified name lookup for fuzzy matching
    und["name_simple"] = und["player"].apply(simplify_name)
    und_names = und["name_simple"].tolist()
    und_lookup = dict(zip(und["name_simple"], und.index))

    print(f"StatsBomb national team players: {len(sb)}")
    print(f"Understat 2024-25 players (≥200 min): {len(und)}")
    print("\nMatching players...")

    rows = []
    matched = 0
    unmatched = 0

    for _, player in sb.iterrows():
        sb_name   = player["player"]
        nation    = player["team"]
        nat_xg90  = float(player["xg_per_90"])
        nat_mins  = int(player["minutes_played"])
        nat_matches = int(player["matches"])

        # Try fuzzy match to Understat
        simple_sb = simplify_name(sb_name)
        best_match = fuzzy_match(sb_name, und_names)

        club_xg90  = np.nan
        club_xa90  = np.nan
        club_mins  = 0
        club_team  = ""
        club_league = ""
        club_position = ""

        if best_match and best_match in und_lookup:
            idx = und_lookup[best_match]
            club_row = und.loc[idx]
            club_xg90    = float(club_row["xg_per_90"])
            club_xa90    = float(club_row["xa_per_90"])
            club_mins    = int(club_row["time"])
            club_team    = str(club_row["team"])
            club_league  = str(club_row["league"])
            club_position = str(club_row["position"])
            matched += 1
        else:
            unmatched += 1

        # Blended rating: weight club form more if available
        if not np.isnan(club_xg90):
            blended_xg90 = 0.4 * nat_xg90 + 0.6 * club_xg90
        else:
            blended_xg90 = nat_xg90

        rows.append({
            "nation":          nation,
            "player":          sb_name,
            "position":        club_position or "",
            "club":            club_team,
            "league":          club_league,
            # National team stats
            "nat_matches":     nat_matches,
            "nat_minutes":     nat_mins,
            "nat_xg_per_90":   round(nat_xg90, 4),
            "nat_shots_per_90": round(float(player["shots_per_90"]), 3),
            "nat_key_passes_per_90": round(float(player["key_passes_per_90"]), 3),
            "nat_prog_passes_per_90": round(float(player["prog_passes_per_90"]), 3),
            "nat_prog_carries_per_90": round(float(player["prog_carries_per_90"]), 3),
            "nat_pressures_per_90": round(float(player["pressures_per_90"]), 3),
            # Club 2024-25
            "club_minutes_2425": club_mins,
            "club_xg_per_90":  round(club_xg90, 4) if not np.isnan(club_xg90) else None,
            "club_xa_per_90":  round(club_xa90, 4) if not np.isnan(club_xa90) else None,
            # Blended
            "blended_xg90":    round(blended_xg90, 4),
            "found_in_understat": not np.isnan(club_xg90),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["nation", "blended_xg90"], ascending=[True, False])

    print(f"  Matched to Understat: {matched}/{len(sb)} ({matched/len(sb):.1%})")
    print(f"  Not found: {unmatched}")

    # Save player-level
    df.to_parquet(DERIVED / "squad_xg_ratings.parquet", index=False)
    df.to_csv(DERIVED / "squad_xg_ratings.csv", index=False)

    # ── TEAM-LEVEL ATTACK/DEFENCE RATINGS ─────────────────────────────────────
    # Proxy for team attack = avg blended xG/90 of top 5 attacking players
    # Proxy for team defence = pressures/90 of top 8 players
    team_rows = []
    for nation, grp in df.groupby("nation"):
        top_attack = grp.nlargest(5, "blended_xg90")
        top_press  = grp.nlargest(8, "nat_pressures_per_90")

        team_rows.append({
            "nation": nation,
            "squad_players": len(grp),
            "matched_to_club": int(grp["found_in_understat"].sum()),
            # Attack proxy
            "attack_rating":    round(top_attack["blended_xg90"].mean(), 4),
            "attack_nat_only":  round(top_attack["nat_xg_per_90"].mean(), 4),
            "attack_club_only": round(top_attack["club_xg_per_90"].mean(), 4),
            # Creative proxy
            "creativity_rating": round(grp["nat_key_passes_per_90"].mean(), 4),
            "progressive_pass_rating": round(grp["nat_prog_passes_per_90"].mean(), 4),
            # Pressing proxy
            "press_intensity":  round(top_press["nat_pressures_per_90"].mean(), 4),
        })

    team_df = pd.DataFrame(team_rows).sort_values("attack_rating", ascending=False)
    team_df.to_parquet(DERIVED / "team_attack_ratings.parquet", index=False)

    # Print results
    print(f"\n{'='*70}")
    print(f"TEAM ATTACK RATINGS (top 16 by attack rating)")
    print(f"{'='*70}")
    print(f"{'Nation':<25} {'Attack':>8} {'Creativity':>11} {'Press':>7} {'Players':>8} {'Matched':>8}")
    print("-" * 70)
    for _, r in team_df.head(16).iterrows():
        print(f"  {r['nation']:<23} {r['attack_rating']:>8.4f} {r['creativity_rating']:>11.4f} "
              f"{r['press_intensity']:>7.4f} {r['squad_players']:>8} {r['matched_to_club']:>8}")

    print(f"\n{'='*70}")
    print(f"SAMPLE TOP PLAYERS — Argentina")
    arg = df[df["nation"]=="Argentina"].head(8)
    print(arg[["player","club","nat_xg_per_90","club_xg_per_90","blended_xg90"]].to_string(index=False))

    print(f"\nSaved → data/derived/squad_xg_ratings.parquet ({len(df)} player-nation rows)")
    print(f"Saved → data/derived/team_attack_ratings.parquet ({len(team_df)} teams)")


if __name__ == "__main__":
    main()
