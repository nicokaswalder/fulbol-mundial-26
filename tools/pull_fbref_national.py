#!/usr/bin/env python3
"""
Scrape FBref national team stats directly (bypassing soccerdata).
Targets: WC 2022, UEFA Nations League 2024-25, UEFA Euro 2024,
         Copa America 2024, CONMEBOL WC Qualifiers.

Saves:
  data/raw/fbref/<comp_slug>_<stat_type>.parquet
  data/derived/fbref_national_shooting.parquet
  data/derived/fbref_national_passing.parquet
  data/derived/fbref_national_possession.parquet

Usage:
  python3 tools/pull_fbref_national.py
"""
import time, warnings, requests
from pathlib import Path
from io import StringIO

warnings.filterwarnings("ignore")
import pandas as pd

ROOT    = Path(__file__).parent.parent
RAW     = ROOT / "data" / "raw" / "fbref"
DERIVED = ROOT / "data" / "derived"
RAW.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# FBref national team stat pages
# Format: (slug, label, url_base, stat_suffix_map)
# FBref competition IDs for national team comps:
#   1  = FIFA World Cup
#   676 = UEFA Euro
#   685 = Copa America
#   765 = UEFA Nations League
#   780 = CONMEBOL WC Qualifying

COMPETITIONS = [
    {
        "slug":  "wc2022",
        "label": "FIFA World Cup 2022",
        "urls": {
            "shooting":   "https://fbref.com/en/comps/1/2022/shooting/2022-FIFA-World-Cup-Stats",
            "passing":    "https://fbref.com/en/comps/1/2022/passing/2022-FIFA-World-Cup-Stats",
            "possession": "https://fbref.com/en/comps/1/2022/possession/2022-FIFA-World-Cup-Stats",
            "defense":    "https://fbref.com/en/comps/1/2022/defense/2022-FIFA-World-Cup-Stats",
        }
    },
    {
        "slug":  "euro2024",
        "label": "UEFA Euro 2024",
        "urls": {
            "shooting":   "https://fbref.com/en/comps/676/2024/shooting/2024-UEFA-European-Championship-Stats",
            "passing":    "https://fbref.com/en/comps/676/2024/passing/2024-UEFA-European-Championship-Stats",
            "possession": "https://fbref.com/en/comps/676/2024/possession/2024-UEFA-European-Championship-Stats",
            "defense":    "https://fbref.com/en/comps/676/2024/defense/2024-UEFA-European-Championship-Stats",
        }
    },
    {
        "slug":  "copa2024",
        "label": "Copa America 2024",
        "urls": {
            "shooting":   "https://fbref.com/en/comps/685/2024/shooting/2024-Copa-America-Stats",
            "passing":    "https://fbref.com/en/comps/685/2024/passing/2024-Copa-America-Stats",
            "possession": "https://fbref.com/en/comps/685/2024/possession/2024-Copa-America-Stats",
            "defense":    "https://fbref.com/en/comps/685/2024/defense/2024-Copa-America-Stats",
        }
    },
    {
        "slug":  "nations_league_2024",
        "label": "UEFA Nations League 2024-25",
        "urls": {
            "shooting":   "https://fbref.com/en/comps/765/2024-2025/shooting/2024-2025-UEFA-Nations-League-Stats",
            "passing":    "https://fbref.com/en/comps/765/2024-2025/passing/2024-2025-UEFA-Nations-League-Stats",
            "possession": "https://fbref.com/en/comps/765/2024-2025/possession/2024-2025-UEFA-Nations-League-Stats",
        }
    },
    {
        "slug":  "conmebol_wc_qual",
        "label": "CONMEBOL WC Qualifying 2026",
        "urls": {
            "shooting":   "https://fbref.com/en/comps/780/2026/shooting/2026-World-Cup-Qualifying-CONMEBOL-Stats",
            "passing":    "https://fbref.com/en/comps/780/2026/passing/2026-World-Cup-Qualifying-CONMEBOL-Stats",
            "possession": "https://fbref.com/en/comps/780/2026/possession/2026-World-Cup-Qualifying-CONMEBOL-Stats",
        }
    },
]


def scrape_stat_page(url: str):
    """Scrape a FBref stat page and return the squad stats table."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}")
            return None
        tables = pd.read_html(StringIO(resp.text))
        # FBref squad stats are usually the largest table or the one with 'Squad' col
        for t in tables:
            cols = [str(c).lower() for c in t.columns.get_level_values(-1)]
            if "squad" in cols:
                # Flatten MultiIndex columns
                if isinstance(t.columns, pd.MultiIndex):
                    t.columns = ["_".join(str(c) for c in col if c != "").strip("_")
                                 for col in t.columns]
                t.columns = [str(c).lower().replace(" ","_").replace("/","_per_")
                             for c in t.columns]
                # Drop rows that are section headers ("vs. opponents" separator)
                t = t[t["squad"].notna()].copy()
                t = t[~t["squad"].str.lower().str.contains("opponent|squad", na=False)].copy()
                return t
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


def main():
    all_shooting  = []
    all_passing   = []
    all_possession = []
    all_defense   = []

    for comp in COMPETITIONS:
        slug  = comp["slug"]
        label = comp["label"]
        print(f"\n--- {label} ---")

        for stat_type, url in comp["urls"].items():
            cache = RAW / f"{slug}_{stat_type}.parquet"
            if cache.exists():
                print(f"  [cache] {stat_type}")
                df = pd.read_parquet(cache)
            else:
                print(f"  scraping {stat_type}...", end=" ", flush=True)
                df = scrape_stat_page(url)
                if df is not None and not df.empty:
                    df["_competition"] = label
                    df["_slug"] = slug
                    df.to_parquet(cache)
                    print(f"{len(df)} rows")
                else:
                    print("no data")
                    df = None
                time.sleep(4)

            if df is None:
                continue

            df["_competition"] = label
            df["_slug"] = slug

            if stat_type == "shooting":
                all_shooting.append(df)
            elif stat_type == "passing":
                all_passing.append(df)
            elif stat_type == "possession":
                all_possession.append(df)
            elif stat_type == "defense":
                all_defense.append(df)

    # Save combined derived files
    for name, frames, path in [
        ("shooting",   all_shooting,   DERIVED/"fbref_national_shooting.parquet"),
        ("passing",    all_passing,    DERIVED/"fbref_national_passing.parquet"),
        ("possession", all_possession, DERIVED/"fbref_national_possession.parquet"),
        ("defense",    all_defense,    DERIVED/"fbref_national_defense.parquet"),
    ]:
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined.to_parquet(path, index=False)
            print(f"\n[saved] {path.name}  {len(combined)} rows")

            if name == "shooting":
                print("\nSample shooting stats (xG, npxG, shots):")
                xg_cols = [c for c in combined.columns if "xg" in c.lower() or "squad" in c.lower() or "sh" in c.lower()][:8]
                if xg_cols:
                    print(combined[xg_cols].head(10).to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
