# Model Card: <your-model-name>

> **Template.** Copy this file into your model folder (`<your-model-name>/MODEL.md`) and fill in every field. Delete this blockquote when done.

| Field | Value |
|---|---|
| **Model name** | <your-model-name> |
| **Author(s)** | Your name + handle |
| **Approach** | One paragraph: is this statistical, market-derived, hand-curated, hybrid? Key methodology in 2-3 sentences. |
| **Stack** | Languages, frameworks, key libraries. Or "spreadsheet" — that's a valid answer. |
| **Data sources** | Where do your inputs come from? List each with a one-line description. |
| **Training window** | Time range of historical data the model uses. |
| **Calibration method** | How do you check if your probabilities are honest? (Walk-forward, holdout, gut check — say what it is.) |
| **Confidence reporting** | How you set the `confidence` column: `high`/`medium`/`low` based on what, or float in [0, 1] based on what. |
| **Update cadence** | How often you write a new snapshot (weekly, daily, ad-hoc). |
| **Output location** | `results/<your-model-name>/<YYYY-MM-DD>/predictions.csv` |
| **Markets covered** | Which `market_type` values you produce (e.g. `match_1x2`, `outright_winner`). |
| **Known limitations** | Be honest. Where does this model fall down? |
| **Validation status** | Plan / built / running / production. |

## Notes for collaborators

Anything else other contributors should know when comparing against your numbers.
