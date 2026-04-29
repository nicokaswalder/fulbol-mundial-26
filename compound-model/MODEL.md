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
| **Validation status** | Plan complete 2026-04-28; live data sources verified; implementation pending |
| **Plan** | [`docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md`](docs/plans/2026-04-28-001-feat-wc26-prediction-edge-finder-plan.md) |
