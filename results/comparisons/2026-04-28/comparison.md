# WC 2026 — Multi-model comparison snapshot 2026-04-28

**Models compared (3):**
- `elo-baseline` v0.1 — World Football Elo + 65pt host advantage
- `poisson-goals` v0.1 — 4-year importance-weighted goal rates → Poisson score grid
- `form-last-10` v0.1 — last 10 matches per team, recency-weighted → Poisson score grid

**Markets:** Kalshi (per-match h2h, all $0 volume currently)

## Mexico vs South Africa — June 11 opener

| Outcome | elo-baseline | poisson-goals | form-last-10 | Kalshi | Model spread |
|---|---|---|---|---|---|
| **home** | 0.772 | 0.417 | 0.442 | 0.650 | 0.355 |
| **draw** | 0.150 | 0.323 | 0.275 | 0.210 | 0.173 |
| **away** | 0.078 | 0.260 | 0.282 | 0.140 | 0.205 |

**Read:** Massive disagreement on Mexico's win probability (77% vs 42% vs 44%). Elo is much more bullish than the goal-based and form-based models. Likely culprits: Elo's home-advantage parameter (+65 pts), and the fact that Mexico has under-performed in goal-based form recently (mostly friendlies). The Kalshi 65% sits between Elo and the average of the others — book consensus is in the middle.

## All WC 2026 matches — first 5 chronologically

| Date | Match | Outcome | elo-baseline | poisson-goals | form-last-10 | Kalshi | spread |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | MEX v RSA | home | 0.77 | 0.42 | 0.44 | 0.65 | 0.36 |
|  |  | draw | 0.15 | 0.32 | 0.28 | 0.21 | 0.17 |
|  |  | away | 0.08 | 0.26 | 0.28 | 0.14 | 0.20 |
|  |  |  |  |  |  |  |  |
| 2026-06-11 | KOR v CZE | home | 0.39 | 0.50 | 0.34 | — | 0.16 |
|  |  | draw | 0.28 | 0.23 | 0.24 | — | 0.05 |
|  |  | away | 0.33 | 0.26 | 0.41 | — | 0.15 |
|  |  |  |  |  |  |  |  |
| 2026-06-12 | USA v PAR | home | 0.32 | 0.68 | 0.46 | 0.50 | 0.36 |
|  |  | draw | 0.26 | 0.22 | 0.26 | 0.24 | 0.04 |
|  |  | away | 0.42 | 0.10 | 0.29 | 0.23 | 0.32 |
|  |  |  |  |  |  |  |  |
| 2026-06-12 | CAN v BIH | home | — | 0.66 | 0.40 | — | 0.26 |
|  |  | draw | — | 0.20 | 0.28 | — | 0.08 |
|  |  | away | — | 0.14 | 0.31 | — | 0.18 |
|  |  |  |  |  |  |  |  |
| 2026-06-13 | HAI v SCO | home | — | 0.64 | 0.32 | — | 0.31 |
|  |  | draw | — | 0.18 | 0.25 | — | 0.08 |
|  |  | away | — | 0.18 | 0.42 | — | 0.24 |
|  |  |  |  |  |  |  |  |

## Top 15 cross-model disagreements

Where models disagree most on a single outcome — highlights where the choice of model matters most.

| Match | Outcome | elo | poisson | form | Kalshi | spread |
|---|---|---|---|---|---|---|
| CIV v ECU (2026-06-14) | **away** | 0.692 | 0.216 | 0.24 | 0.48 | **0.476** |
| URU v CPV (2026-06-21) | **home** | 0.746 | 0.435 | 0.295 | 0.76 | **0.451** |
| NZL v BEL (2026-06-26) | **away** | 0.709 | 0.288 | 0.718 | 0.78 | **0.43** |
| BRA v HAI (2026-06-19) | **home** | 0.791 | 0.383 | 0.439 | — | **0.408** |
| UZB v COL (2026-06-17) | **away** | 0.685 | 0.281 | 0.405 | 0.7 | **0.404** |
| GER v CIV (2026-06-20) | **home** | 0.685 | 0.283 | 0.429 | 0.8 | **0.402** |
| TUN v NED (2026-06-25) | **away** | 0.737 | 0.341 | 0.619 | 0.48 | **0.396** |
| BRA v MAR (2026-06-13) | **home** | 0.598 | 0.218 | 0.291 | 0.63 | **0.38** |
| ARG v AUT (2026-06-22) | **home** | 0.713 | 0.546 | 0.344 | 0.43 | **0.369** |
| COL v COD (2026-06-23) | **home** | 0.734 | 0.373 | 0.399 | — | **0.361** |
| USA v PAR (2026-06-12) | **home** | 0.32 | 0.677 | 0.455 | 0.5 | **0.357** |
| MEX v RSA (2026-06-11) | **home** | 0.772 | 0.417 | 0.442 | 0.65 | **0.355** |
| IRI v NZL (2026-06-15) | **home** | 0.615 | 0.267 | 0.55 | 0.57 | **0.348** |
| CZE v RSA (2026-06-18) | **home** | 0.648 | 0.303 | 0.428 | — | **0.345** |
| NZL v BEL (2026-06-26) | **home** | 0.141 | 0.465 | 0.12 | 0.05 | **0.345** |

## Model agreement summary

Per-match aggregate: how often do all 3 models agree on the favourite?

| Agreement | Matches |
|---|---|
| All 3 models pick same favourite | 31 |
| 2 of 3 agree | 27 |
| All 3 split (each picks different) | 0 |
| Insufficient model coverage | 23 |