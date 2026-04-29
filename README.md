# fulbol-mundial-26

A **multi-contributor** workbench for predicting the 2026 FIFA World Cup. The goal is simple: every participant brings their own modeling approach, drops their estimations into a common results folder, and the group compares them against prediction-market prices (Kalshi, Polymarket, Hard Rock Bet) to find positive-edge betting opportunities.

The repo is a tournament between approaches. We don't care whether a model is hand-built in a spreadsheet, a Bayesian hierarchy in Stan, or a quick gut-feel tier list — if it produces probabilities and writes them in the standard format, the comparison framework treats them all equally.

## Structure

```
fulbol-mundial-26/
├── README.md                       # this file — project overview
├── compound-model/                 # one model: AI/quant pipeline
│   ├── README.md                   # what this model does
│   ├── MODEL.md                    # standardized model card
│   └── docs/plans/                 # full implementation plan
├── <your-model>/                   # add your own folder here
│   └── MODEL.md
└── results/                        # SHARED output zone
    ├── README.md                   # the schema everyone writes to
    └── _template/                  # blank predictions.csv template
```

## How it works

1. **You build a model** — any methodology. Statistical, market-derived, hand-curated, hybrid.
2. **You produce estimations** — probabilities for the matches/markets you want to call.
3. **You write a CSV** to `results/<your-model-name>/<YYYY-MM-DD>/predictions.csv` following the schema in [`results/README.md`](results/README.md).
4. **You write a `MODEL.md`** in your model folder describing the approach, author, methodology, last update, and any caveats.
5. **The group compares** estimations side-by-side against prediction-market prices to surface where models agree, where they diverge, and where there's an exploitable edge.

## Contributing models

To add your model:

```bash
mkdir <your-model-name>
cp results/_template/MODEL.md <your-model-name>/MODEL.md   # fill in
cp -r results/_template results/<your-model-name>          # your output home
```

Then edit `<your-model-name>/MODEL.md` and start dropping prediction snapshots into `results/<your-model-name>/<date>/predictions.csv`. See [`results/README.md`](results/README.md) for the exact CSV schema — it's eight columns and intentionally simple so a non-coder can produce one in a spreadsheet.

## Models currently in the repo

| Model | Folder | Approach | Status |
|---|---|---|---|
| compound-model | [`compound-model/`](compound-model/) | Python pipeline: Dixon-Coles + Bivariate Poisson with xG-aggregated lineups, 10k-iter Monte Carlo over the 2026 bracket, walk-forward backtest against Euro 2024 / Copa 2024 / WC 2022 | Plan complete (2026-04-28); implementation pending |

Add your row when you join.

## What everyone writes to `results/`

The shared schema is the contract. One CSV per model per day with these columns:

| Column | Example |
|---|---|
| `as_of_date` | 2026-04-28 |
| `match_id` | `WC26-MEXRSA-2026-06-11` (or `OUTRIGHT-WC2026` for futures) |
| `market_type` | `match_1x2`, `outright_winner`, `group_winner`, `team_advances` |
| `outcome` | `home`, `draw`, `away`, or `<TEAM_CODE>` for outrights |
| `p_model` | 0.62 |
| `confidence` | `high`, `medium`, `low` (or numeric 0–1) |
| `model_version` | `v1.0` or git sha |
| `notes` | free-text optional |

Full details in [`results/README.md`](results/README.md).

## Why this format

- **Spreadsheet-friendly.** Anyone can open a CSV in Excel/Numbers, fill rows by hand, and contribute without writing code.
- **Diff-friendly.** Daily snapshots in dated folders make it trivial to track how a model's view evolved (and to spot last-minute changes that suggest information asymmetry).
- **Comparison-friendly.** Every model writing the same columns means a one-liner can join them all and produce the side-by-side table.

## Cost & infrastructure

Free for any contributor. The compound-model has its own credentials section ([`compound-model/README.md`](compound-model/README.md#cost-and-credentials)) — TL;DR $0/month on free API tiers, $30 once for backtest historical odds. Other models may have zero infra cost (e.g. a hand-curated tier list).

## License & ground rules

- Each contributor owns their model folder and their entries in `results/`.
- Do not modify another contributor's `results/<their-model>/...` files.
- Write to your own folder, on your own cadence.
- The bet ledger is private — each participant logs their own bets locally in `bets/ledger.csv` (gitignored).

## World Cup timeline

- **Today: 2026-04-28** — the tournament starts in 6 weeks
- **2026-06-11** — opening match: Mexico vs South Africa, Mexico City
- **2026-07-19** — final
