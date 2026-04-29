---
title: "feat: World Cup 2026 prediction-market edge finder (Python CLI + notebooks)"
type: feat
status: active
date: 2026-04-28
---

# feat: World Cup 2026 prediction-market edge finder (Python CLI + notebooks)

## Overview

A single-user Python toolkit that, on a weekly cadence, ingests odds for the 2026 FIFA World Cup from Kalshi, Polymarket, and Hard Rock Bet (via The Odds API), runs an internal Dixon-Coles + xG-derived model that simulates the tournament, and prints one dense comparison table per match showing where our model disagrees with the consensus and which book is offering the disagreement at the best price. The user reads the table in the terminal or in a notebook, decides which bets to place manually, and logs them to a CSV ledger so we can score the model's calibration after each match-day.

The first usable version ships before the user wants to place outright/group-stage futures (target: within 7 days from 2026-04-28). The model is then refit and recalibrated weekly through the tournament (kickoff 2026-06-11).

## Problem Frame

The user wants a defensible edge against US-accessible prediction markets and sportsbooks for the WC 2026. Three constraints shape the design:

1. **Cycle is short.** ~6 weeks until kickoff and the user wants to bet on outrights now. Anything that doesn't ship in week 1 has to wait. Output 100% prioritizes "table I can act on" over polish.
2. **Markets are heterogeneous.** Kalshi event contracts, Polymarket binary YES/NO tokens, and Hard Rock 1X2 sportsbook odds all express probability differently and all carry different vig structures. Comparing them requires a uniform devigged probability space.
3. **International football is data-sparse.** WC teams play 8-12 competitive games per cycle. A pure goal-based Poisson on national-team results will overfit. The model must lean on club-level xG aggregated through projected lineups, plus FIFA/World Football Elo as a Bayesian prior.

The user explicitly does not want graphical output; they want "complex insights presented in an easy-to-digest form" — i.e. dense tabular CLI/notebook output with markdown summaries, not plots.

## Requirements Trace

- **R1.** Pull current market prices for every WC 2026 match and every WC outright/group market from Kalshi, Polymarket, and Hard Rock Bet (Hard Rock via The Odds API).
- **R2.** Pull a sharp baseline (Pinnacle via The Odds API) for fair-value reference.
- **R3.** Run an internal probabilistic model that produces a 1X2 probability (and an outright/group-advance probability) for every WC 2026 fixture.
- **R4.** Express every market price and the model output in the same devigged probability space and surface `edge = p_model - p_market_devigged` per (match, outcome, book).
- **R5.** Render one comparison table that the user can read and act on in <2 minutes per week.
- **R6.** Validate the model with walk-forward backtests against Euro 2024, Copa America 2024, and WC 2022 closing odds; report log-loss, Brier, RPS, and ECE.
- **R7.** Log placed bets and post-match outcomes so we can score realized ROI and CLV against Pinnacle close.
- **R8.** Refit the model weekly during qualifiers and the tournament without manual ceremony — one CLI command.

## Scope Boundaries

- No live in-play odds tracking. Snapshot polling is sufficient (weekly out-of-tournament, daily on match-days).
- No automated bet placement. The user places bets manually on each platform.
- No graphical/visualization output (matplotlib, plotly). Tables only.
- No multi-user / web service / dashboard. CLI + notebook on the user's laptop.
- No live LLM agents. "Agents" in the user's brief are scrapers — we model them as plain Python functions and CLI subcommands.

### Deferred to Separate Tasks

- **Hierarchical Bayesian DC (PyMC)** — deferred. MVP uses MLE Dixon-Coles. Bayesian uncertainty is a v2 if we have time after the group stage.
- **Correct-score and totals markets** — deferred. MVP covers 1X2, outright winner, and group-advance only. Scorelines and over/under come from the same DC simulation but we won't ship a comparison view for them in v1.
- **Closing-line value tracker** — partial. We log placed bets but a full CLV harness against time-aligned Pinnacle closes is a v2.
- **Polymarket on-chain trading** — out of scope. We read prices, we don't trade.

## Context & Research

### Relevant Code and Patterns

This is a greenfield repo (only `README.md` exists at the project root). All patterns will be established by this plan. The most relevant external reference implementation is `penaltyblog` (Dixon-Coles, BVP, Kelly, time-decay) — the project will use it directly rather than re-implement.

### Institutional Learnings

No prior `docs/solutions/` entries exist in this repo. Document one after the first betting cycle.

### External References

Match modeling and devigging — distilled from research; see "Sources & References" for full list:

- **Dixon-Coles** with exponential time-decay is the practitioner default for football. `penaltyblog` provides a working MLE implementation, Kelly utilities, and a backtester.
- **Bivariate Poisson (Karlis & Ntzoufras 2003)** is the better choice when feeding xG-derived means because it captures positive goal correlation. Available in `penaltyblog`.
- **Shin devig** is the right method for outright/futures (handles favorite-longshot bias). **Power devig** is best for 1X2 per Clarke 2017. Multiplicative is fast and used as a sanity baseline.
- **Pinnacle closing line is the canonical fair-value baseline** — beating it by ≥1% in log-odds is the success bar.
- **2026 format is new**: 12 groups of 4 → top 2 + 8 best thirds → Round of 32 → standard knockout. The Monte Carlo must respect cross-group third-place tiebreakers (points, GD, GF, fair play, drawing of lots).

### API surfaces (all confirmed accessible from Python in 2026)

- **Kalshi Trading API v2** — `https://api.elections.kalshi.com/trade-api/v2`. **Read endpoints (`/series`, `/events`, `/markets`, `/markets/{ticker}/orderbook`) accept unauthenticated GETs** — verified live on 2026-04-28; earlier external research stating "auth required even for reads" was wrong. RSA-PSS signing is only required for trading. Five WC series we'll ingest: `KXMENWORLDCUP` (outright winner, 56 binary team markets), `KXWCGAME` (per-match 1X2, 54+ events keyed by `KXWCGAME-26<DATE><HOMEAWY>`), `KXWCGROUPWIN` (group winner A–L), `KXFIFAADVANCE` (binary "team to advance"), `KXWCGOALLEADER` (Golden Boot). Official `kalshi-python` SDK on PyPI for trading; for reads, plain `httpx` is enough. Demo env: `https://demo-api.kalshi.co/trade-api/v2`.
- **Polymarket Gamma API** — `https://gamma-api.polymarket.com`. No auth for read. `/events?slug=2026-fifa-world-cup`, `/markets?event_id=...`. Prices in 0–1 USDC = implied probability directly. Plain `httpx` is sufficient; no SDK needed for snapshot polling.
- **Hard Rock Bet** — no public API exists (Kambi B2B feed only). Pulled through **The Odds API** which lists `hardrockbet` as a US bookmaker key.
- **The Odds API v4** — `https://api.the-odds-api.com/v4`. Sport key likely `soccer_fifa_world_cup` (verify via `GET /sports` once tournament is in active list). Returns `h2h` as 3-way for soccer including draw outcome. Includes Pinnacle in `eu` region. Pricing: **free tier (500 credits/mo) is sufficient for live polling** — one call to `/odds?regions=us,eu&markets=h2h` returns all matches and costs 2 credits, so weekly polling ≈ 8 credits/mo, daily during the tournament ≈ 60 credits/mo. The $30/mo plan (20k credits) is only needed once if we want a thorough historical-odds backtest (10× multiplier on historical = ~880 credits across WC 2022 + Euro 2024 + Copa 2024).
- **Free data**: `soccerdata` PyPI package wraps FBref, Understat, ClubElo, Football-Data.co.uk; eloratings.net (national-team Elo, scrape via `pandas.read_html`); StatsBomb Open Data on GitHub for Euro 2024, Copa 2024, WC 2022 event-level priors.

