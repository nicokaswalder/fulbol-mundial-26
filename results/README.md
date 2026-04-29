# results/ — shared output zone

Every model in this repo writes its predictions here using the same CSV schema. This folder is the **comparison surface** of the project: when models disagree, the bets get interesting.

## Folder layout

```
results/
├── README.md                        # this file
├── _template/                       # copy this to bootstrap your model's folder
│   ├── MODEL.md
│   └── 2026-XX-XX/
│       └── predictions.csv          # blank with header row
├── compound-model/                  # one model per folder
│   ├── 2026-04-28/
│   │   └── predictions.csv
│   └── 2026-05-05/
│       └── predictions.csv
└── <your-model>/
    └── ...
```

**One folder per model. One folder per snapshot date inside it. One CSV per snapshot.** That's it. Older snapshots are kept so we can see how a model's view evolved.

## The schema

All CSVs in `results/` use these eight columns, in this order:

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `as_of_date` | ISO date `YYYY-MM-DD` | yes | The snapshot date. Should match the folder name. |
| 2 | `match_id` | string | yes | Stable identifier. See "Match ID conventions" below. |
| 3 | `market_type` | enum | yes | `match_1x2`, `outright_winner`, `group_winner`, `team_advances`, `top_scorer`, `totals`, `btts` |
| 4 | `outcome` | string | yes | What probability is for. See "Outcome values" below. |
| 5 | `p_model` | float in [0, 1] | yes | Your model's probability. **Probabilities for one (match_id, market_type) should sum to ~1.0** for mutually-exclusive markets. |
| 6 | `confidence` | `high`/`medium`/`low` or float [0, 1] | yes | Your subjective or computed confidence in this row. Pick one convention per model and stick with it; document in your `MODEL.md`. |
| 7 | `model_version` | string | yes | Free-form. Examples: `v1.2`, `2026-05-15-trained`, git short SHA `a1b2c3d`. Anything that lets you tell two snapshots apart. |
| 8 | `notes` | string | optional | Free-form. Use for caveats, e.g. "France: Mbappé doubtful — projected XI updated 2026-06-09". |

## Match ID conventions

Use these patterns so any model's CSVs join cleanly with any other's.

| Market | `match_id` pattern | Example |
|---|---|---|
| Group-stage match | `WC26-<HOME3>-<AWAY3>-<YYYY-MM-DD>` | `WC26-MEX-RSA-2026-06-11` |
| Knockout match (placeholders allowed) | `WC26-R32-01`, `WC26-R16-08`, `WC26-QF-04`, `WC26-SF-02`, `WC26-F` | `WC26-R32-01` |
| Outright winner | `OUTRIGHT-WC2026` | `OUTRIGHT-WC2026` |
| Group winner | `GROUP-<LETTER>-WC2026` | `GROUP-A-WC2026` |
| Team to advance to R32 | `ADVANCE-<TEAM3>-WC2026` | `ADVANCE-MEX-WC2026` |
| Top scorer | `GOLDENBOOT-WC2026` | `GOLDENBOOT-WC2026` |

**Three-letter team codes:** Use FIFA codes (e.g. `MEX`, `RSA`, `KOR`, `CZE`, `ARG`, `BRA`). When in doubt, copy from `compound-model/data/derived/fixtures_wc26.parquet` once it exists, or from the [official FIFA squad list](https://www.fifa.com).

## Outcome values

| Market type | Allowed `outcome` values |
|---|---|
| `match_1x2` | `home`, `draw`, `away` |
| `outright_winner` | three-letter team code (e.g. `ARG`, `FRA`) |
| `group_winner` | three-letter team code |
| `team_advances` | `yes`, `no` |
| `top_scorer` | player full name as it appears on FIFA roster |
| `totals` | `over_2_5`, `under_2_5` (or other lines, named consistently) |
| `btts` | `yes`, `no` |

## Examples

### `match_1x2` row

```csv
as_of_date,match_id,market_type,outcome,p_model,confidence,model_version,notes
2026-04-28,WC26-MEX-RSA-2026-06-11,match_1x2,home,0.62,medium,v1.0,
2026-04-28,WC26-MEX-RSA-2026-06-11,match_1x2,draw,0.21,medium,v1.0,
2026-04-28,WC26-MEX-RSA-2026-06-11,match_1x2,away,0.17,medium,v1.0,
```

### `outright_winner` row (one per team)

```csv
as_of_date,match_id,market_type,outcome,p_model,confidence,model_version,notes
2026-04-28,OUTRIGHT-WC2026,outright_winner,FRA,0.171,medium,v1.0,
2026-04-28,OUTRIGHT-WC2026,outright_winner,ESP,0.166,medium,v1.0,
2026-04-28,OUTRIGHT-WC2026,outright_winner,ENG,0.115,medium,v1.0,
2026-04-28,OUTRIGHT-WC2026,outright_winner,ARG,0.096,medium,v1.0,
... (one row per team you have a view on)
```

You don't have to call every market or every team. **Skip rows you don't have a view on** — comparison code joins on the rows present.

## Validation rules

A `predictions.csv` is "well-formed" if:

1. Header row matches the eight-column schema exactly.
2. Every `as_of_date` value matches the parent folder name.
3. Every `p_model` is in [0, 1].
4. Probabilities for any single (`match_id`, `market_type`) sum to between 0.95 and 1.05 (allow rounding noise) for these market types: `match_1x2`, `outright_winner`, `group_winner`, `team_advances`, `totals`, `btts`. (`top_scorer` is a single-row-per-player market with no sum constraint.)
5. `match_id` follows one of the conventions above.

A simple checker will be added once the first model writes outputs. For now: trust + verify.

## How to start

```bash
# 1. Copy the template into your model's results folder
cp -r results/_template results/<your-model-name>

# 2. Fill in the predictions.csv for your first snapshot
$EDITOR results/<your-model-name>/$(date +%Y-%m-%d)/predictions.csv

# 3. (Once a comparison tool exists) compare against compound-model:
#    python tools/compare.py --date 2026-05-15
```

## Why these specific columns

- **`as_of_date` + dated folder** — lets us replay how a model evolved as new data arrived.
- **`match_id` + `market_type` + `outcome`** — the natural key for joining models. Without all three, comparing two CSVs is brittle.
- **`p_model`** — the only thing comparison tooling actually consumes for edge calculations.
- **`confidence`** — lets us weight comparisons. A high-confidence model disagreeing with a low-confidence one is less interesting than two high-confidence models disagreeing.
- **`model_version`** — separates "the model changed" from "the data changed" when reading historical snapshots.
- **`notes`** — escape hatch. Future-you and other contributors will thank you.

## Things this folder is NOT

- **Not a leaderboard.** No automated scoring lives here. Backtests and PnL tracking happen inside each model's folder.
- **Not a database.** It's a folder of CSVs. Anyone can read them with `cat`, Excel, or `pd.read_csv`.
- **Not a place to put code.** Code lives in the model's folder. `results/` only holds outputs.
- **Not a place to overwrite history.** Older snapshots stay. If you want to revise, write a new snapshot under today's date.
