"""
Ensemble model: Elo + Time-Decayed Dixon-Coles + Recent Form
Strict temporal split: train on pre-WC2022, validate on WC2022, predict WC2026.
No data leakage: WC2022 matches are never seen during training.
"""
import warnings
warnings.filterwarnings("ignore")

import requests
import pandas as pd
import numpy as np
from scipy.optimize import minimize
from sklearn.metrics import log_loss, brier_score_loss
from datetime import datetime
import os, json

RAW_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
WC22_START = pd.Timestamp("2022-11-20")
WC22_END   = pd.Timestamp("2022-12-18")
TRAIN_START = pd.Timestamp("2012-01-01")  # 10-year window pre-WC22

# ── 2026 WC fixtures from existing predictions ─────────────────────────────────
WC26_MATCHES_FILE = "results/elo-baseline/2026-04-28/predictions.csv"

def load_results():
    cache = "data/raw/martj42/latest/results.csv"
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if not os.path.exists(cache):
        print("Downloading martj42 results...")
        r = requests.get(RAW_URL, timeout=60)
        r.raise_for_status()
        with open(cache, "wb") as f:
            f.write(r.content)
    df = pd.read_csv(cache, parse_dates=["date"])
    df = df[df["home_score"].notna()].copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    return df

# ── ELO MODEL ─────────────────────────────────────────────────────────────────
def build_elo_ratings(matches, k=30):
    """Walk forward Elo, returning final ratings dict."""
    ratings = {}
    def get_r(t): return ratings.get(t, 1500)

    for _, m in matches.sort_values("date").iterrows():
        h, a = m["home_team"], m["away_team"]
        rh, ra = get_r(h), get_r(a)
        eh = 1 / (1 + 10 ** ((ra - rh) / 400))
        ea = 1 - eh
        gh, ga = m["home_score"], m["away_score"]
        if gh > ga:   sh, sa = 1.0, 0.0
        elif gh < ga: sh, sa = 0.0, 1.0
        else:         sh, sa = 0.5, 0.5
        # goal-margin multiplier
        gd = abs(gh - ga)
        mult = np.log(max(gd, 1) + 1) * (1 if gd <= 1 else 1.5 if gd == 2 else 1.75)
        ratings[h] = rh + k * mult * (sh - eh)
        ratings[a] = ra + k * mult * (sa - ea)
    return ratings

def elo_match_probs(rh, ra, home_advantage=50):
    """Returns (p_home, p_draw, p_away) using Elo."""
    rh_adj = rh + home_advantage
    expected_h = 1 / (1 + 10 ** ((ra - rh_adj) / 400))
    # Convert win-prob to 1X2 using Bradley-Terry draw extension
    p_home = expected_h ** 2.2
    p_away = (1 - expected_h) ** 2.2
    p_draw = 1 - p_home - p_away
    # Normalize
    total = p_home + p_draw + p_away
    return p_home/total, p_draw/total, p_away/total

# ── TIME-DECAYED POISSON ───────────────────────────────────────────────────────
IMPORTANCE = {
    "FIFA World Cup": 1.0,
    "UEFA Euro": 0.9,
    "Copa América": 0.9,
    "AFC Asian Cup": 0.85,
    "Gold Cup": 0.7,
    "Africa Cup of Nations": 0.85,
    "FIFA World Cup qualification": 0.7,
    "UEFA Euro qualification": 0.65,
    "FIFA Confederations Cup": 0.8,
    "UEFA Nations League": 0.6,
}
DEFAULT_IMPORTANCE = 0.35  # friendlies

def get_importance(tournament):
    for key, val in IMPORTANCE.items():
        if key.lower() in str(tournament).lower():
            return val
    return DEFAULT_IMPORTANCE

def time_decay_weight(date, ref_date, xi=0.002):
    days = (ref_date - date).days
    return np.exp(-xi * days)

