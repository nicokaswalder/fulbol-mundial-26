# compound-model

A Python CLI + notebooks pipeline that predicts every FIFA World Cup 2026 match using a Dixon-Coles + Bivariate Poisson model fed by xG-aggregated lineup ratings, simulates the tournament 10,000 times respecting the new 12-group + best-thirds bracket, and compares the model's probabilities against live odds from Kalshi, Polymarket, and Hard Rock Bet to surface positive-edge bets.

> This is **one model** in the multi-contributor [fulbol-mundial-26](../README.md) repo. See the root README for how to add your own.

## What this model does

- Pulls 49,256 senior international match results (since 1872) from `martj42/international_results` and computes time-decayed Dixon-Coles attack/defense parameters for every WC team.
- Aggregates club-level xG from FBref through projected national-team lineups so we get per-team expected-goal rates that don't depend on sparse international xG data.
- Runs a 10,000-iteration Monte Carlo simulator that respects the 2026 bracket (12 groups × 4 → top 2 + 8 best thirds → R32) including extra time and penalty shootouts.
- Pulls live odds from Kalshi (5 series, no auth needed for reads), Polymarket Gamma, and The Odds API (Hard Rock + Pinnacle baseline), strips the vig with Power and Shin methods, and computes per-book edges.
- Emits a dense CLI/notebook comparison table — no graphics — sorted by edge with half-Kelly stake suggestions clipped at 2% bankroll.
- Writes its predictions to [`../results/compound-model/<YYYY-MM-DD>/predictions.csv`](../results/) using the shared schema.

## Status

**Plan complete (2026-04-28). Implementation pending.** The full plan is at [`docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md`](docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md).

| Phase | Target | Status |
|---|---|---|
| Phase 1: Working comparison table (baseline = Pinnacle-devigged) | +7 days | Not started |
| Phase 2: Internal Dixon-Coles model | +14 days | Not started |
| Phase 3: Backtest + calibration + bet ledger | +19 days | Not started |
| Phase 4: Tournament operations | June 11 – July 19 | Not started |

## Cost and credentials

**$0/month for live operation.** One optional $30 charge for The Odds API historical-odds backtest.

| Source | Cost | Credential |
|---|---|---|
| The Odds API (Hard Rock + Pinnacle) | $0/mo free tier | API key (free signup) |
| Kalshi (reads only — verified unauthenticated) | Free | None at v1 |
| Polymarket Gamma | Free | None |
| FBref / eloratings.net / StatsBomb / `martj42` | Free | None |
| Hosting / DB / scheduler | $0 | Your laptop |

See the plan's "Cost & credentials" decision and the validation findings section for details.

## Setup (once it's built)

```bash
cd compound-model
uv sync                                    # install deps
cp .env.example .env                       # set ODDS_API_KEY
uv run wc26 weekly                         # full pipeline → results/compound-model/<today>/predictions.csv
```

## Weekly workflow

```bash
uv run wc26 weekly        # data refresh → model fit → markets pull → simulate → compare → write predictions.csv
```

After placing a bet manually:
```bash
uv run wc26 bet log --match WC26-MEXRSA-2026-06-11 --side home --book hardrock --price 1.83 --stake 50
uv run wc26 bet score    # after match-day, settles open bets
```

The local bet ledger lives at `bets/ledger.csv` (gitignored — private financial data).

## Why this approach

International football is data-sparse — most teams play 8–12 competitive matches per cycle. Pure goal-based Poisson models on national-team data overfit. The pipeline leans on three pillars instead:

1. **Goal-based time-decayed Dixon-Coles** trained on 7,961 modern (2018+) internationals
2. **Club-xG-aggregated lineup ratings** — the model's strength signal lives at the player-club level where xG data is dense
3. **FIFA / World Football Elo as a Bayesian prior** for overall team strength

A baseline mode (`--model baseline`) ships before the full Dixon-Coles model is fit, so the comparison table is usable in week 1 even if v1 modeling slips. Baseline computes `p_model = Pinnacle-devigged-probability` and finds book-vs-book mispricing — genuine edge that doesn't require the internal model to be right.

## Output to the shared `results/` folder

Every weekly run writes one CSV to `../results/compound-model/<YYYY-MM-DD>/predictions.csv` with the standard 8-column schema. See [`../results/README.md`](../results/README.md) for the exact contract.

## Files in this folder

```
compound-model/
├── README.md                    # this file
├── MODEL.md                     # standardized model card
└── docs/
    └── plans/
        └── 2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md
                                  # full implementation plan
```

The `src/`, `notebooks/`, `tests/`, etc. directories will appear once Phase 1 of the plan is built.

## Compare against other models

```bash
# Diff our predictions against another model on the same day
diff <(cut -d, -f2-5 ../results/compound-model/2026-05-15/predictions.csv | sort) \
     <(cut -d, -f2-5 ../results/<other-model>/2026-05-15/predictions.csv | sort)
```

Or in pandas:
```python
import pandas as pd
ours = pd.read_csv("../results/compound-model/2026-05-15/predictions.csv")
theirs = pd.read_csv("../results/<other-model>/2026-05-15/predictions.csv")
joined = ours.merge(theirs, on=["match_id","market_type","outcome"], suffixes=("_ours","_theirs"))
joined["disagreement"] = (joined["p_model_ours"] - joined["p_model_theirs"]).abs()
print(joined.sort_values("disagreement", ascending=False).head(20))
```