## Key Technical Decisions

- **Language: Python 3.12** with `uv` for env and lockfile management. Single-process CLI; no microservices.
- **CLI: Typer** (named subcommands like `wc26 odds pull`, `wc26 model fit`, `wc26 compare`). One entry point in `src/wc26/cli.py`.
- **Storage: SQLite (`data/wc26.db`) + parquet snapshots in `data/derived/`**. SQLite is enough for 104 matches × weekly polls; parquet for analyst-friendly notebook reads. Schema migrations via plain SQL files in `src/wc26/storage/migrations/`. No ORM.
- **Cost posture: $0/month operating cost.** All required APIs (Kalshi reads, Polymarket Gamma, The Odds API free tier, FBref, eloratings.net, StatsBomb) have free tiers sufficient for one analyst polling weekly or even daily. The only optional charge is **$30 once** on The Odds API's $30/mo plan to fetch historical odds for backtesting (Unit 10), then drop back to free. Hosting is the user's laptop — no cloud, no DB, no scheduler.
- **Modeling: `penaltyblog`** for Dixon-Coles / Bivariate Poisson + Kelly + time-decay. `mberk/shin` for Shin devig. `scikit-learn` for calibration (`CalibratedClassifierCV`, `log_loss`, `brier_score_loss`).
- **Output: `rich` tables** in the terminal; `pandas` DataFrames + markdown cells in notebooks. No matplotlib by default. The comparison table is the canonical view; everything else feeds it.
- **No async.** Weekly polling against 4 APIs takes seconds; a sequential `for` loop with `httpx.Client` and explicit per-source rate limiting is simpler and sufficient.
- **Devig defaults: Power for 1X2, Shin for outrights/futures, multiplicative as sanity-check.** Each market table column shows `p_devig_power | p_devig_shin` so the user can see method sensitivity at a glance.
- **Sharp consensus baseline = Pinnacle close.** Edge is computed twice: vs each individual book, and vs Pinnacle. We bet only when both edges are positive (≥3% vs the targeted book AND ≥1.5% vs Pinnacle).
- **Single-rep model run per week** — we don't ensemble at v1. Dixon-Coles fed by xG-aggregated team ratings is the model. Adding a LightGBM blend is deferred to v2 unless backtest log-loss is worse than Pinnacle.
- **No ML agents.** The user's brief asked whether we need "multiple agents to capture data". For a single-user CLI on weekly cadence, plain Python functions per source are simpler, debuggable, and version-controllable. We revisit only if a source requires LLM-driven scraping (e.g. Hard Rock direct).
- **Primary source for international match results: `martj42/international_results` GitHub CSV** (verified live 2026-04-28: 49,328 rows, 49,256 played, current through 2026-03-31; schema `date, home_team, away_team, home_score, away_score, tournament, city, country, neutral`). Pulled via `httpx` from raw GitHub URL; daily snapshot to `data/raw/martj42/<YYYY-MM-DD>/results.csv`; canonicalized + importance-weighted into `data/derived/internationals.parquet`. Cross-checked weekly against eloratings.net.
- **No Kalshi auth required at v1.** The `.env.example` lists `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` as **optional** — only generate them if/when the user wants to place a trade through the API rather than the Kalshi web UI. The full comparison-table workflow runs without them.

## Open Questions

### Resolved During Planning

- **Should we run a hierarchical Bayesian DC?** Resolved: not in v1. MLE DC ships in days; PyMC adds a week of fitting/diagnostic work for marginal calibration gain. Deferred.
- **Three markets at launch or phased?** Resolved: all three at launch — Kalshi, Polymarket, Hard Rock (via Odds API), plus Pinnacle baseline. Hard Rock through The Odds API is one extra config line.
- **Which odds aggregator?** Resolved: The Odds API ($30/mo). It covers Hard Rock + Pinnacle + 6 other US books in one call; the per-credit cost makes our weekly footprint trivial.
- **Where do we store data?** Resolved: SQLite + parquet snapshots, both in `data/`. `data/` is gitignored except `data/derived/fixtures_wc26.parquet` which is checked in for reproducibility.
- **How many bookmakers' regions to pull?** Resolved: `regions=us,eu` on The Odds API. US covers Hard Rock and the major US books; EU covers Pinnacle.

### Deferred to Implementation

- **Exact xG-to-team-rating aggregation formula.** We know the shape (sum player_xG90 × predicted_minutes / 90 across projected XI + bench weight), but the precise minutes prediction and bench weight will be tuned during model fit (Unit 5).
- **Recency-decay `xi`.** Cross-validated during fit (Unit 7). Expected range 0.001–0.003 (~1–3 year half-life).
- **Match-importance weights.** Will start at WC=1.0, Euro/Copa=0.9, WCQ=0.7, Nations League=0.6, friendly=0.35, then sensitivity-test in backtest.
- **Group-stage in-tournament refit cadence.** Daily after each match-day vs once per round. Decide once we see how much group results move team posteriors.

## Validation Findings (2026-04-28)

Live spot-checks performed against the actual data sources before committing this plan.

**martj42 dataset** (`results.csv`, 3.5MB, raw GitHub URL): pulled successfully, 49,328 rows / 49,256 played, current through 2026-03-31 (last day of March FIFA window — April has zero played matches as expected, no FIFA window). Modern training window (2018+) has 7,961 matches; recent window (2024-2026) has 2,398 matches. Top-12 favorites have 95–106 matches each since 2018; smallest WC qualifiers floor at ~77. **Verdict: sufficient for time-decayed Dixon-Coles with shrinkage.**

**Kalshi WC market depth** (verified live, no auth):
- Outright winner (`KXMENWORLDCUP-26`): 56 binary markets. Top of field on 2026-04-28: France 17.1%, Spain 16.6%, England 11.5%, Argentina 9.6%, Brazil 9.3%. Mexico 1.9%, South Africa 0.1%. **Volume = 0 across the board** — these are illiquid futures.
- Per-match (`KXWCGAME-26JUN11MEXRSA`): Mexico 65% / Tie 21% / RSA 14% (sums to 100% — Kalshi has already devigged this market). No recorded volume.
- Group A winner (`KXWCGROUPWIN-26A`): Mexico 48%, Korea 23%, Czechia 21%, South Africa 5%; sum across visible options 107% — that 7% is the vig (plus phantom teams, see Risks).

**Implications already folded into this plan:**
1. Kalshi reads are unauthenticated — `.env` keys are optional, simplifying Unit 1 and Unit 3.
2. Five Kalshi series (`KXMENWORLDCUP`, `KXWCGAME`, `KXWCGROUPWIN`, `KXFIFAADVANCE`, `KXWCGOALLEADER`) replace the single-stream assumption in Unit 3.
3. Pre-May 2026 futures lack volume; the comparison table needs a `min_volume` filter to avoid flagging "edges" against operator risk-modeled prices (see Risks).
4. Group-winner markets contain phantom-team rows (placeholder teams at 1–8% as overround buffer) that must be filtered before devigging (see Risks).
5. The Odds API free tier (500 credits/mo) is sufficient — `/odds` is per-call, not per-match, and weekly polling costs ~8 credits/mo. The $30 plan is only needed once for the historical-odds backtest.

