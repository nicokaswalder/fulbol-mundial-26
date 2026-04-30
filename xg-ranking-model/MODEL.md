# xg-ranking-model

> Hybrid xG + FIFA-ranking anchored model for the 2026 FIFA World Cup group stage.  
> **Snapshot cadence:** weekly, or after significant squad news.  
> **Markets covered:** `match_1x2`, `totals`, `btts`, `group_winner`, `outright_winner`  
> **Confidence convention:** `high` / `medium` / `low` (subjective tier based on tier gap between teams and data coverage)

---

## How the model works

### Architecture — two layers

**Layer 1 — Anchor prior (60% weight)**  
Match results are seeded from football domain knowledge: historical head-to-head patterns, 2022–2026 qualifying form, and known team tier. These anchors act as a regularisation prior to prevent the math layer from producing unrealistic scorelines.

**Layer 2 — Math adjustment (40% weight)**  
A strength score is computed per team. If the ratio of home-to-away strength diverges strongly from the anchor (ratio > 1.6 or < 0.65), the scoreline is nudged ±1 goal. Win/draw/loss probabilities are derived entirely from the math layer.

---

## Strength score

```
strength(team) = rank_score×0.24 + (xGF × atk_mult)×0.43 + xGA_def×0.20 + conf_adj + surprise
```

| Input | Formula |
|---|---|
| `rank_score` | `max(5, 100 − FIFA_rank) / 100` |
| `atk_mult` | Tier S = 1.45×, A = 1.15×, B = 0.92×, C = 0.60× |
| `xGA_def` | `2.5 − xGA` (lower conceding = higher score) |
| `conf_adj` | See table below |
| `surprise` | Norway only: +0.20 (Haaland xGF 2.02 factor) |

### Confederation adjustments

| Confederation | Condition | Adjustment |
|---|---|---|
| CONMEBOL | Tier S (Argentina) | +0.16 |
| CONMEBOL | All others | +0.10 |
| UEFA | Tier S only | +0.08 |
| CAF | Tier A (Morocco) | 0.00 |
| CAF | All others | −0.12 |
| CONCACAF host | USA / Mexico / Canada | +0.06 |

### FIFA ranking multiplier (applied to xGF and xGA inputs)

| Rank range | Multiplier |
|---|---|
| 1–5 | 1.50× |
| 6–10 | 1.40× |
| 11–20 | 1.25× |
| 21–30 | 1.12× |
| 31–50 | 1.00× |
| 51–70 | 0.88× |
| 71+ | 0.72× |

---

## Team tiers

| Tier | Teams |
|---|---|
| **S** | France, Spain, Argentina, England, Portugal, Netherlands, Germany, Belgium, Brazil, Norway |
| **A** | Morocco, Colombia, Croatia, Uruguay, Japan, USA, Mexico, Switzerland, South Korea, Senegal, Turkey, Austria, Ecuador, Paraguay, Sweden |
| **B** | Australia, Iran, Scotland, Bosnia-Herz., Algeria, Egypt, Ivory Coast, Ghana, Saudi Arabia, Tunisia |
| **C** | DR Congo, Uzbekistan, Cape Verde, Curaçao, Qatar, Haiti, Iraq, Jordan, New Zealand, Panama |

---

## Draw probability cap

| Condition | Draw cap |
|---|---|
| Tier gap ≥ 3 | 5% |
| Tier gap = 2 | 10% |
| Rank gap ≤ 8 | 27% |
| Rank gap ≤ 15 | 22% |
| All other | 17% |

---

## Data sources

| Source | Details |
|---|---|
| FIFA rankings | April 1, 2026 |
| xGF / xGA | Aggregated 2022–2026 qualifying + competitive matches |
| Match type weights | Qualifier 1.00×, Confed. final 0.88×, Nations League 0.76×, Friendly 0.40× |
| Historical WC draw rate | ~22% baseline (group stage, 2006–2022) |

---

## Predicted group winners

| Group | Winner | Runner-up | Notes |
|---|---|---|---|
| A | Mexico | South Korea | Host advantage |
| B | Switzerland | Canada | Qatar winless |
| C | Morocco | Brazil | Draw MD1 likely — Morocco xGA 0.68 |
| D | **Paraguay** | USA | CONMEBOL +12% — strongest market edge |
| E | Germany | Ecuador | Curaçao heavy losses |
| F | Netherlands | Japan | Sweden Tier B |
| G | Belgium | Egypt | Iran Tier C |
| H | Spain | Uruguay | Spain 9 pts |
| I | France | Norway | Group of death |
| J | Argentina | Austria | Argentina 9 pts |
| K | Portugal | Colombia | Portugal Tier S |
| L | England | Croatia | England dominant |

---

## Top market edges (vs Polymarket / Kalshi, Apr 28 2026)

| Bet | Model | Market | Edge | Direction |
|---|---|---|---|---|
| Paraguay group winner (D) | 45% | 12% | +33pp | **BUY** |
| Morocco group winner (C) | 38% | 17% | +21pp | **BUY** |
| Japan win vs Tunisia (F MD2) | 75% | 46% | +29pp | **BUY** |
| Belgium group winner (G) | 85% | 70% | +15pp | **BUY** |
| Norway group winner (I) | 30% | 24% | +6pp | **BUY** |
| Egypt win vs Iran (G MD1) | 60% | 33% | +27pp | **BUY** |
| USA group winner (D) | 32% | 51% | −19pp | **FADE** |
| Brazil group winner (C) | 42% | 77% | −35pp | **FADE** |

---

## Limitations

- No injury or suspension data incorporated (add to `notes` column manually when relevant)
- Host advantage fixed at +0.06–0.07; crowd effects at USA/Mexico venues may be larger
- Scorelines are point estimates; actual results will vary
- Draw probabilities may be underestimated in Group D (four Tier A teams)
- Model will be retrained once confirmed squads are published (target: June 1 2026)

---

## Version history

| Version | Date | Changes |
|---|---|---|
| v7-math-anchored | 2026-04-30 | Initial submission. Two-layer architecture. Full group stage coverage. |
