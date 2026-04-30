---
title: "feat: WC2026 Match Prediction Dashboard CSV"
type: feat
status: active
date: 2026-04-28
---

# feat: WC2026 Match Prediction Dashboard CSV

## Overview

Add a `tools/build_dashboard.py` script that joins all model prediction CSVs + Kalshi snapshot into a single wide-format CSV (`results/dashboard/YYYY-MM-DD.csv`). Each row is one match × outcome with every model's probability, Kalshi's probability, and a computed `opportunity` flag derived from the WC2022 backtest golden-zone rule. Also append a rolling Kalshi history log to enable line-movement queries.

## Problem Frame

The pipeline already produces per-model CSVs (`results/<model>/<date>/predictions.csv`) and a Kalshi snapshot (`data/derived/kalshi_snapshot_<date>.csv`), but no step assembles them into a single queryable table. The existing `comparison.csv` in `results/comparisons/` only contains the 3 base models (no ensemble column) and no opportunity flag. Opening a CSV in Google Sheets is the desired end-state — no app or notebook needed.

## Requirements Trace

- R1. Single CSV with all WC2026 matches × outcomes, one row per (match, outcome)
- R2. Columns for each model's probability: elo-baseline, poisson-goals, form-last-10, ensemble-e3, ensemble-v2 (computed)
- R3. Kalshi probability column (where available)
- R4. `opportunity` column: ✅ when golden-zone AND edge > 3pp, else ❌ or blank when Kalshi unavailable
- R5. Kalshi prices appended to a history file on each run (for line-movement tracking)
- R6. Script callable standalone and wired into `weekly_pull.py`

## Scope Boundaries

- No interactive UI, no Streamlit, no HTML rendering
- No new model training — only reads existing prediction files
- No Polymarket column in dashboard (already in comparison.csv; keep dashboard focused on Kalshi)
- Knockout-stage games not in scope until fixtures are known

### Deferred to Separate Tasks

- ensemble-v2 standalone prediction file: computed on the fly as simple average of elo/poisson/form (no separate file needed for now)
- Kalshi line-movement chart/visualization: data will be in history CSV; rendering deferred to a future pass

## Context & Research

### Relevant Code and Patterns

- `tools/weekly_pull.py` — full pipeline pattern: pull → normalize → build → write CSV. `build_dashboard.py` follows the same `build_*` function shape
- `results/elo-baseline/<date>/predictions.csv` — long-format: `as_of_date, match_id, market_type, outcome, p_model, confidence, model_version, notes`
- `results/ensemble-e3/<date>/predictions.csv` — same schema
- `data/derived/kalshi_snapshot_<date>.csv` — `match_id, market_type, outcome, last_price, volume, ...`
- `results/comparisons/<date>/comparison.csv` — existing wide-format attempt; dashboard replaces/extends this for per-match use

### Institutional Learnings

- Golden zone rule (WC2022 backtest): all 3 base models agree on same favourite → 15/15 correct, +5.2% ROI
- Real Kalshi edge only exists when model_p > market_p by >3pp (2/15 games in WC2022 had this)
- ensemble-v2 (equal weights: elo + poisson + form / 3) has log-loss 1.054, beats ensemble-e3 (1.062)
- form-last-10 is the strongest individual predictor (46.9% accuracy)

## Key Technical Decisions

- **ensemble-v2 computed on the fly**: simple mean of elo/poisson/form p_model for each (match_id, outcome). No separate prediction file to maintain. If any base model is missing for a match, ensemble-v2 is left blank for that row.
- **Opportunity rule**: `golden_zone = all 3 base models agree on same favourite` AND `ensemble_v2_p - kalshi_p > 0.03` AND `kalshi_p is not null`. Blank (not ❌) when Kalshi has no price.
- **One row per (match_id, outcome)**: keeps the CSV flat and filterable in Sheets (e.g. filter `outcome=home` to see all home-win rows). Three rows per match.
- **Kalshi history log**: append-only `data/derived/kalshi_history.csv` with `as_of_date, match_id, outcome, p_kalshi, v_kalshi`. Create on first run, append on subsequent runs. Enables pivot/chart of Kalshi movement over time.
- **Output path**: `results/dashboard/YYYY-MM-DD.csv` — parallel to other `results/` directories.

## Open Questions

### Resolved During Planning

- **Which ensemble to use**: ensemble-v2 (equal weights) beats ensemble-e3 on WC2022 log-loss. Compute on the fly; no new file.
- **Output format**: wide CSV (one row per match × outcome). User confirmed "simple CSV sheet".
- **Opportunity threshold**: golden zone + 3pp edge, matching the backtest finding.
- **Kalshi API access**: already handled by `tools/weekly_pull.py` via unauthenticated `api.elections.kalshi.com/trade-api/v2`. Per-match volume is currently $0 but prices exist.