## Output Structure

```
fulbol-mundial-26/
├── pyproject.toml                 # uv project, deps pinned
├── uv.lock
├── .env.example                   # ODDS_API_KEY, KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH
├── README.md
├── data/
│   ├── raw/                       # gitignored, per-source snapshots
│   ├── derived/                   # gitignored except fixtures_wc26.parquet
│   │   └── fixtures_wc26.parquet  # checked in for reproducibility
│   └── wc26.db                    # gitignored, SQLite
├── src/wc26/
│   ├── __init__.py
│   ├── cli.py                     # Typer entry: `wc26 ...`
│   ├── config.py                  # env vars, paths, constants
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                  # connection helpers
│   │   └── migrations/            # 001_init.sql, 002_*.sql
│   ├── data/
│   │   ├── fixtures.py            # WC 2026 schedule + groups
│   │   ├── fbref.py               # via soccerdata
│   │   ├── elo.py                 # eloratings.net + ClubElo
│   │   ├── statsbomb.py           # Euro/Copa/WC22 backtest data
│   │   └── lineups.py             # injuries, projected XI
│   ├── markets/
│   │   ├── kalshi.py
│   │   ├── polymarket.py
│   │   ├── odds_api.py            # Hard Rock + Pinnacle + others
│   │   ├── normalize.py           # uniform Match × Outcome × Book schema
│   │   └── devig.py               # Shin, Power, multiplicative
│   ├── model/
│   │   ├── ratings.py             # team strength aggregation (Elo + xG-weighted lineup)
│   │   ├── features.py            # rest, travel, host, altitude
│   │   ├── dixon_coles.py         # wraps penaltyblog
│   │   └── simulate.py            # Monte Carlo 2026 tournament (12×4 + best thirds)
│   ├── analysis/
│   │   ├── edges.py               # model_p − devigged_p per (match, outcome, book)
│   │   ├── kelly.py               # half-Kelly with edge thresholds
│   │   └── compare.py             # rich-table renderer
│   └── eval/
│       ├── backtest.py            # walk-forward harness
│       └── calibration.py         # log-loss, Brier, RPS, ECE, calibration table
├── notebooks/
│   ├── 01_data_explore.ipynb
│   ├── 02_model_fit.ipynb
│   ├── 03_backtest_calibration.ipynb
│   ├── 04_weekly_review.ipynb     # the main weekly artifact
│   └── 05_bet_ledger.ipynb        # PnL + calibration of placed bets
├── bets/
│   └── ledger.csv                 # gitignored except header schema
└── tests/
    ├── test_devig.py
    ├── test_kelly.py
    ├── test_simulate.py
    ├── test_features.py
    └── test_normalize.py
```

The tree is the expected shape, not a contract. The implementer may move files if a better structure emerges. Per-unit `**Files:**` sections are authoritative.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Data flow (one weekly run)

```
            ┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐
            │ FBref / xG   │  │ eloratings.net  │  │ StatsBomb open  │
            │ (soccerdata) │  │  + ClubElo      │  │ (Euro24/WC22…)  │
            └──────┬───────┘  └────────┬────────┘  └────────┬────────┘
                   ▼                   ▼                    ▼
              ┌──────────────────────────────────────────────────┐
              │   Team-strength ratings (xG-weighted lineup +    │
              │   Elo prior + recency decay + match weights)     │
              └────────────────────────┬─────────────────────────┘
                                       ▼
                    ┌──────────────────────────────────┐
                    │  Dixon-Coles / Bivariate Poisson │
                    │  (penaltyblog) → λ_home, λ_away  │
                    │     → 1X2 + score grid           │
                    └────────────────┬─────────────────┘
                                     ▼
                       ┌────────────────────────────┐
                       │  Tournament Monte Carlo    │
                       │  10k iters, 2026 format,   │
                       │  ET + penalty rules        │
                       │  → outright / group-advance│
                       └─────────────┬──────────────┘
                                     ▼
                          ┌──────────────────┐
                          │  p_model         │
                          └─────────┬────────┘
                                    │
       ┌──────────┐ ┌────────────┐ ┌▼──────────────┐ ┌──────────┐
       │ Kalshi   │ │ Polymarket │ │ Hard Rock /   │ │ Pinnacle │
       │ (signed) │ │ (Gamma)    │ │ Odds API (US) │ │ (eu)     │
       └────┬─────┘ └─────┬──────┘ └────────┬──────┘ └────┬─────┘
            ▼             ▼                 ▼             ▼
       ┌──────────────────────────────────────────────────────┐
       │ markets.normalize → uniform (match, outcome, book)   │
       │ markets.devig    → p_devig_power, p_devig_shin       │
       └─────────────────────────┬────────────────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │ analysis.edges:                    │
                │  edge_book   = p_model - p_book    │
                │  edge_pinny  = p_model - p_pinny   │
                │ analysis.kelly: half-Kelly stake   │
                │ analysis.compare: rich table       │
                └───────────────┬────────────────────┘
                                ▼
                ┌──────────────────────────────────┐
                │  Terminal table  +  notebook df   │
                │  bets/ledger.csv (manual append)  │
                └──────────────────────────────────┘
```

### Comparison-table shape (one row per match × outcome × book)

| Match            | Side  | p_model | Pinny p* | Edge vs Pinny | Best book   | Best price (dec) | Implied | Edge | ½-Kelly stake |
|------------------|-------|---------|----------|---------------|-------------|------------------|---------|------|---------------|
| ARG vs CAN (Jun11) | ARG W | 0.62    | 0.58     | +4.0%         | Hard Rock   | 1.83             | 0.546   | +7.4%| 1.6% bankroll |
| ARG vs CAN (Jun11) | Draw  | 0.21    | 0.24     | -3.0%         | —           | —                | —       | —    | —             |
| ARG vs CAN (Jun11) | CAN W | 0.17    | 0.18     | -1.0%         | —           | —                | —       | —    | —             |

Outright/group-advance markets get a separate sub-table with the same columns. `p_devig_power` and `p_devig_shin` are shown side-by-side for the favored book so the user can see method sensitivity. Negative-edge rows are dimmed but kept for context.

## Implementation Units

Implementation is grouped into four phases. Phase 1 must complete before the user places their first bet.

### Phase 1 — Working comparison table (target: 7 days)

- [ ] **Unit 1: Project scaffolding + data layer**

**Goal:** A runnable `wc26` CLI that loads config from `.env`, opens a SQLite database via migrations, and exits cleanly with `wc26 --help`.

**Requirements:** R8 (one-command operation).

**Dependencies:** None.

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `.env.example`, `.gitignore`
- Create: `src/wc26/__init__.py`, `src/wc26/cli.py`, `src/wc26/config.py`
- Create: `src/wc26/storage/__init__.py`, `src/wc26/storage/db.py`, `src/wc26/storage/migrations/001_init.sql`
- Create: `tests/test_storage.py`

**Approach:**
- `uv init` then add deps: `typer`, `rich`, `httpx`, `pandas`, `numpy`, `scipy`, `scikit-learn`, `penaltyblog`, `soccerdata`, `kalshi-python`, `python-dotenv`, `pyarrow`, `pytest`.
- `config.py` loads `.env` and validates required keys (`ODDS_API_KEY`, `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`). Missing keys raise on first use, not at import.
- `storage/db.py` opens a SQLite connection at `data/wc26.db`, applies migrations on startup, returns a connection. No ORM.
- Initial schema (`001_init.sql`): `matches`, `team_ratings`, `market_snapshots`, `model_probs`, `placed_bets`, `match_outcomes`. Wide tables with `as_of` timestamps; we re-derive on query rather than mutating in place.
- `cli.py` registers Typer subcommand groups: `data`, `markets`, `model`, `compare`, `eval`. v1 has stubs for each.

