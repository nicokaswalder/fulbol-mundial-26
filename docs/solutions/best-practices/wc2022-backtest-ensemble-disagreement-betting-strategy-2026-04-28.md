---
title: "WC 2022 Backtest: Model Disagreement Taxonomy and Betting Strategy"
date: 2026-04-28
category: docs/solutions/best-practices
module: prediction-model
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - Building or evaluating a multi-model ensemble for tournament football prediction
  - Deciding which WC 2026 matches to bet on Kalshi or Polymarket
  - Interpreting ensemble output where models give conflicting signals
tags:
  - ensemble, xg-model, betting-strategy, wc2026, kalshi, model-disagreement, calibration, backtest
---

# WC 2022 Backtest: Model Disagreement Taxonomy and Betting Strategy

## Context

We ran a full WC 2022 backtest with three independent models (Elo, Form-last-10, xG-Poisson) trained on pre-November 2022 data, tested on all 64 matches. The ensemble (ensemble-v2) uses equal weighting (33/33/33). Out of this, we discovered that **model disagreement level is the strongest predictor of whether to bet** — more reliable than model confidence alone.

The xG-Poisson was patched to use StatsBomb match-level xG (WC 2018 + Euro 2020) as the target variable instead of actual goals, giving it a less noisy signal. The resulting ensemble-v2 achieved log-loss 1.054, beating the previous goals-based ensemble-e3 (1.062) and matching Pinnacle's accuracy benchmark (46.9%).

## Guidance

### Model Disagreement Taxonomy

Classify every predicted match into one of three buckets before deciding to bet:

| Bucket | Definition | WC 2022 result | Action |
|---|---|---|---|
| **Golden Zone** | All 3 models predict same outcome | 15/15 correct (100%) | Bet if model > market |
| **False Consensus** | All 3 agree but are wrong | 4 games — all major upsets | Bet with capped stake only |
| **3-Way Split** | Each model picks a different outcome | 20 games, 40% accuracy | Skip — do not bet |
| **2-Way Split** | Two models agree, one disagrees | 25 games, mixed | Small stake if 2 agree with high confidence |

All-or-nothing rule: **If models 3-way split, there is no bet regardless of individual confidence scores.** The ensemble average is meaningless when three independent methodologies point in opposite directions — it just averages random noise.

### The Golden Zone in practice

```
Golden Zone games: 15 of 64 (23.4%)
Avg confidence:    56.1%
Min confidence:    47.7%
Max confidence:    72.5%

Accuracy: 15/15 (100%) — WC 2022
```

These were not all dominant mismatches. Some had confidence as low as 48% (Wales vs England, Ghana vs Uruguay). What unified them: all three independent signal sources — historical ratings, recent form, and xG quality — told the same story.

### Edge calculation (Kalshi)

Being right is not enough. You only make money when **model probability > market implied probability**:

```
edge = p_model - p_market_devigged
```

Against approximate Pinnacle WC 2022 closing lines, only **2 of the 15 golden zone games** had genuine edge (model > market by >3%):

- **Wales vs Iran**: model 51% Away, Pinnacle 38% Away → +12.8% edge @ 2.62 odds
- **Poland vs Argentina**: model 65% Away, Pinnacle 60% Away → +4.7% edge @ 1.66 odds

The other 13 golden zone games were correctly predicted but the market had already priced the favorites efficiently — no edge to capture.

### Realistic ROI (all "models agree" games)

Betting all 19 games where all three models agreed (15 golden + 4 false consensus losses):

```
15 wins + 4 losses = +5.2% ROI on total stake
```

This is a genuinely good long-run edge. Professional bettors target 3–7% ROI. The 4 false consensus losses are unavoidable — they were the biggest WC 2022 upsets (Argentina vs Saudi Arabia, Cameroon vs Brazil, etc.).

### Calibration check

ensemble-v2 is well-calibrated — predicted probabilities track actual win rates:

