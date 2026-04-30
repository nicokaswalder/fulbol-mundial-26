# Model Card: compound-model

| Field | Value |
|---|---|
| **Model name** | compound-model |
| **Author(s)** | Luis Noguera (`@lnoguera`) |
| **Approach** | Statistical: time-decayed Dixon-Coles + Bivariate Poisson, fed by xG-aggregated lineup ratings, with Elo prior. Tournament outcomes via 10k-iteration Monte Carlo respecting 2026 bracket. |
| **Stack** | Python 3.12, `penaltyblog`, `soccerdata`, `pandas`, `numpy`, `scipy` |
| **Data sources** | `martj42/international_results` (49,256 matches), FBref player xG, eloratings.net, StatsBomb open data (backtest), Kalshi/Polymarket/The Odds API (live odds) |
| **Training window** | 2018-01-01 → present (7,961 modern matches), exponential time-decay with `xi` ∈ [0.001, 0.003] |
| **Calibration method** | Walk-forward against Euro 2024, Copa America 2024, WC 2022; temperature scaling |
| **Confidence reporting** | `high` if backtest log-loss within 1.05× Pinnacle close; `medium` within 1.10×; `low` otherwise |
| **Update cadence** | Weekly pre-tournament, daily during the tournament |
| **Output location** | `results/compound-model/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered (v1)** | `match_1x2`, `outright_winner`, `group_winner` |
| **Markets covered (v2)** | + `team_advances`, totals, BTTS |
| **Known limitations** | International xG is sparse — model leans on club-xG aggregation through projected lineups; lineup YAMLs need updating after each FIFA squad announcement; small-sample teams (e.g. Ghana, Cape Verde) get wider posteriors and fewer actionable rows |
| **Validation status** | WC 2022 backtest complete 2026-04-28. ensemble-v2 log-loss 1.054 (beats ensemble-e3 1.062). Form model strongest individual predictor (46.9% accuracy, matches Pinnacle). xG-Poisson needs more training data. |
| **Backtest results** | `results/comparisons/wc2022-backtest/` — per-match predictions and summary metrics |
| **Betting rule** | Only bet Golden Zone matches (all 3 models agree). Skip 3-way splits. Edge threshold: model_p > market_p by ≥3%. Realistic ROI: +5.2% across all "models agree" games. |
| **Plan** | [`docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md`](docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md) |
| **Model roles** | [`../docs/solutions/best-practices/model-roles-and-best-use-2026-04-28.md`](../docs/solutions/best-practices/model-roles-and-best-use-2026-04-28.md) |
| **Next priority** | Pull xG for Nations League + WC qualifying to expand xG-Poisson training data. Wire in player lineup xG ratings (Understat data already in `data/derived/`). |