### Deferred to Implementation

- Match-ID alignment: some Kalshi match IDs may differ from model match IDs (e.g. `WC26-HTI-SCO` vs `WC26-HAI-SCO`). Implementation should log unmatched rows; a mapping table can be added if needed.
- Whether to include ensemble-e3 column: predictions file exists for 2026-04-28. Implementation should include it if available for the date, skip column if file is absent.

## Output Structure

    results/
      dashboard/
        2026-04-28.csv    ← primary output
        2026-04-29.csv    ← subsequent runs
    data/
      derived/
        kalshi_history.csv  ← append-only history log

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification.*

```
build_dashboard(date):
  1. load_models(date)
     → read results/<model>/<date>/predictions.csv for each model
     → key: (match_id, outcome) → p_model
     → models: elo-baseline, poisson-goals, form-last-10, ensemble-e3

  2. compute_ensemble_v2(elo, poisson, form)
     → mean(elo_p, poisson_p, form_p) per (match_id, outcome)

  3. load_kalshi(date)
     → read data/derived/kalshi_snapshot_<date>.csv
     → filter market_type=match_1x2
     → key: (match_id, outcome) → (p_kalshi, v_kalshi)

  4. join + compute signals
     → all_keys = union of model + kalshi keys for match_1x2
     → per key: compute golden_zone, edge, opportunity

  5. write results/dashboard/<date>.csv

  6. append_kalshi_history(date, kalshi_rows)
     → create or append data/derived/kalshi_history.csv
```

**Dashboard CSV columns:**

| Column | Description |
|--------|-------------|
| match_id | e.g. WC26-MEX-RSA-2026-06-11 |
| outcome | home / draw / away |
| p_elo | elo-baseline probability |
| p_poisson | poisson-goals probability |
| p_form | form-last-10 probability |
| p_ensemble_e3 | ensemble-e3 probability |
| p_ensemble_v2 | computed equal-weight ensemble |
| p_kalshi | Kalshi last price (blank if unavailable) |
| v_kalshi | Kalshi volume |
| golden_zone | 1 if all 3 base models agree on same favourite, else 0 |
| edge | p_ensemble_v2 - p_kalshi (blank if no Kalshi) |
| opportunity | ✅ / blank |

## Implementation Units

- [ ] **Unit 1: `tools/build_dashboard.py` — join, compute, write**

**Goal:** Read all model prediction CSVs and Kalshi snapshot for a given date, produce the wide dashboard CSV.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Existing model files and Kalshi snapshot for the target date must exist (produced by `weekly_pull.py`).

**Files:**
- Create: `tools/build_dashboard.py`

**Approach:**
- Accept date as CLI argument (default: today), same pattern as `weekly_pull.py`
- Load each model's predictions into a dict keyed by `(match_id, outcome)`, filter `market_type=match_1x2`
- Load Kalshi snapshot, filter `market_type=match_1x2`, key by `(match_id, outcome)`
- Compute ensemble-v2 as mean of elo/poisson/form where all three exist
- Compute `golden_zone`: for each match_id, find which outcome each base model gives highest probability; `golden_zone=1` if all three agree
- Compute `edge = p_ensemble_v2 - p_kalshi` (blank if no Kalshi price)
- Compute `opportunity = "✅"` if `golden_zone=1 AND edge > 0.03`, else blank
- Write `results/dashboard/<date>.csv`; create dir if absent

**Patterns to follow:**
- `tools/weekly_pull.py` — `build_comparison()` function for join/write pattern
- Use `csv.DictWriter` / `csv.DictReader`; stdlib only, no pandas

**Test scenarios:**
- Happy path: all 3 base models present, Kalshi has a price → row has all columns populated, opportunity computed
- Edge case: Kalshi price missing for a match → `p_kalshi`, `edge`, `opportunity` all blank; row still written
- Edge case: one base model missing for a match (e.g. elo has no Elo rating for a team) → `golden_zone=0`, `p_ensemble_v2` blank
- Edge case: all 3 models agree but edge ≤ 0.03 → `golden_zone=1`, `opportunity` blank
- Golden zone + edge > 0.03 → `opportunity = "✅"`
- Output file has exactly 3 rows per match_id (home, draw, away) for matches with full model coverage
- Running twice for the same date overwrites (not appends) the dashboard CSV