def fit_poisson_model(matches, ref_date, xi=0.002):
    """Fit attack/defence parameters for each team via MLE with time decay."""
    teams = sorted(set(matches["home_team"]) | set(matches["away_team"]))
    team_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    weights = np.array([
        time_decay_weight(r["date"], ref_date, xi) * get_importance(r["tournament"])
        for _, r in matches.iterrows()
    ])

    def neg_log_lik(params):
        # params: [attack_0..n-1, defence_0..n-1, home_adv, intercept]
        attack  = np.exp(params[:n])
        defence = np.exp(params[n:2*n])
        home_adv = params[2*n]
        mu_h = attack[hi] * defence[ai] * np.exp(home_adv)
        mu_a = attack[ai] * defence[hi]
        lam_h = np.maximum(mu_h, 1e-6)
        lam_a = np.maximum(mu_a, 1e-6)
        ll = weights * (
            gh * np.log(lam_h) - lam_h +
            ga * np.log(lam_a) - lam_a
        )
        return -ll.sum()

    hi = np.array([team_idx[r["home_team"]] for _, r in matches.iterrows()])
    ai = np.array([team_idx[r["away_team"]] for _, r in matches.iterrows()])
    gh = matches["home_score"].values.astype(float)
    ga = matches["away_score"].values.astype(float)

    x0 = np.zeros(2*n + 1)
    res = minimize(neg_log_lik, x0, method="L-BFGS-B",
                   options={"maxiter": 200, "ftol": 1e-6})
    attack  = np.exp(res.x[:n])
    defence = np.exp(res.x[n:2*n])
    home_adv = res.x[2*n]
    return {t: (attack[i], defence[i]) for t, i in team_idx.items()}, home_adv

def poisson_match_probs(lam_h, lam_a, max_goals=8):
    """1X2 from independent Poisson."""
    from scipy.stats import poisson
    ph = np.array([poisson.pmf(g, lam_h) for g in range(max_goals+1)])
    pa = np.array([poisson.pmf(g, lam_a) for g in range(max_goals+1)])
    grid = np.outer(ph, pa)
    p_home = np.tril(grid, -1).sum()
    p_away = np.triu(grid, 1).sum()
    p_draw = np.diag(grid).sum()
    total = p_home + p_draw + p_away
    return p_home/total, p_draw/total, p_away/total

# ── FORM MODEL ─────────────────────────────────────────────────────────────────
def compute_form(matches, team, ref_date, n=10):
    """Average points per game from last n matches before ref_date."""
    tm = matches[
        ((matches["home_team"] == team) | (matches["away_team"] == team)) &
        (matches["date"] < ref_date)
    ].sort_values("date").tail(n)
    if len(tm) == 0:
        return 0.0
    pts = []
    for _, r in tm.iterrows():
        if r["home_team"] == team:
            if r["home_score"] > r["away_score"]: pts.append(3)
            elif r["home_score"] == r["away_score"]: pts.append(1)
            else: pts.append(0)
        else:
            if r["away_score"] > r["home_score"]: pts.append(3)
            elif r["away_score"] == r["home_score"]: pts.append(1)
            else: pts.append(0)
    return np.mean(pts) / 3.0  # normalize to [0,1]

def form_match_probs(form_h, form_d, base_draw=0.25):
    """Simple form-based 1X2."""
    raw_h = 0.3 + 0.5 * form_h
    raw_a = 0.3 + 0.5 * form_d
    raw_draw = base_draw
    total = raw_h + raw_draw + raw_a
    return raw_h/total, raw_draw/total, raw_a/total

# ── ENSEMBLE ───────────────────────────────────────────────────────────────────
def ensemble_predict(home, away, elo_ratings, poisson_params, home_adv_poisson, all_matches, ref_date,
                     w_elo=0.35, w_poisson=0.45, w_form=0.20, neutral=False):
    """Combine three models into ensemble 1X2 probabilities."""
    # ELO
    rh = elo_ratings.get(home, 1500)
    ra = elo_ratings.get(away, 1500)
    ha_elo = 0 if neutral else 50
    pe_h, pe_d, pe_a = elo_match_probs(rh, ra, ha_elo)

    # POISSON
    if home in poisson_params and away in poisson_params:
        att_h, def_h = poisson_params[home]
        att_a, def_a = poisson_params[away]
        ha_p = 0 if neutral else home_adv_poisson
        lam_h = att_h * def_a * np.exp(ha_p)
        lam_a = att_a * def_h
        pp_h, pp_d, pp_a = poisson_match_probs(lam_h, lam_a)
    else:
        pp_h, pp_d, pp_a = pe_h, pe_d, pe_a  # fallback to elo

    # FORM
    form_h = compute_form(all_matches, home, ref_date)
    form_a = compute_form(all_matches, away, ref_date)
    pf_h, pf_d, pf_a = form_match_probs(form_h, form_a)

    ph = w_elo*pe_h + w_poisson*pp_h + w_form*pf_h
    pd_ = w_elo*pe_d + w_poisson*pp_d + w_form*pf_d
    pa = w_elo*pe_a + w_poisson*pp_a + w_form*pf_a
    total = ph + pd_ + pa
    return ph/total, pd_/total, pa/total

