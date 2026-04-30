---
title: "Statistical Model Roles: When and How to Use Each Model"
date: 2026-04-28
category: docs/solutions/best-practices
module: prediction-model
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - Building the WC 2026 ensemble
  - Deciding how much weight to give each model signal
  - Diagnosing why the ensemble gave a surprising prediction
  - Adding a new model to the ensemble in the future
tags:
  - elo, form, xg-poisson, ensemble, model-design, wc2026, signal-hierarchy
---

# Statistical Model Roles: When and How to Use Each Model

## Context

After running the WC 2022 backtest (all 64 matches, strict temporal split) with three independent models and comparing them per-match, a clear division of responsibilities emerged. Each model captures a different layer of team quality. Understanding what each model is actually measuring — and where it breaks — is essential for building the WC 2026 ensemble correctly and for diagnosing future failures.

Validated metrics (WC 2022, 64 matches):

| Model | Log-loss | Accuracy | Role |
|---|---|---|---|
| elo-baseline | 1.2254 | 43.8% | Long-term reputation prior |
| form-last-10 | 1.0807 | **46.9%** | Current momentum signal |
| poisson-xg | 1.1688 | 40.6% | Underlying quality signal |
| ensemble-v2 (equal weight) | **1.0544** | 43.8% | Calibrated final probability |
| Pinnacle benchmark | ~0.97 | ~47% | Sharp market baseline |

## Guidance

### Model 1 — Elo: Long-term Reputation

**What it measures:** Decades of head-to-head results, weighted by goal margin, adjusted for opponent strength. The slowest-moving signal.

**Best at:**
- Identifying the true talent tier of a nation (Brazil, Argentina, France are consistently top regardless of recent noise)
- Separating elite from mid-table even with limited recent data
- Providing a stable prior for teams with few recent competitive fixtures

**Fails at:**
- Detecting in-tournament form shifts quickly (still rates a team on 2-year history even if they won 10 straight)
- Teams rebuilding — a new generation performing above their Elo gets no credit until they've played enough matches
- Any team whose Elo was dragged down by a bad qualifying or Nations League campaign they've since recovered from (classic example: France before WC 2022)

**Design note for WC 2026:** Use Elo as a floor, not a ceiling. When all other signals are uncertain, Elo is the tiebreaker. Do not let a single bad run override a team's 5-year Elo unless Form and xG both confirm it.

---

### Model 2 — Form (last 10): Current Momentum

**What it measures:** Average points per game across the most recent 10 competitive fixtures, normalized to [0, 1].

**Best at:**
- Capturing squad fitness and tactical coherence in the months before a tournament
- Detecting teams that are genuinely in form vs coasting on reputation
- The single strongest predictor of WC results — 46.9% accuracy matching Pinnacle

**Fails at:**
- Schedule quality: a team that went 10/10 against Caribbean minnows looks the same as one that went 10/10 against UEFA A-league sides
- Squad rotation: competitive results in qualifiers may not reflect the starting XI that plays the WC
- Treating a loss to Brazil in a friendly differently than a loss to a weak opponent — all losses are equal

**Design note for WC 2026:** Weight fixtures by the importance multiplier already built into the Poisson model. A Nations League A match should count more than a friendly. Consider adding opponent quality weighting to the form calculation to fix the schedule quality gap.

---

### Model 3 — xG-Poisson: Underlying Quality

**What it measures:** Expected goals (xG) as the Poisson target variable — the quality of chances created and conceded, regardless of whether they were converted. Fit via Dixon-Coles MLE with time decay.

**Best at:**
- Identifying teams whose results don't reflect their actual performance (the "deserved to win" signal)
- High-variance predictions — it's the most aggressive model, giving extreme probabilities to dominant teams (Brazil at 95% vs Switzerland)
- Catching market inefficiencies: when Form says 45% but xG says 70%, the market often hasn't priced the underlying dominance

**Fails at:**
- Small xG training sample: currently only 115 matches have real StatsBomb xG (WC 2018 + Euro 2020). With more data it will close the 6-point accuracy gap vs Form
- Projecting tournament performance from qualifying xG — teams play differently in tournaments than in qualifiers
- Minnow teams: sparse data means very uncertain attack/defence parameters

**Design note for WC 2026:** This model has the most upside. Adding xG from:
- UEFA Nations League 2022-23, 2024-25
- CONMEBOL WC qualifying 2026
- CONCACAF Nations League

...would likely bring it to parity with or better than the Form model. Priority data pull before building the WC 2026 version.

---

### Ensemble-v2: The Calibrated Bet-Sizing Number

**What it measures:** Equal-weight average of the three independent models (33/33/33). Best log-loss (1.054) because it smooths out each model's individual failure modes.

