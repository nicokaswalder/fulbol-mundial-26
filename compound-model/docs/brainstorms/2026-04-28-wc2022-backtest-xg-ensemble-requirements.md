---
title: "WC 2022 Backtest — xG-Patched Ensemble"
type: requirements
status: draft
date: 2026-04-28
---

# WC 2022 Backtest: xG-Patched Ensemble

## Problem

The current ensemble (Elo 35% + goals-Poisson 45% + Form 20%) scored **35.9% accuracy and ~1.05 log-loss** on WC 2022 — barely above the 33% random baseline for a 3-way outcome. The primary weakness is that the Poisson model uses actual goals as its target variable. Goals are noisy; a 1-0 game where the losing team dominated possession (e.g. Argentina vs Saudi Arabia) looks the same as a dominant 1-0. xG corrects for that noise.

## Goal

Patch the Poisson model to use xG as its target variable, re-run the WC 2022 backtest across all 4 models with a strict temporal split, and produce a comparison table of individual model vs ensemble performance. The output is **insight**, not deployment: we learn which signal matters most so we can build a better WC 2026 model.

## Success Criteria

- xG-Poisson log-loss on WC 2022 is lower than goals-Poisson log-loss
- Equal-weight ensemble of all 4 models beats the current ensemble-e3 (35.9% accuracy, ~1.05 log-loss)
- Output includes a clear per-model breakdown: log-loss, Brier score, accuracy, and calibration
- No data leakage: WC 2022 match data (scores, xG) is never used in training or fitting

## Scope

### In

- Patch `poisson-goals` → `poisson-xg`: swap goals for StatsBomb xG as the Poisson target variable
- Use StatsBomb WC 2018 + Euro 2020 as the primary xG training source (115 matches, both pre-WC 2022)
- Fall back to actual goals from `martj42` for all other matches without StatsBomb xG coverage
- Keep `elo-baseline`, `form-last-10`, `ensemble-e3` exactly as they are
- Add `ensemble-v2`: equal-weight average of all 4 model probability outputs
- WC 2022 test set: 64 matches (2022-11-20 → 2022-12-18), all treated as neutral venue
- Report metrics: log-loss (1X2), accuracy (argmax), Brier score, calibration table (5-bin)
- Save results to `results/poisson-xg/wc2022-backtest/` and `results/ensemble-v2/wc2022-backtest/`

### Out

- No LightGBM or ML classifiers (overfitting risk on small dataset)
- No meta-model / stacking (deferred — interesting but not needed here)
- No Kalshi comparison in this iteration (phase 2)
- No hyperparameter tuning (keep xi decay and importance weights fixed)
- No player-level lineup rating (deferred to WC 2026 model)

## Data

| Source | Role | Coverage |
|---|---|---|
| `data/raw/martj42/latest/results.csv` | Goals-based training (Elo, Form, Poisson fallback) | 49k matches through 2026-03-31 |
| StatsBomb WC 2018 (`competition_id=43, season_id=3`) | xG training signal — **must be pulled first via `tools/pull_statsbomb.py`** | 64 matches |
| StatsBomb Euro 2020 (`competition_id=55, season_id=43`) | xG training signal — **must be pulled first via `tools/pull_statsbomb.py`** | 51 matches |
| `data/derived/statsbomb_team_xg.parquet` | xG already pulled for WC 2022 — **test set only, never used in training** | 64 matches |
| `data/raw/elo/2026-04-28/World.tsv` | Elo prior | All national teams |

**Prerequisite:** Run `tools/pull_statsbomb.py` with WC 2018 and Euro 2020 added to `TARGETS` before running the model. These competitions are confirmed available in the free StatsBomb open data.

Training window: `2012-01-01 → 2022-11-19` (same as current ensemble).
xG substitution: wherever a match appears in StatsBomb WC 2018 or Euro 2020, replace `home_score / away_score` with `xg_home / xg_away` in the Poisson likelihood. All other matches in the training window use goals as-is.

## Models

**Three independent models feed ensemble-v2. ensemble-e3 is a comparison benchmark only — it is not a component of the new ensemble because it already combines Elo + goals-Poisson + Form internally, which would double-count those signals.**

| Model | Change | Role |
|---|---|---|
| `elo-baseline` | None | ensemble-v2 component (33%) |
| `form-last-10` | None | ensemble-v2 component (33%) |
| `poisson-xg` | Swap goals → xG in Dixon-Coles MLE | ensemble-v2 component (33%) |
| `ensemble-e3` | None — load from existing `results/ensemble-e3/wc2022-backtest/predictions_vs_actual.csv` | Comparison benchmark only |

**Note on ensemble-e3:** reuse the existing predictions file rather than re-fitting, to avoid L-BFGS-B non-determinism producing a different number than the documented 35.9%.

## Output

### Per-model metrics table (WC 2022, 64 matches)

| Model | Log-loss | Accuracy | Brier |
|---|---|---|---|
| elo-baseline | ? | ? | ? |
| form-last-10 | ? | ? | ? |
| poisson-goals (current) | ? | ? | ? |
| poisson-xg (patched) | ? | ? | ? |
| ensemble-e3 (current) | ? | ? | ? |
| ensemble-v2 (equal weight) | ? | ? | ? |
| Pinnacle benchmark | ~0.97 | ~47% | ~0.21 |

### Calibration table (ensemble-v2)

5-bin reliability: predicted probability bucket vs actual win rate. Tells us whether the model is over- or under-confident.

### Per-match prediction table

Same format as `results/ensemble-e3/wc2022-backtest/predictions_vs_actual.csv` — extended with `p_model_v2` column.

## Key Learnings to Extract

After running the backtest, answer these questions to guide the WC 2026 build:

1. Did xG improve log-loss vs goals-Poisson? By how much?
2. Which single model had the lowest log-loss?
3. Did the equal-weight ensemble beat the best individual model?
4. Where did all models agree and still get it wrong? (systematic blind spots)
5. Which matches had the largest `|p_model - actual_result|`? Any pattern (upsets, specific teams)?

## Phase 2 — WC 2026 (deferred, not in scope here)

Once learnings are extracted:
- Apply best-performing model architecture to WC 2026 predictions
- Pull current Kalshi prices and devig
- Compute `edge = p_model - p_kalshi_devigged` per match × outcome
- Flag rows where `edge > 3%` and model confidence is `high`
- Meta-model (train logistic regression on model outputs as features) — revisit after WC 2022 backtest shows which models add independent signal