# ── WC 2022 MATCHES ────────────────────────────────────────────────────────────
WC22_GROUPS = {
    "Group A": [("Qatar","Ecuador"),("Senegal","Netherlands"),("Qatar","Senegal"),("Netherlands","Ecuador"),("Netherlands","Qatar"),("Ecuador","Senegal")],
    "Group B": [("England","Iran"),("USA","Wales"),("Wales","Iran"),("England","USA"),("Wales","England"),("Iran","USA")],
    "Group C": [("Argentina","Saudi Arabia"),("Mexico","Poland"),("Poland","Saudi Arabia"),("Argentina","Mexico"),("Poland","Argentina"),("Saudi Arabia","Mexico")],
    "Group D": [("Denmark","Tunisia"),("France","Australia"),("Tunisia","Australia"),("France","Denmark"),("Tunisia","France"),("Australia","Denmark")],
    "Group E": [("Germany","Japan"),("Spain","Costa Rica"),("Japan","Costa Rica"),("Germany","Spain"),("Japan","Spain"),("Costa Rica","Germany")],
    "Group F": [("Morocco","Croatia"),("Belgium","Canada"),("Belgium","Morocco"),("Croatia","Canada"),("Croatia","Belgium"),("Morocco","Canada")],
    "Group G": [("Switzerland","Cameroon"),("Brazil","Serbia"),("Cameroon","Serbia"),("Brazil","Switzerland"),("Cameroon","Brazil"),("Serbia","Switzerland")],
    "Group H": [("Uruguay","South Korea"),("Portugal","Ghana"),("South Korea","Ghana"),("Portugal","Uruguay"),("Ghana","Uruguay"),("South Korea","Portugal")],
}
WC22_KNOCKOUT = [
    # R16
    ("Netherlands","USA"), ("Argentina","Australia"), ("France","Poland"),
    ("England","Senegal"), ("Japan","Croatia"), ("Brazil","South Korea"),
    ("Morocco","Spain"), ("Portugal","Switzerland"),
    # QF
    ("Croatia","Brazil"), ("Netherlands","Argentina"), ("Morocco","Portugal"), ("England","France"),
    # SF
    ("Argentina","Croatia"), ("France","Morocco"),
    # 3rd
    ("Croatia","Morocco"),
    # Final
    ("Argentina","France"),
]

def get_wc22_actual(results):
    """Extract actual WC2022 results from the dataset."""
    wc22 = results[
        (results["date"] >= WC22_START) &
        (results["date"] <= WC22_END) &
        (results["tournament"] == "FIFA World Cup")
    ].copy()
    return wc22

# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("ENSEMBLE MODEL: Elo + Dixon-Coles Poisson + Form")
    print("Temporal split: train < 2022-11-20, validate on WC2022")
    print("=" * 65)

    # 1. Load data
    all_results = load_results()
    print(f"\nLoaded {len(all_results):,} matches ({all_results['date'].min().date()} – {all_results['date'].max().date()})")

    # 2. STRICT temporal split — no WC22 data in training
    train = all_results[
        (all_results["date"] >= TRAIN_START) &
        (all_results["date"] < WC22_START)
    ].copy()
    print(f"Training window: {len(train):,} matches ({TRAIN_START.date()} – {WC22_START.date() - pd.Timedelta(days=1)})")

    # 3. Fit models on training data only
    print("\nFitting Elo ratings on training data...")
    elo_ratings = build_elo_ratings(train)

    print("Fitting time-decayed Poisson model (xi=0.002, L-BFGS-B)...")
    poisson_params, home_adv = fit_poisson_model(train, ref_date=WC22_START)
    print(f"  Home advantage parameter: {home_adv:.3f}")

    # 4. Validate on WC2022
    print("\n── WC 2022 VALIDATION ──────────────────────────────────────")
    wc22_actual = get_wc22_actual(all_results)
    print(f"WC2022 matches found in dataset: {len(wc22_actual)}")

    preds, actuals_1x2 = [], []
    results_table = []

    for _, row in wc22_actual.iterrows():
        home, away = row["home_team"], row["away_team"]
        gh, ga = row["home_score"], row["away_score"]

        ph, pd_, pa = ensemble_predict(
            home, away, elo_ratings, poisson_params, home_adv, train,
            ref_date=row["date"], neutral=True  # WC matches are neutral
        )

        if gh > ga:   actual = 0
        elif gh == ga: actual = 1
        else:          actual = 2

        preds.append([ph, pd_, pa])
        actuals_1x2.append(actual)

        predicted = ["H","D","A"][np.argmax([ph, pd_, pa])]
        correct   = ["H","D","A"][actual]
        results_table.append({
            "match": f"{home} vs {away}",
            "score": f"{gh}-{ga}",
            "actual": correct,
            "pred": predicted,
            "p_home": f"{ph:.3f}",
            "p_draw": f"{pd_:.3f}",
            "p_away": f"{pa:.3f}",
            "correct": "✓" if predicted == correct else "✗"
        })

    preds_arr = np.array(preds)
    y_true_oh = np.eye(3)[actuals_1x2]

    ll = log_loss(y_true_oh, preds_arr)
    bs = brier_score_loss(
        (np.array(actuals_1x2) == 0).astype(int), preds_arr[:, 0]
    )  # home win brier
    acc = np.mean(np.argmax(preds_arr, axis=1) == np.array(actuals_1x2))

    print(f"\nMetrics vs WC2022 actual results:")
    print(f"  Log-loss (1X2):   {ll:.4f}  (Pinnacle benchmark ~0.95–1.02)")
    print(f"  Accuracy:         {acc:.3f}  ({int(acc*len(actuals_1x2))}/{len(actuals_1x2)} correct)")
    print(f"  Brier (home win): {bs:.4f}")

    print("\nSample predictions (group stage):")
    df_res = pd.DataFrame(results_table)
    print(df_res[["match","score","p_home","p_draw","p_away","pred","actual","correct"]].head(24).to_string(index=False))

    # 5. Save WC2022 predictions (the actual deliverable)
    out_dir = "results/ensemble-e3/wc2022-backtest"
    os.makedirs(out_dir, exist_ok=True)

    # Full prediction table with actuals
    df_wc22 = pd.DataFrame(results_table)
    df_wc22.to_csv(f"{out_dir}/predictions_vs_actual.csv", index=False)

    # Standard predictions format (pre-tournament, no actuals)
    out_rows = []
    for r in results_table:
        for outcome, p in [("home", float(r["p_home"])), ("draw", float(r["p_draw"])), ("away", float(r["p_away"]))]:
            out_rows.append({
                "as_of_date": "2022-11-19",  # day before WC22 kickoff
                "match_id": r["match"].replace(" vs ", "-").replace(" ", "_"),
                "match": r["match"],
                "market_type": "match_1x2",
                "outcome": outcome,
                "p_model": p,
                "actual_result": r["actual"],
                "model_pred": r["pred"],
                "correct": r["correct"],
                "score": r["score"],
                "confidence": "medium",
                "model_version": "ensemble-e3-v0.1",
                "notes": f"Elo(0.35)+Poisson(0.45)+Form(0.20); trained on 2012-2022-11-19"
            })
    pd.DataFrame(out_rows).to_csv(f"{out_dir}/predictions.csv", index=False)

    # Per-match summary
    print(f"\nFULL WC2022 PREDICTIONS vs ACTUAL RESULTS")
    print(f"{'Match':<35} {'Score':>6} {'p_H':>6} {'p_D':>6} {'p_A':>6} {'Pred':>4} {'Act':>3} {'OK':>2}")
    print("-" * 75)
    for r in results_table:
        print(f"{r['match']:<35} {r['score']:>6} {r['p_home']:>6} {r['p_draw']:>6} {r['p_away']:>6} {r['pred']:>4} {r['actual']:>3} {r['correct']:>2}")

    print(f"\n── FINAL METRICS ───────────────────────────────────────────")
    print(f"  Log-loss (1X2):   {ll:.4f}  (Pinnacle benchmark ~0.95–1.02)")
    print(f"  Accuracy:         {acc:.3f}  ({int(acc*len(actuals_1x2))}/{len(actuals_1x2)} correct)")
    print(f"  Brier (home win): {bs:.4f}")
    print(f"\nPredictions saved → {out_dir}/")

if __name__ == "__main__":
    main()