**Patterns to follow:** Standard Python project layout (`src/` layout, `pyproject.toml`-driven). Typer's `app.add_typer` for grouped subcommands.

**Test scenarios:**
- *Happy path:* `wc26 --help` lists all subcommand groups and exits 0.
- *Happy path:* `db.connect()` applies migrations idempotently — calling it twice does not fail or duplicate tables.
- *Edge case:* missing `.env` raises a clear "create `.env` from `.env.example`" error, not a `KeyError`.
- *Edge case:* migration applied to a fresh DB matches schema applied to an existing DB after re-run (no orphan columns).

**Verification:**
- `uv run wc26 --help` succeeds.
- `uv run pytest tests/test_storage.py` passes.
- `data/wc26.db` is created with all expected tables.

---

- [ ] **Unit 2: Static fixture data (WC 2026 schedule + groups)**

**Goal:** A canonical, version-controlled list of the 104 WC 2026 matches with date, kickoff, venue, host country, group, and the 48 participating teams placed into 12 groups.

**Requirements:** R1 (need fixture identifiers to align market data), R3 (model needs the slate).

**Dependencies:** Unit 1.

**Files:**
- Create: `src/wc26/data/fixtures.py`
- Create: `data/derived/fixtures_wc26.parquet` (checked in)
- Create: `tests/test_fixtures.py`

**Approach:**
- One-time scrape from the official FIFA fixture page (or Wikipedia 2026 FIFA World Cup knockout stage / group stage pages, which have proven reliable in `pandas.read_html`).
- Persist to parquet. The CLI command `wc26 data fixtures refresh` re-pulls; daily idempotent.
- Each fixture has `match_id` (e.g. `WC26-001`), `kickoff_utc`, `home_team`, `away_team`, `venue`, `host_country`, `stage` (`group`/`R32`/`R16`/`QF`/`SF`/`F`), `group` (A–L for groups).
- Knockout slots that are unresolved (e.g. "Winner Group A") get placeholder team codes that the simulator resolves.

**Patterns to follow:** None — this file is the pattern.

**Test scenarios:**
- *Happy path:* `fixtures.load()` returns 104 rows. 72 group-stage rows, 32 knockout rows.
- *Happy path:* every group A–L has exactly 4 teams and 6 matches.
- *Edge case:* knockout placeholder teams are flagged `is_placeholder=True` and excluded from initial Elo lookup.
- *Integration:* `fixtures.load()` reads from parquet without network access.

**Verification:**
- `wc26 data fixtures refresh` updates the parquet.
- Unit tests pass.

---

- [ ] **Unit 3: Market ingestion — Kalshi, Polymarket, Odds API**

**Goal:** Three pull functions that, given a fresh-enough fixture table, return a normalized `MarketSnapshot` table with `(match_id_or_event_id, outcome, book, raw_price, implied_prob, fetched_at)` rows.

**Requirements:** R1, R2.

**Dependencies:** Units 1, 2.

**Files:**
- Create: `src/wc26/markets/__init__.py`, `src/wc26/markets/kalshi.py`, `src/wc26/markets/polymarket.py`, `src/wc26/markets/odds_api.py`, `src/wc26/markets/normalize.py`
- Modify: `src/wc26/cli.py` (add `wc26 markets pull [--source]`)
- Create: `tests/test_normalize.py`, `tests/test_markets_kalshi.py`, `tests/test_markets_polymarket.py`, `tests/test_markets_odds_api.py`

**Approach:**
- **Kalshi:** unauthenticated `httpx` GETs against `/trade-api/v2/{series,events,markets}` (verified live 2026-04-28). Iterate the five WC series — `KXMENWORLDCUP`, `KXWCGAME`, `KXWCGROUPWIN`, `KXFIFAADVANCE`, `KXWCGOALLEADER` — pulling all events under each, then markets per event. Match ticker convention is `KXWCGAME-26<DATE><HOMEAWY>` (e.g. `KXWCGAME-26JUN11MEXRSA`); parse to recover `match_id`. For group-winner markets, **filter out phantom-team rows** (Kalshi includes 1-8% placeholder rows for non-qualified teams as overround buffer; e.g. Group A includes Ireland/Denmark/N. Macedonia at ~1-8%) by inner-joining against the qualified-team list from `data/derived/fixtures_wc26.parquet`. For outright/group, store as `event_id`. **Volume-based actionability filter:** drop any market with `volume == 0` from the actionable comparison view; keep in the informational view. RSA signing is *only* needed if and when the user trades, not for reads.
- **Polymarket:** plain `httpx`. `GET /events?slug=2026-fifa-world-cup&closed=false`. For each event, list markets; each binary market's `lastTradePrice` (or mid of `bestBid`/`bestAsk` if available) maps directly to implied probability. Tag matches by parsing market titles against fixture team names (fuzzy matching via `rapidfuzz` with a confidence threshold and a manual override table for known mismatches).
- **The Odds API:** `httpx.get("/v4/sports/soccer_fifa_world_cup/odds", params={"apiKey": ..., "regions": "us,eu", "markets": "h2h,outrights"})`. Walk `bookmakers` array; emit one snapshot row per (market, outcome, book). Filter to `hardrockbet` and `pinnacle` for the canonical analysis but retain all books for reference.
- **Normalization:** `markets/normalize.py` defines a single dataclass `MarketSnapshot` and a dispatch function `to_snapshots(source, raw) -> list[MarketSnapshot]`. Outcome strings are canonicalized: `"home"`, `"draw"`, `"away"`, or `team_code` for outrights/advance markets.
- **Match resolution.** A central `resolve_match(book_event_label) -> match_id | None` helper handles fuzzy team-name matching. Misses are logged to `data/raw/unresolved_<source>_<date>.jsonl` for manual review, never silently dropped.
- **Rate limiting.** Per-source `time.sleep` between calls based on documented limits; for weekly polling this is trivial overhead. No async.

**Patterns to follow:** Each source module exports `pull(client, fixtures: pd.DataFrame) -> pd.DataFrame` with the same signature.

**Test scenarios:**
- *Happy path:* recorded fixture (`tests/fixtures/odds_api_sample.json`) parses into N expected `MarketSnapshot` rows with correct outcome canonicalization.
- *Happy path:* draw is preserved as a third outcome for soccer `h2h` markets.
- *Edge case:* Polymarket binary YES at price 0.50 implies probability 0.50 (not 0.50 / total).
- *Edge case:* an Odds API response with a missing book returns rows for the present books and does not error.
- *Edge case:* fuzzy match below threshold returns `None` and writes to the unresolved log.
- *Integration:* `wc26 markets pull --source all` writes a row to `market_snapshots` for at least one match per source against recorded responses.
- *Edge case:* Kalshi `KXWCGROUPWIN-26A` markets list teams not in Group A (phantom-team buffer); `pull` filters them out by inner-joining against `fixtures_wc26.parquet` before emitting snapshots.
- *Edge case:* Kalshi market with `volume == 0` is captured but flagged `actionable=False` so the comparison table can hide it from the Kelly view.
- *Error path:* a 401 from Kalshi (only possible if RSA-signed *trading* call is added later) raises a typed `KalshiAuthError` with a helpful message, not a stack trace.
- *Error path:* The Odds API monthly credit quota exhausted (response header `x-requests-remaining: 0`) logs a warning but writes the partial response.