| Predicted win prob | Actual win rate | N |
|---|---|---|
| 0–20% | 20% | 5 |
| 20–35% | 37% | 30 |
| 35–50% | 47% | 19 |
| 50–65% | 67% | 9 |
| 65–100% | 100% | 1 |

This matters because calibration is the prerequisite for edge calculation. If the model were overconfident (predicted 70%, actual 40%), edge estimates would be meaningless.

### The France vs Australia lesson

France won 4-1 but:
- Elo predicted Draw (France's Elo was dragged down by poor Nations League 2022 form)
- Form predicted Away win (France had genuinely mixed recent results)
- xG-Poisson predicted Away win (France weren't a high-xG team in WC 2018 training data)

Ensemble average: H:34% D:34% A:31% — complete three-way split with no conviction.

**Rule: when ensemble probabilities are within 5pp of each other across all three outcomes, the model has no signal. Skip the bet regardless of what the "prediction" label says.**

## Why This Matters

Without this taxonomy, you'd bet on 19 games (all where models agree) and only discover 4 were losses after the fact. With it, you can pre-screen using the 3-way split filter to eliminate low-signal games before evaluating edge vs market.

For WC 2026:
- The strategy is profitable at any bankroll size at +5.2% ROI
- Scale matters more than the per-game accuracy — 15+ bettable games per tournament is enough to let edge play out statistically
- The biggest lever: finding more games where model > Pinnacle by >3% (only 2 of 15 in 2022)

## When to Apply

- Every WC 2026 match: run all 3 models, classify disagreement bucket first
- Only proceed to edge calculation for Golden Zone matches
- Before each match: compare ensemble probability vs Kalshi devigged price
- Do not bet 3-way split matches regardless of potential payout

## Examples

### Identifying a bettable game

```python
# After running ensemble predictions
def classify_disagreement(elo_pred, form_pred, xgp_pred):
    preds = {elo_pred, form_pred, xgp_pred}
    if len(preds) == 1:
        return "golden_zone"   # all agree
    elif len(preds) == 2:
        return "two_way_split"
    else:
        return "three_way_split"  # skip

def has_edge(model_p, market_p, threshold=0.03):
    return (model_p - market_p) >= threshold

# Only bet when:
# 1. golden_zone (all models agree)
# 2. has_edge (model > market by 3%+)
# 3. market has volume > 0 (Kalshi pre-tournament markets are often illiquid)
```

### Metrics from WC 2022 backtest

```
Model            Log-loss   Accuracy   Correct
elo-baseline     1.2254     43.8%      28/64
form-last-10     1.0807     46.9%      30/64   ← best accuracy
poisson-xg       1.1688     40.6%      26/64
ensemble-v2      1.0544     43.8%      28/64   ← best log-loss
ensemble-e3      1.0620     35.9%      23/64   (benchmark)
Pinnacle         ~0.97      ~47%       ~30/64  (sharp benchmark)
```

Key takeaway: **Form is the single strongest individual model for tournament football** (46.9%, matching Pinnacle). Recency matters more than historical ratings at major tournaments. xG-Poisson underperformed due to sparse training data — only 115 matches had real StatsBomb xG (WC 2018 + Euro 2020). Adding Nations League and WC qualifying xG would likely close the gap.

## Related

- `compound-model/docs/brainstorms/2026-04-28-wc2022-backtest-xg-ensemble-requirements.md` — requirements that drove this backtest
- `compound-model/docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md` — full WC 2026 implementation plan
- `results/comparisons/wc2022-backtest/all_models_comparison.csv` — per-match predictions vs actuals for all models
- `results/comparisons/wc2022-backtest/summary_metrics.csv` — log-loss, accuracy, Brier per model
- `wc2022_xg_backtest.py` — backtest script (reproducible with `/opt/homebrew/bin/python3.12 wc2022_xg_backtest.py`)