**Verification:**
- `results/dashboard/2026-04-28.csv` exists with header row and 3 rows per match
- At least one `opportunity = "✅"` row visible (cross-check against `results/comparisons/2026-04-28/actionable.md`)
- All model columns present; no NaN/empty cells except where Kalshi is missing

---

- [ ] **Unit 2: Kalshi history log — append on each run**

**Goal:** On each dashboard build, append that day's per-match Kalshi prices to a rolling history CSV for line-movement queries.

**Requirements:** R5

**Dependencies:** Unit 1 (reuses the loaded Kalshi data)

**Files:**
- Modify: `tools/build_dashboard.py` (add `append_kalshi_history()` function)
- Create (first run): `data/derived/kalshi_history.csv`

**Approach:**
- After building the dashboard, write rows `(as_of_date, match_id, outcome, p_kalshi, v_kalshi)` for all match_1x2 Kalshi rows
- If `kalshi_history.csv` does not exist: create with header
- If it exists: check if `as_of_date` already present; skip append to avoid duplicates on re-runs
- Keep it append-only; do not overwrite past rows

**Patterns to follow:**
- `data/derived/kalshi_snapshot_<date>.csv` for column names

**Test scenarios:**
- First run: file created, header + rows written
- Second run same date: no duplicate rows added (idempotent)
- Second run different date: new rows appended, existing rows untouched
- History file has columns: `as_of_date, match_id, outcome, p_kalshi, v_kalshi`

**Verification:**
- `data/derived/kalshi_history.csv` exists after first run
- Running twice for same date produces the same row count (idempotent)
- Row count grows after a second date's run

---

- [ ] **Unit 3: Wire `build_dashboard` into `weekly_pull.py`**

**Goal:** `python3 tools/weekly_pull.py` now also calls `build_dashboard` as the final step so the whole pipeline runs in one command.

**Requirements:** R6

**Dependencies:** Unit 1

**Files:**
- Modify: `tools/weekly_pull.py`

**Approach:**
- Add `from tools.build_dashboard import build_dashboard` OR inline call via subprocess — prefer a clean import or shared function. Given both scripts use stdlib, simplest is to duplicate the `build_dashboard(date)` call inline (import from same package if `__init__.py` exists, otherwise just `import` with sys.path manipulation or copy the function call pattern)
- Alternative: `weekly_pull.py` `main()` simply calls `subprocess.run(["python3", "tools/build_dashboard.py", TODAY])` — avoids import coupling and follows the single-responsibility pattern already used for other tools
- Add `print(f"  results/dashboard/{TODAY}/wc2026_dashboard.csv")` to the Done output block

**Test scenarios:**
- `python3 tools/weekly_pull.py 2026-04-28` (with existing raw data): `results/dashboard/2026-04-28.csv` exists after run
- `python3 tools/build_dashboard.py 2026-04-28` standalone: same output produced
- Re-running weekly_pull does not append duplicate Kalshi history rows

**Verification:**
- `results/dashboard/YYYY-MM-DD.csv` present after a full `weekly_pull.py` run
- Script prints the dashboard path in its Done summary

## System-Wide Impact

- **Interaction graph:** `build_dashboard.py` is read-only with respect to all upstream files; only writes to `results/dashboard/` and appends to `data/derived/kalshi_history.csv`
- **Error propagation:** Missing model file for a date → log a warning, skip that model column (don't crash). Missing Kalshi snapshot → skip Kalshi columns, write dashboard with blank market columns
- **State lifecycle risks:** `kalshi_history.csv` is append-only; concurrent runs on the same date must be idempotent (check date before appending)
- **Unchanged invariants:** `weekly_pull.py`'s existing outputs (`comparison.csv`, `comparison.md`, `actionable.md`) are not changed. Dashboard is additive.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Kalshi match_id mismatch (e.g. HAI vs HTI country codes) | Log unmatched rows; existing `comparison.csv` shows which IDs align — use it as a reference during implementation |
| ensemble-e3 file absent for a date | Skip column gracefully; golden_zone and ensemble_v2 still computable from 3 base models |
| kalshi_history.csv grows large over tournament | ~54 matches × 3 outcomes × ~60 days = ~10K rows; trivially small |
| Per-match Kalshi volume is currently $0 | Opportunity flags will fire on price signal even at zero volume; user is aware and can filter by `v_kalshi > 0` |

## Sources & References

- Related code: `tools/weekly_pull.py` — `build_comparison()` for join pattern
- Related results: `results/comparisons/2026-04-28/comparison.csv`, `results/comparisons/2026-04-28/actionable.md`
- Backtest: `results/comparisons/wc2022-backtest/summary_metrics.csv`
- Memory: `docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md`