**Verification:**
- `uv run pytest tests/test_markets_*` passes.
- `wc26 markets pull --source all` produces ≥1 snapshot per source against live APIs (or recorded fixtures in CI).

---

- [ ] **Unit 4: Devigging + market consensus**

**Goal:** Convert raw market probabilities (which include vig) into devigged probabilities using Power, Shin, and multiplicative methods. Compute a "Pinnacle baseline" devigged probability per match × outcome.

**Requirements:** R4 (uniform probability space), R5 (one comparison view).

**Dependencies:** Unit 3.

**Files:**
- Create: `src/wc26/markets/devig.py`
- Create: `tests/test_devig.py`

**Approach:**
- Three pure functions: `power(probs)`, `shin(probs)`, `multiplicative(probs)`. All take a list of raw implied probabilities for one event's mutually exclusive outcomes and return a list summing to 1.0 (within float tolerance).
- For 1X2: pass `[home, draw, away]`. For outrights with N teams: pass all N. The Power method solves `sum(p_i^k) = 1` numerically (Newton's method or `scipy.optimize.brentq`); start k=1.
- Shin uses the `mberk/shin` package (already in deps).
- `consensus(snapshots, method='power') -> DataFrame` joins all books for a match × outcome, devigs per-book, and emits the per-book devigged prob plus the Pinnacle-only baseline.

**Patterns to follow:** Pure functions, well-tested. No I/O.

**Test scenarios:**
- *Happy path:* given vig'd 1X2 (0.45, 0.30, 0.30), power-devig sum is 1.0 ± 1e-9.
- *Happy path:* power method on a fair-priced event (sum already 1.0) returns the inputs unchanged.
- *Edge case:* outright with 32 teams summing to 1.08 devigs to within tolerance for both Power and Shin.
- *Edge case:* one outcome priced at 0.99 (heavy favorite) does not produce numerically unstable Shin output.
- *Error path:* probabilities containing 0 or negatives raise `ValueError` rather than producing NaN.
- *Integration:* `consensus()` against a recorded multi-book Odds API snapshot returns one Pinnacle row per outcome and matches a hand-calculated benchmark within 0.5%.

**Verification:**
- `uv run pytest tests/test_devig.py` passes.
- For a known historical event (e.g. WC 2022 final), Pinnacle Power-devig matches published fair-value sources.

---

- [ ] **Unit 5: Baseline model — implied-only fair value**

**Goal:** A v0 model that computes `p_model = Pinnacle Power-devig` so we can ship the comparison table on day 7 even before Dixon-Coles is fit. This establishes the comparison pipeline end-to-end and gives the user a usable artifact while we build the real model.

**Requirements:** R3 (need *a* p_model), R5.

**Dependencies:** Units 3, 4.

**Files:**
- Create: `src/wc26/model/baseline.py`
- Modify: `src/wc26/cli.py` (`wc26 compare --model baseline`)
- Create: `src/wc26/analysis/__init__.py`, `src/wc26/analysis/edges.py`, `src/wc26/analysis/kelly.py`, `src/wc26/analysis/compare.py`
- Create: `tests/test_kelly.py`, `tests/test_edges.py`

**Approach:**
- `model/baseline.py` simply wraps `markets.devig` to expose `predict_match(match_id) -> {home, draw, away, …}` using Pinnacle. When Pinnacle is missing, fall back to power-devigged median across books.
- `analysis/edges.py` joins p_model with per-book devigged probs and computes `edge = p_model - p_book_devig` per (match, outcome, book). Also returns `edge_vs_pinnacle`.
- `analysis/kelly.py` computes `f* = (b*p - q) / b` then applies a `0.5` multiplier (half-Kelly) and clips to a 2% bankroll cap. Returns 0 if either edge condition is unmet (≥3% vs book AND ≥1.5% vs Pinnacle baseline).
- `analysis/compare.py` renders a `rich.table.Table` to stdout, sorted by `edge` descending. Notebook variant returns a styled `pd.DataFrame`.

**Note:** The baseline is a stepping stone, but it can also detect *book vs book* mispricing (e.g. Kalshi vs Pinnacle) which is genuine edge even before our internal model exists. So Unit 5 is shippable on its own.

**Patterns to follow:** Pure-function analysis layer, with all I/O in `cli.py`.

**Test scenarios:**
- *Happy path:* `wc26 compare --model baseline` against a recorded snapshot prints a table with at least one row per WC 2026 match.
- *Happy path:* a book priced 5% better than Pinnacle on a 1X2 outcome shows up with positive `edge_vs_pinnacle`.
- *Edge case:* a match present in Hard Rock but absent in Pinnacle is shown with `edge_vs_pinnacle=NaN` and `kelly=0`, not dropped.
- *Edge case:* Kelly clamps to 2% bankroll cap on extreme edges (e.g. 25%).
- *Integration:* the CLI returns non-zero exit code if no markets were ingested in the last 24 hours, prompting the user to run `markets pull` first.

**Verification:**
- The user runs `wc26 markets pull --source all && wc26 compare --model baseline` and gets a sorted table they can act on.

---

### Phase 2 — Internal Dixon-Coles model (target: +7 days)

- [ ] **Unit 6: Team-strength ratings**

**Goal:** A weekly-rebuildable team-rating table for all 48 WC 2026 squads combining (a) FIFA / World Football Elo prior, (b) club-xG-aggregated lineup strength, (c) recent international form with time decay.

**Requirements:** R3.

**Dependencies:** Unit 1; new dep: `soccerdata`.

**Files:**
- Create: `src/wc26/data/fbref.py`, `src/wc26/data/elo.py`, `src/wc26/data/lineups.py`
- Create: `src/wc26/model/__init__.py`, `src/wc26/model/ratings.py`
- Modify: `src/wc26/cli.py` (`wc26 data refresh`, `wc26 model ratings`)
- Create: `tests/test_ratings.py`

**Approach:**
- `data/elo.py`: scrape eloratings.net via `pandas.read_html`. Persist to `team_ratings`. Cache 24h.
- `data/fbref.py`: `soccerdata.FBref` to pull current-season player xG/xGA per 90 for the top 5 European leagues + MLS + Liga MX + Brasileirão. Aggregate by national team via player country (FBref includes nationality). Cache 7d (FBref scraper is brittle).
- `data/lineups.py`: maintain a per-country YAML file `data/lineups/<TEAM>.yml` with projected XI + bench. Manually curated; one-time effort per team. CLI subcommand `wc26 data lineup edit ARG` opens `$EDITOR`.
- `model/ratings.py`: combine signals as `attack = 0.4*elo_attack + 0.4*xg_lineup_attack + 0.2*recent_form_attack` (weights tuned in Unit 8). Symmetric for defence.

**Patterns to follow:** Each `data/*.py` module exports `refresh()` (writes raw + cache) and `load()` (reads cache, raises if stale). `cli.py` only orchestrates.

**Test scenarios:**
- *Happy path:* `wc26 data refresh` populates ratings for all 48 WC teams.
- *Happy path:* `model.ratings.compute(asof='2026-04-28')` returns 48 rows with finite `attack` and `defence`.
- *Edge case:* a country with fewer than 5 listed players in the lineup YAML still gets a rating, weighted-down by a coverage penalty rather than NaN.
- *Edge case:* if `soccerdata.FBref` raises (Cloudflare 403), the function returns the last good cache and warns.
- *Error path:* an unknown team code raises `UnknownTeamError`.
- *Integration:* recomputing twice on the same day returns identical numbers (idempotent).

**Verification:**
- Sanity: top-rated teams approximately match consensus (Spain, France, Argentina, Brazil, England in some order). Bottom-rated should look reasonable.

---

- [ ] **Unit 7: Dixon-Coles + Bivariate Poisson match model**

**Goal:** Given two team ratings and a match context (rest, travel, host, altitude), produce `(λ_home, λ_away)` and a 1X2 + score-grid distribution.

**Requirements:** R3.

**Dependencies:** Units 2, 6; uses `penaltyblog`.

**Files:**
- Create: `src/wc26/model/features.py`, `src/wc26/model/dixon_coles.py`
- Modify: `src/wc26/model/__init__.py`
- Create: `tests/test_features.py`, `tests/test_dixon_coles.py`

**Approach:**
- `features.py`: pure functions for `rest_days`, `travel_km` (haversine over venue coords), `host_advantage` (1.0 for USA/MEX/CAN at home venue, 0.6 for "regional" hosts, 0.0 for neutral), `altitude_m`.
- `dixon_coles.py`: wraps `penaltyblog.models.DixonColesGoalModel` (or BivariatePoisson). Fits on a ~10-year window of international matches with our match-importance weights and time-decay `xi`. Predict yields a fair-value 1X2 plus score grid. Exposes `predict(home, away, context) -> ModelOutput`.
- Predictions for unbalanced matchups (top vs minnow) are clamped to a sane range (no >99% probabilities) to avoid overconfident model output dominating the comparison.

**Execution note:** Implement `features.py` test-first — these are pure deterministic functions and getting them wrong silently corrupts the model. Dixon-Coles wrapping can follow conventional development since `penaltyblog` is well-tested upstream.

**Patterns to follow:** `penaltyblog` examples in their docs (https://penaltyblog.readthedocs.io/).

**Test scenarios:**
- *Happy path:* `features.rest_days` between two known fixtures returns expected integer.
- *Happy path:* `features.travel_km(LosAngeles, NewYork)` ≈ 3940km ± 50.
- *Happy path:* DC model on Euro 2024 final returns probabilities summing to 1.0 ± 1e-9.
- *Edge case:* host_advantage for a Mexico match in Mexico City returns 1.0; for Mexico in Toronto returns 0.6.
- *Edge case:* a team with very few internationals in the training window (e.g. a debut WC participant) produces a wide-but-finite prediction, not NaN.
- *Integration:* model.predict applied to all 72 WC 2026 group-stage fixtures completes in under 60s.

**Verification:**
- DC fit log-loss on a holdout slice of WC 2022 group games is within 5% of Pinnacle-devigged closing log-loss. (We tighten this in Unit 9.)

---

- [ ] **Unit 8: Tournament Monte Carlo simulator**

**Goal:** Given the match model, simulate the full WC 2026 bracket 10,000+ times respecting the 12-group → top 2 + best 8 thirds → R32 format, producing per-team outright-winner probabilities, group-advance probabilities, "reach R16/QF/SF/Final" probabilities.

**Requirements:** R3, R5.

**Dependencies:** Units 2, 7.

**Files:**
- Create: `src/wc26/model/simulate.py`
- Modify: `src/wc26/cli.py` (`wc26 model simulate --iters 10000`)
- Create: `tests/test_simulate.py`

**Approach:**
- For each iteration: simulate every group-stage match with the DC score grid (sample a (h_goals, a_goals) pair per match). Compute group standings using FIFA tiebreakers in order: points, GD, GF, head-to-head points, head-to-head GD, head-to-head GF, fair-play points (random in sim), drawing of lots (random).
- Determine top 2 per group + 8 best third-place teams across the 12 groups using cross-group tiebreakers.
- Map advancing teams into the R32 bracket per the official 2026 bracket structure.
- Knockout matches: simulate FT with DC. If draw, simulate ET (extend λ by 30/90). If still draw, sample penalty shootout: each side scores ~75% of attempts (configurable per team based on historical PK rate); first to 5 attempts then sudden-death.
- Aggregate per-team probabilities and write to `model_probs` table.
- Vectorize where possible (numpy goal sampling) but leave the bracket logic procedural; 10k iters at <60s is the bar.

**Execution note:** Test-first. Bracket logic is the kind of code that silently produces "looks reasonable" output even when it's wrong. Snapshot-test against known WC 2022 outcomes in characterization mode before trusting the 2026 numbers.

**Patterns to follow:** None directly in repo. Cross-reference Wikipedia 2026 FIFA World Cup knockout stage page for bracket structure.

**Test scenarios:**
- *Happy path:* 10k simulation of a 4-team mock group with deterministic equal teams produces ~25% group-winner probability per team.
- *Happy path:* outright winner probabilities across all 48 teams sum to 1.0 ± 1e-6.
- *Edge case:* a 0-0 ET into penalty shootout terminates and yields one winner per simulation (no infinite loops).
- *Edge case:* group with three teams tied on points/GD/GF resolves via deterministic tie-breaker chain ending in random draw.
- *Edge case:* "best 8 thirds" picks exactly 8 teams across 12 groups, never 7 or 9.
- *Integration:* simulating with a single dominant team (artificial λ=4 for one side) produces that team's outright probability >50%.
- *Error path:* simulation with an invalid bracket (e.g. missing a team) raises `BracketError`.

**Verification:**
- `wc26 model simulate --iters 10000` writes `model_probs` rows for all 48 teams across all advancement targets in <60s.
- Manual sanity-check: top-5 outright probabilities are recognizable favorites.

---

- [ ] **Unit 9: Replace baseline with internal model in compare**

**Goal:** `wc26 compare --model dc` runs the full pipeline (data refresh → ratings → DC fit → simulate → compare) and emits the comparison table using `p_model` from our model rather than Pinnacle.

**Requirements:** R3, R4, R5.

**Dependencies:** Units 5, 6, 7, 8.

**Files:**
- Modify: `src/wc26/analysis/edges.py`, `src/wc26/analysis/compare.py`, `src/wc26/cli.py`
- Create: `tests/test_compare_dc.py`

**Approach:**
- `compare.py` accepts a `model` parameter: `baseline` (Phase 1) or `dc` (Phase 2). Internally swaps the source of `p_model`.
- The table now also surfaces `model_disagreement = p_model - p_pinnacle` so the user can see where our model is sticking its neck out vs the sharps.
- Compare table additions: `kalshi_p`, `polymarket_p`, `hardrock_p`, `pinnacle_p`, `p_model`, `model_vs_pinny`, `best_book`, `best_price`, `edge_vs_book`, `edge_vs_pinny`, `½-kelly`. Keep it under ~12 columns; drop columns the user can recompute on demand in the notebook.

**Patterns to follow:** Unit 5's compare module structure.

**Test scenarios:**
- *Happy path:* `wc26 compare --model dc` runs end-to-end against recorded data and prints a table.
- *Happy path:* a match where p_model > Pinnacle by 5pp shows positive `model_vs_pinny`.
- *Edge case:* the DC model and Pinnacle are perfectly aligned → `model_vs_pinny` ≈ 0 and no row hits the bet threshold.
- *Integration:* the table is also retrievable as a DataFrame inside `notebooks/04_weekly_review.ipynb`.

**Verification:**
- The user runs the full Phase-2 pipeline and gets a model-driven comparison table that flags real edges.

---

### Phase 3 — Validation, calibration, and weekly workflow (target: +5 days)

- [ ] **Unit 10: Walk-forward backtest harness**

**Goal:** A reusable backtester that trains the model up to a date, predicts the next event window, scores log-loss / Brier / RPS / ECE against actual outcomes, and tests realized-EV against historical Pinnacle closing odds.

**Requirements:** R6.

**Dependencies:** Units 6, 7, 8.

**Files:**
- Create: `src/wc26/eval/__init__.py`, `src/wc26/eval/backtest.py`, `src/wc26/eval/calibration.py`
- Create: `notebooks/03_backtest_calibration.ipynb`
- Modify: `src/wc26/cli.py` (`wc26 eval backtest --tournament wc22|euro24|copa24`)
- Create: `tests/test_backtest.py`, `tests/test_calibration.py`

**Approach:**
- StatsBomb Open Data + Football-Data.co.uk historical odds CSVs feed the backtester.
- Walk-forward: for each tournament, fit on data through the day before each match, predict, compare. Log-loss, Brier, RPS via `sklearn`. ECE via 10-bin calibration table.
- Realized EV: for every bet our `kelly` rule would have placed (≥3% edge after Power devig vs Pinnacle close), record stake × (price-1) on win, -stake on loss. Sum for tournament-level ROI.
- Output: a markdown summary table that the user can drop into a doc — no charts.

**Patterns to follow:** sklearn metrics; `penaltyblog`'s built-in backtester for the inner loop.

**Test scenarios:**
- *Happy path:* `wc26 eval backtest --tournament wc22` returns finite metrics for each round.
- *Happy path:* model log-loss on WC 2022 group stage is ≤ 1.05 × Pinnacle-devigged log-loss (the bar is "competitive with the sharpest book").
- *Edge case:* a tournament with no recorded Pinnacle odds reports model metrics only and skips realized EV with a warning.
- *Edge case:* extra-time/penalty matches are scored on FT regulation outcome, not knockout winner (matches our 1X2 model output).
- *Error path:* requesting an unsupported tournament returns a typed error listing supported keys.

**Verification:**
- The table in `notebooks/03_backtest_calibration.ipynb` shows model performance is within striking distance of Pinnacle on Euro 2024 + WC 2022; if not, surface specific failure modes for v2.

---

- [ ] **Unit 11: Calibration adjustment + Kelly thresholds**

**Goal:** A temperature-scaling step that nudges the model's probabilities toward the calibration curve observed in backtest, plus tuning Kelly thresholds based on backtest realized EV.

**Requirements:** R6.

**Dependencies:** Unit 10.

**Files:**
- Modify: `src/wc26/model/dixon_coles.py` (add `apply_calibration`)
- Modify: `src/wc26/eval/calibration.py` (compute and persist the temperature)
- Modify: `src/wc26/analysis/kelly.py` (load thresholds from config)
- Create: `data/derived/calibration.json` (gitignored)

**Approach:**
- After Unit 10, fit a single temperature parameter `T` on the calibration curve from the most recent two tournaments (Euro 2024 + Copa 2024). Apply `softmax(logits / T)` at predict time.
- Backtest sweep across edge thresholds {2%, 2.5%, 3%, 4%, 5%} and Kelly multipliers {0.25, 0.5} to pick the one with best out-of-sample realized EV given drawdown constraints.
- Persist chosen thresholds to `data/derived/calibration.json`. Ratios are loaded by `analysis.kelly` at runtime.

**Patterns to follow:** `sklearn` `CalibratedClassifierCV` is overkill for a single T parameter; implement directly with `scipy.optimize.minimize_scalar` on log-loss.

**Test scenarios:**
- *Happy path:* fitted T values fall in (0.5, 2.0) — outside that range suggests the underlying model is mis-specified.
- *Happy path:* applying T=1.0 leaves probabilities unchanged.
- *Edge case:* if the calibration curve is too noisy (insufficient data), default to T=1.0 with a warning.
- *Integration:* `wc26 compare` after this unit uses the calibrated probabilities transparently.

**Verification:**
- ECE on the post-calibration backtest is ≤ ECE pre-calibration. If not, revert.

---

- [ ] **Unit 12: Weekly review notebook + bet ledger**

**Goal:** A notebook the user opens every Sunday (and after each match-day during the tournament) that runs the pipeline, displays the comparison table, accepts bet entries, and tracks PnL.

**Requirements:** R5, R7, R8.

**Dependencies:** Units 9, 11.

**Files:**
- Create: `notebooks/04_weekly_review.ipynb`, `notebooks/05_bet_ledger.ipynb`
- Create: `bets/.gitkeep`, `bets/ledger.csv` (header only, gitignored from row 2)
- Modify: `src/wc26/cli.py` (`wc26 bet log --match ARG-CAN --side home --book hardrock --price 1.83 --stake 50`, `wc26 bet score`)

**Approach:**
- `04_weekly_review.ipynb`:
  1. Run pipeline (cell 1: refresh data, fit model, simulate).
  2. Render comparison table sorted by edge (cell 2).
  3. Show a tighter "actionable rows only" subset where Kelly stake > 0 (cell 3).
  4. Show outright/group-advance subtable (cell 4).
- `05_bet_ledger.ipynb`:
  1. Read `bets/ledger.csv`.
  2. After each match-day, score open bets against actual outcomes.
  3. Render running PnL table (no charts) and a calibration table comparing model probabilities against realized outcomes for placed bets — this is the closing-line-value proxy.
- The ledger schema: `placed_at, match_id, side, book, decimal_price, implied_p_at_bet, p_model_at_bet, p_pinnacle_at_bet, edge_at_bet, kelly_stake_pct, stake_usd, status, settled_at, payout_usd`.

**Patterns to follow:** Plain CSV + pandas. No SQLAlchemy. Notebook outputs are styled DataFrames + markdown.

**Test scenarios:**
- *Happy path:* `wc26 bet log` appends a row with a generated UUID and `status='open'`.
- *Happy path:* `wc26 bet score` against a fixture with a known outcome flips status to `'won'` or `'lost'` and computes payout.
- *Edge case:* logging a bet for a match the user has already bet on the same side is allowed (multiple stakes), but flagged in the notebook view.
- *Edge case:* settling a bet on a match without a recorded outcome leaves status as `'open'` and warns.
- *Integration:* a full cycle (log → simulate match outcome via test fixture → score) produces correct PnL.

**Verification:**
- The user runs the notebook on Sunday, sees the table, places bets, logs them, and runs `bet score` after each match-day to see PnL update.

---

### Phase 4 — Tournament operations (continuous, June 11 – July 19, 2026)

- [ ] **Unit 13: In-tournament refit cadence + monitoring**

**Goal:** Document and codify the weekly (and during-tournament daily) refit workflow so the user can run it without thinking, and so we can review what we've learned after the tournament.

**Requirements:** R8.

**Dependencies:** All prior units.

**Files:**
- Create: `docs/runbook.md`
- Create: `docs/solutions/2026-XX-XX-wc26-postmortem.md` (write at end of tournament)
- Modify: `src/wc26/cli.py` (`wc26 weekly` — single command running the whole pipeline)

**Approach:**
- `wc26 weekly` is a thin wrapper that runs `data refresh → model ratings → markets pull --source all → model simulate → compare --model dc` and pipes all logs to `data/raw/weekly_<date>.log`.
- Document the workflow in `docs/runbook.md`: cron snippet (optional `0 9 * * 0` Sunday morning), what to do if a source 4xx's, when to re-edit the lineup YAMLs (after squad announcements ~10 days pre-kickoff and after each match in case of suspensions/injuries).
- Post-tournament: write a solution doc capturing realized ROI, calibration vs Pinnacle, model failure modes, and what to keep/drop for the next cycle.

**Patterns to follow:** None — this is documentation + thin orchestration.

**Test scenarios:**
- *Happy path:* `wc26 weekly` against recorded data runs all five stages and writes a log.
- *Edge case:* one source failing does not abort the others; the comparison table renders with a "missing book" indicator.

**Verification:**
- A weekly run takes <5 minutes wall-clock on the user's laptop.
- The runbook is intelligible to a teammate who has not seen the project before.

## System-Wide Impact

- **Interaction graph:** All four data sources are read-only; no inter-source coupling beyond the `match_id` join key. Failures in one source do not block others.
- **Error propagation:** Per-source failures are caught at the CLI command boundary, logged, and the pipeline continues with the data it has. The compare table marks missing-book columns with `—`.
- **State lifecycle risks:** The bet ledger is the only mutable user-owned data outside the SQLite cache. We never overwrite `bets/ledger.csv`; we only append. SQLite snapshots are reproducible from cached parquet, so DB corruption is recoverable.
- **API surface parity:** CLI, notebook, and tests share the same Python module entry points. Anything available in the CLI is available in the notebook as a plain function call, and vice versa.
- **Integration coverage:** End-to-end tests against recorded JSON fixtures from each market source live in `tests/test_compare_dc.py`. They are slow but should run in CI on every commit.
- **Unchanged invariants:** None — this is a greenfield project.

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| **The Odds API doesn't list `soccer_fifa_world_cup` until close to kickoff.** | Fall back to the existing soccer keys (`soccer_uefa_european_championship`-style) for backtest data. For live, monitor `GET /sports`; the user can manually toggle the sport key in `.env`. |
| **`soccerdata.FBref` breaks due to Cloudflare bot defense.** | Cache aggressively (7 days). Pin `soccerdata` version. If it breaks mid-tournament, fall back to a manually maintained CSV of player xG ratings (one-time scrape from FBref public CSV exports). |
| **Hard Rock Bet odds via The Odds API are stale or thin.** | The Odds API documents Hard Rock as supported but stale data is a known industry issue. Treat Hard Rock prices as one of three offers, not the source of truth; require both `edge_vs_pinnacle` AND `edge_vs_book` to be positive before betting. |
| **Polymarket prices are illiquid for non-headline markets.** | Use mid of `bestBid`/`bestAsk` rather than last trade price; require minimum `volume_24hr` to consider a Polymarket price actionable. Skip if volume < $10k. |
| **Model log-loss is worse than Pinnacle on backtest.** | This is the failure mode that kills the project. Mitigation: Unit 10 explicitly gates on this metric; if model is worse, we fall back to baseline (Pinnacle-devigged) for `p_model` and only bet on book-vs-Pinnacle disagreements rather than model-vs-market. |
| **2026 format edge cases in the simulator (best-8-thirds, cross-group ties).** | Snapshot tests against deterministic synthetic groups in Unit 8. Manual sanity-check on real teams' published outright odds before betting any outright. |
| **Kelly over-staking.** | Half-Kelly + 2% bankroll cap + minimum-edge thresholds are all hard-coded in `analysis.kelly`. Any change requires updating tests. |
| **Polymarket access from US (legal/jurisdictional).** | We only read public odds — we do not place trades on Polymarket. The user's bets go through Kalshi (US-regulated) or Hard Rock (US sportsbook). Polymarket is information only. |
| **Time pressure forces a v0 with no real model.** | Unit 5 explicitly ships a baseline pipeline that finds book-vs-book edges before the DC model is built. The user can place bets using v0 in week 1 and let v1 catch up. |
| **Kalshi futures markets are illiquid pre-May 2026** (verified 2026-04-28: every WC market has `volume == 0`). Acting on a 1-2pp "edge" against an operator's risk-modeled price with no trade history is noise, not signal. | `analysis.compare` applies a `min_volume` filter (default: actionable only when book-volume > 0; configurable per-market). Pre-May futures appear in the *informational* table but are excluded from the *actionable* subset and from Kelly stake suggestions. Re-enable as volume materialises closer to kickoff. |
| **Kalshi group-winner markets include phantom teams** (verified 2026-04-28: `KXWCGROUPWIN-26A` lists Ireland, Denmark, North Macedonia at 1–8% as overround buffer although they are not in Group A). Devigging across phantom rows distorts the implied probabilities for the four real teams. | Inner-join Kalshi group-winner markets against the qualified-team list from `data/derived/fixtures_wc26.parquet` *before* devigging. Phantom rows are dropped silently (logged at DEBUG); only the four qualified teams contribute to the Power/Shin normalization. |
| **`martj42` dataset maintainer abandons the repo** (single point of failure for the primary international-results feed). | Daily immutable snapshot to `data/raw/martj42/<YYYY-MM-DD>/results.csv` plus weekly cross-check against eloratings.net match table. If `martj42` stops updating, the cross-check surfaces the staleness within 7 days and we promote eloratings.net to primary. |

## Documentation / Operational Notes

- `README.md` to be expanded as part of Unit 1 with a quick-start: install `uv`, copy `.env.example`, run `wc26 weekly`.
- `docs/runbook.md` (Unit 13) covers weekly cadence, in-tournament daily cadence, troubleshooting common API errors.
- `docs/solutions/` will hold post-tournament learnings, written after July 19, 2026.
- API-key rotation: Kalshi keys are tied to the user's account; document key creation steps in the runbook. The Odds API key is monthly-billed; document the credit dashboard URL.
- The user's bet ledger is private financial data. Confirm `.gitignore` excludes `bets/ledger.csv` rows and `data/wc26.db`.

## Sources & References

External research (April 2026):
- Dixon-Coles paper: Dixon & Coles (1997), JRSS-C
- Karlis & Ntzoufras (2003) on bivariate Poisson
- Constantinou & Fenton (2012) on Ranked Probability Score for football
- Wilkens (2026), "Can simple models predict football", SAGE
- `penaltyblog` library and docs: https://penaltyblog.readthedocs.io/
- `soccerdata`: https://soccerdata.readthedocs.io/
- `mberk/shin` Python package: https://github.com/mberk/shin
- StatsBomb Open Data: https://github.com/statsbomb/open-data
- Polymarket Gamma API: https://docs.polymarket.com/developers/gamma-markets-api
- Polymarket py-clob-client: https://github.com/Polymarket/py-clob-client
- Kalshi API docs: https://docs.kalshi.com
- The Odds API v4: https://the-odds-api.com/liveapi/guides/v4/
- The Odds API bookmaker list: https://the-odds-api.com/sports-odds-data/bookmaker-apis.html
- 2026 World Cup format and tiebreakers (ESPN): https://www.espn.com/soccer/story/_/id/47108758/2026-fifa-world-cup-format-tiebreakers-fixtures-schedule
- 2026 FIFA World Cup knockout stage (Wikipedia): https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
- Kambi–Hard Rock Odds Feed+ partnership confirms no public Hard Rock API.
- Devig methods (Clarke 2017): https://outlier.bet/wp-content/uploads/2023/08/2017-clarke-adjusting_bookmakers_odds.pdf