**Best at:**
- Producing calibrated probabilities — predicted win rates track actual win rates cleanly (see calibration table below)
- Being the number you plug into `edge = p_model - p_market_devigged`
- Surfacing disagreement: when ensemble probability is flat across H/D/A (~33/33/33), that's a signal to skip the bet

**Calibration table (WC 2022):**

| Predicted win prob | Actual win rate | N |
|---|---|---|
| 0–20% | 20% | 5 |
| 20–35% | 37% | 30 |
| 35–50% | 47% | 19 |
| 50–65% | 67% | 9 |
| 65–100% | 100% | 1 |

**Does not replace** individual model analysis — you need to look at the three model predictions separately to classify disagreement before using the ensemble number for betting.

## Why This Matters

Using the wrong model for the wrong job produces false confidence. Specific risks:

- **Relying on Elo alone** for a team in current poor form → overestimate strong-but-cold favorites
- **Relying on Form alone** for a team that played weak qualifiers → underestimate opponents who were resting starters
- **Relying on xG-Poisson alone** with sparse data → extreme probabilities for minnow matchups with no real signal
- **Using ensemble probability without checking disagreement** → betting on 3-way split games that should be skipped

## When to Apply

Reference this document when:
- Adding a fourth model to the ensemble (e.g. market-implied baseline, LightGBM)
- Diagnosing a surprising prediction ("why did the model say X when Y is obvious?")
- Deciding weights for a future meta-model (Form should get higher prior weight than xG-Poisson until xG training data expands)
- Writing the WC 2026 model card or updating `compound-model/MODEL.md`

## Examples

### Reading a prediction correctly

```
France vs Australia — WC 2022 actual: France 4-1

Elo:        H:0.35  D:0.53  A:0.12  → pred: D   (France Elo deflated by Nations League)
Form:       H:0.41  D:0.17  A:0.42  → pred: A   (France had mixed recent results)
xG-Poisson: H:0.27  D:0.33  A:0.40  → pred: A   (France low xG in WC 2018 training data)
Ensemble:   H:0.34  D:0.34  A:0.31  → pred: D   (coin flip — no signal)

Disagreement: 3-way split → SKIP
```

### A bettable prediction

```
Poland vs Argentina — WC 2022 actual: Argentina 0-2

Elo:        H:0.02  D:0.30  A:0.68  → pred: A
Form:       H:0.35  D:0.17  A:0.48  → pred: A
xG-Poisson: H:0.05  D:0.16  A:0.79  → pred: A
Ensemble:   H:0.14  D:0.21  A:0.65  → pred: A

Disagreement: all agree (golden zone)
Model: 65% Away    Pinnacle: 60% Away    Edge: +4.7%  → BET
```

### Diagnosing a False Consensus loss

```
Argentina vs Saudi Arabia — WC 2022 actual: Argentina 1-2

Elo:        H:0.71  D:0.28  A:0.01  → pred: H
Form:       H:0.50  D:0.17  A:0.33  → pred: H
xG-Poisson: H:0.47  D:0.38  A:0.14  → pred: H
Ensemble:   H:0.56  D:0.28  A:0.16  → pred: H

Disagreement: all agree → golden zone
BUT: actual result was A — Saudi Arabia won

Lesson: No model captures tactical surprise, underdog motivation,
or day-of fitness. False consensus losses like this are irreducible.
Cap stakes even on golden zone bets — never go all-in.
```

## Future Model Candidates

Features ranked by expected value-add for WC 2026:

| Feature | Signal type | Status | Expected impact |
|---|---|---|---|
| xG from Nations League + WC qualifying | xG-Poisson training data | Not yet pulled | High — closes 6pt accuracy gap |
| Player lineup xG rating | Attack/defence quality | Understat data pulled, not wired in | High — captures squad quality |
| Squad injury / suspension flags | Pre-match context | Manual YAML, not built | Medium |
| Altitude + travel distance | Match context features | Planned in Unit 7 | Low–medium |
| Market-implied baseline | 4th model (Pinnacle devigged) | Not built | Medium — adds sharp consensus signal |
| Meta-model (logistic regression on 3 model outputs) | Weight optimization | Deferred | Medium — revisit after WC 2026 backtest |

## Related

- `docs/solutions/best-practices/wc2022-backtest-ensemble-disagreement-betting-strategy-2026-04-28.md` — disagreement taxonomy and betting rules
- `compound-model/MODEL.md` — model card (update after each backtest)
- `wc2022_xg_backtest.py` — reproducible backtest script
- `results/comparisons/wc2022-backtest/all_models_comparison.csv` — per-match predictions for all models
- `compound-model/docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md` — WC 2026 implementation plan (Unit 6 = lineup ratings, Unit 7 = features)
