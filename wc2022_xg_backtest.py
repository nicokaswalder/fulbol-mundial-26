"""
WC 2022 Backtest — xG-Patched Ensemble
Three independent models trained on pre-WC-2022 data, tested on all 64 WC 2022 matches.

Models:
  1. elo-baseline       — walk-forward Elo with goal-margin multiplier
  2. form-last-10       — avg points per game, last 10 matches per team
  3. poisson-xg         — Dixon-Coles Poisson, xG replaces goals where StatsBomb data exists
  ensemble-v2           — equal weight (33/33/33) of the three above
  ensemble-e3 (bench)   — loaded from existing file; Elo+goals-Poisson+Form blend

Output:
  Per-match comparison table (all models + ensemble + actual result)
  Summary metrics table (log-loss, accuracy, Brier per model)
  results/poisson-xg/wc2022-backtest/predictions.csv
  results/ensemble-v2/wc2022-backtest/predictions.csv
"""
import warnings, os, csv
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
from sklearn.metrics import log_loss, brier_score_loss
from pathlib import Path

ROOT = Path(__file__).parent

# ── CONSTANTS ──────────────────────────────────────────────────────────────────
TRAIN_START  = pd.Timestamp("2012-01-01")
WC22_START   = pd.Timestamp("2022-11-20")
WC22_END     = pd.Timestamp("2022-12-18")

IMPORTANCE = {
    "FIFA World Cup": 1.0, "UEFA Euro": 0.9, "Copa América": 0.9,
    "AFC Asian Cup": 0.85, "Gold Cup": 0.7, "Africa Cup of Nations": 0.85,
    "FIFA World Cup qualification": 0.7, "UEFA Euro qualification": 0.65,
    "FIFA Confederations Cup": 0.8, "UEFA Nations League": 0.6,
}

def get_importance(t):
    for k, v in IMPORTANCE.items():
        if k.lower() in str(t).lower():
            return v
    return 0.35

def time_decay(date, ref, xi=0.002):
    return np.exp(-xi * (ref - date).days)


# ── DATA LOADING ───────────────────────────────────────────────────────────────
def load_martj42():
    df = pd.read_csv(ROOT / "data/raw/martj42/latest/results.csv", parse_dates=["date"])
    df = df[df["home_score"].notna()].copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    return df


def load_statsbomb_xg_training():
    """Load StatsBomb team xG for WC 2018 + Euro 2020 only (pre-WC-2022 training signal)."""
    sb = pd.read_parquet(ROOT / "data/derived/statsbomb_team_xg.parquet")
    train = sb[sb["season"].isin(["wc2018", "euro2020"])].copy()

    # Build per-match xG lookup: (home_team, away_team) -> (home_xg, away_xg)
    home_sb = train[train["is_home"] == True][["match_id","team","opponent","xg","match_date"]].copy()
    away_sb = train[train["is_home"] == False][["match_id","team","opponent","xg"]].copy()
    merged  = home_sb.merge(away_sb, on="match_id", suffixes=("_h","_a"))
    merged  = merged.rename(columns={
        "team_h":"home_team","opponent_h":"away_team",
        "xg_h":"home_xg","xg_a":"away_xg","match_date":"date"
    })
    merged["date"] = pd.to_datetime(merged["date"])
    return merged[["home_team","away_team","home_xg","away_xg","date"]]


def build_hybrid_training(martj42_df, sb_xg):
    """
    Merge StatsBomb xG into the martj42 training set.
    Where a match exists in StatsBomb, replace goals with xG.
    Falls back to actual goals for all other matches.
    """
    train = martj42_df[
        (martj42_df["date"] >= TRAIN_START) &
        (martj42_df["date"] < WC22_START)
    ].copy()

    # Build lookup key on team names (StatsBomb and martj42 share names)
    sb_lookup = {}
    for _, r in sb_xg.iterrows():
        sb_lookup[(r["home_team"], r["away_team"])] = (r["home_xg"], r["away_xg"])
        sb_lookup[(r["away_team"], r["home_team"])] = (r["away_xg"], r["home_xg"])

    xg_h, xg_a, used_xg = [], [], []
    for _, r in train.iterrows():
        key = (r["home_team"], r["away_team"])
        if key in sb_lookup:
            h, a = sb_lookup[key]
            xg_h.append(h); xg_a.append(a); used_xg.append(True)
        else:
            xg_h.append(float(r["home_score"]))
            xg_a.append(float(r["away_score"]))
            used_xg.append(False)

    train = train.copy()
    train["eff_home"] = xg_h
    train["eff_away"] = xg_a
    train["used_xg"]  = used_xg
    xg_count = sum(used_xg)
    print(f"  Hybrid training: {len(train):,} matches, {xg_count} with StatsBomb xG, "
          f"{len(train)-xg_count} with goals fallback")
    return train


# ── MODEL 1: ELO ──────────────────────────────────────────────────────────────
def build_elo(matches, k=30):
    ratings = {}
    def get_r(t): return ratings.get(t, 1500)
    for _, m in matches.sort_values("date").iterrows():
        h, a = m["home_team"], m["away_team"]
        rh, ra = get_r(h), get_r(a)
        eh = 1 / (1 + 10**((ra - rh) / 400))
        gh, ga = m["home_score"], m["away_score"]
        sh = 1.0 if gh > ga else 0.0 if gh < ga else 0.5
        gd   = abs(gh - ga)
        mult = np.log(max(gd,1)+1) * (1 if gd<=1 else 1.5 if gd==2 else 1.75)
        ratings[h] = rh + k * mult * (sh - eh)
        ratings[a] = ra + k * mult * ((1-sh) - (1-eh))
    return ratings

def elo_probs(rh, ra, ha=50):
    exp_h = 1 / (1 + 10**((ra - rh - ha) / 400))
    ph = exp_h ** 2.2
    pa = (1 - exp_h) ** 2.2
    pd = max(0, 1 - ph - pa)
    s  = ph + pd + pa
    return ph/s, pd/s, pa/s


# ── MODEL 2: FORM ─────────────────────────────────────────────────────────────
def compute_form(matches, team, ref_date, n=10):
    tm = matches[
        ((matches["home_team"]==team) | (matches["away_team"]==team)) &
        (matches["date"] < ref_date)
    ].sort_values("date").tail(n)
    if len(tm) == 0: return 0.5
    pts = []
    for _, r in tm.iterrows():
        if r["home_team"] == team:
            pts.append(3 if r["home_score"]>r["away_score"] else 1 if r["home_score"]==r["away_score"] else 0)
        else:
            pts.append(3 if r["away_score"]>r["home_score"] else 1 if r["away_score"]==r["home_score"] else 0)
    return np.mean(pts) / 3.0

def form_probs(fh, fa, base_draw=0.25):
    rh = 0.3 + 0.5 * fh
    ra = 0.3 + 0.5 * fa
    s  = rh + base_draw + ra
    return rh/s, base_draw/s, ra/s


# ── MODEL 3: xG-POISSON ────────────────────────────────────────────────────────
def fit_xg_poisson(hybrid_train, ref_date, xi=0.002):
    """Fit Dixon-Coles attack/defence using xG (or goals fallback) as the target."""
    teams = sorted(set(hybrid_train["home_team"]) | set(hybrid_train["away_team"]))
    tidx  = {t: i for i, t in enumerate(teams)}
    n     = len(teams)

    weights = np.array([
        time_decay(r["date"], ref_date, xi) * get_importance(r["tournament"])
        for _, r in hybrid_train.iterrows()
    ])

    hi = np.array([tidx[r["home_team"]] for _, r in hybrid_train.iterrows()])
    ai = np.array([tidx[r["away_team"]] for _, r in hybrid_train.iterrows()])
    gh = hybrid_train["eff_home"].values.astype(float)
    ga = hybrid_train["eff_away"].values.astype(float)

    def neg_ll(params):
        att  = np.exp(params[:n])
        defe = np.exp(params[n:2*n])
        ha   = params[2*n]
        lam_h = np.maximum(att[hi] * defe[ai] * np.exp(ha), 1e-6)
        lam_a = np.maximum(att[ai] * defe[hi], 1e-6)
        ll = weights * (gh*np.log(lam_h) - lam_h + ga*np.log(lam_a) - lam_a)
        return -ll.sum()

    x0  = np.zeros(2*n + 1)
    res = minimize(neg_ll, x0, method="L-BFGS-B", options={"maxiter":300,"ftol":1e-6})
    att  = np.exp(res.x[:n])
    defe = np.exp(res.x[n:2*n])
    ha   = res.x[2*n]
    params = {t: (att[i], defe[i]) for t, i in tidx.items()}
    return params, ha

def poisson_probs(lam_h, lam_a, max_g=8):
    ph_arr = np.array([poisson.pmf(g, lam_h) for g in range(max_g+1)])
    pa_arr = np.array([poisson.pmf(g, lam_a) for g in range(max_g+1)])
    grid   = np.outer(ph_arr, pa_arr)
    p_home = np.tril(grid, -1).sum()
    p_away = np.triu(grid, 1).sum()
    p_draw = np.diag(grid).sum()
    s = p_home + p_draw + p_away
    return p_home/s, p_draw/s, p_away/s


# ── PREDICT ONE MATCH ─────────────────────────────────────────────────────────
def predict_match(home, away, elo_r, xg_params, xg_ha, all_train, ref_date):
    # 1) Elo (neutral venue → ha=0)
    rh, ra = elo_r.get(home, 1500), elo_r.get(away, 1500)
    e_h, e_d, e_a = elo_probs(rh, ra, ha=0)

    # 2) Form
    fh = compute_form(all_train, home, ref_date)
    fa = compute_form(all_train, away, ref_date)
    f_h, f_d, f_a = form_probs(fh, fa)

    # 3) xG-Poisson (neutral → ha=0)
    if home in xg_params and away in xg_params:
        att_h, def_h = xg_params[home]
        att_a, def_a = xg_params[away]
        lam_h = att_h * def_a          # no home advantage
        lam_a = att_a * def_h
        p_h, p_d, p_a = poisson_probs(lam_h, lam_a)
    else:
        p_h, p_d, p_a = e_h, e_d, e_a  # fallback

    # Ensemble-v2: equal weight
    w = 1/3
    v2_h = w*e_h + w*f_h + w*p_h
    v2_d = w*e_d + w*f_d + w*p_d
    v2_a = w*e_a + w*f_a + w*p_a
    s = v2_h + v2_d + v2_a
    v2_h, v2_d, v2_a = v2_h/s, v2_d/s, v2_a/s

    return {
        "elo":   (e_h, e_d, e_a),
        "form":  (f_h, f_d, f_a),
        "xg_p":  (p_h, p_d, p_a),
        "v2":    (v2_h, v2_d, v2_a),
    }


# ── LOAD ENSEMBLE-E3 BENCHMARK ────────────────────────────────────────────────
def load_e3_benchmark():
    p = ROOT / "results/ensemble-e3/wc2022-backtest/predictions_vs_actual.csv"
    df = pd.read_csv(p)
    lookup = {}
    for _, r in df.iterrows():
        key = r["match"].replace(" vs ", "__")
        lookup[key] = {
            "p_home": float(r["p_home"]),
            "p_draw": float(r["p_draw"]),
            "p_away": float(r["p_away"]),
        }
    return lookup


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("WC 2022 BACKTEST — xG-Patched Ensemble")
    print("Train: 2012-01-01 → 2022-11-19  |  Test: 64 WC 2022 matches")
    print("=" * 80)

    # Load data
    all_results = load_martj42()
    sb_xg       = load_statsbomb_xg_training()

    # Build hybrid training set
    print("\n[1] Building hybrid training set...")
    hybrid_train = build_hybrid_training(all_results, sb_xg)
    # Goals-only training for Elo and Form models
    goals_train  = all_results[
        (all_results["date"] >= TRAIN_START) &
        (all_results["date"] < WC22_START)
    ].copy()

    # Fit models
    print("[2] Fitting Elo ratings...")
    elo_ratings = build_elo(goals_train)

    print("[3] Fitting xG-Poisson (Dixon-Coles)...")
    xg_params, xg_ha = fit_xg_poisson(hybrid_train, ref_date=WC22_START)
    print(f"    Home advantage parameter: {xg_ha:.3f} (set to 0 for WC neutral venue)")

    # WC 2022 test matches
    wc22 = all_results[
        (all_results["date"] >= WC22_START) &
        (all_results["date"] <= WC22_END) &
        (all_results["tournament"] == "FIFA World Cup")
    ].sort_values("date").reset_index(drop=True)
    print(f"[4] Test set: {len(wc22)} WC 2022 matches\n")

    # Load e3 benchmark
    e3_bench = load_e3_benchmark()

    # Run predictions
    results_table = []
    preds_elo, preds_form, preds_xgp, preds_v2, preds_e3 = [], [], [], [], []
    actuals = []

    for _, row in wc22.iterrows():
        home, away = row["home_team"], row["away_team"]
        gh, ga     = row["home_score"], row["away_score"]
        actual_idx = 0 if gh > ga else 1 if gh == ga else 2
        actual_lbl = "H" if gh > ga else "D" if gh == ga else "A"

        preds = predict_match(home, away, elo_ratings, xg_params, xg_ha,
                              goals_train, ref_date=row["date"])

        e_h, e_d, e_a   = preds["elo"]
        f_h, f_d, f_a   = preds["form"]
        p_h, p_d, p_a   = preds["xg_p"]
        v_h, v_d, v_a   = preds["v2"]

        # e3 benchmark
        key = f"{home}__{away}"
        e3  = e3_bench.get(key, {"p_home": v_h, "p_draw": v_d, "p_away": v_a})
        b_h, b_d, b_a = e3["p_home"], e3["p_draw"], e3["p_away"]

        preds_elo.append([e_h, e_d, e_a])
        preds_form.append([f_h, f_d, f_a])
        preds_xgp.append([p_h, p_d, p_a])
        preds_v2.append([v_h, v_d, v_a])
        preds_e3.append([b_h, b_d, b_a])
        actuals.append(actual_idx)

        v2_pred  = ["H","D","A"][np.argmax([v_h, v_d, v_a])]
        results_table.append({
            "date":     str(row["date"].date()),
            "match":    f"{home} vs {away}",
            "score":    f"{gh}-{ga}",
            "actual":   actual_lbl,
            # elo
            "elo_H": round(e_h,3), "elo_D": round(e_d,3), "elo_A": round(e_a,3),
            "elo_pred": ["H","D","A"][np.argmax([e_h,e_d,e_a])],
            # form
            "form_H": round(f_h,3), "form_D": round(f_d,3), "form_A": round(f_a,3),
            "form_pred": ["H","D","A"][np.argmax([f_h,f_d,f_a])],
            # xg-poisson
            "xgp_H": round(p_h,3), "xgp_D": round(p_d,3), "xgp_A": round(p_a,3),
            "xgp_pred": ["H","D","A"][np.argmax([p_h,p_d,p_a])],
            # ensemble-v2
            "v2_H": round(v_h,3), "v2_D": round(v_d,3), "v2_A": round(v_a,3),
            "v2_pred": v2_pred,
            "v2_correct": "✓" if v2_pred == actual_lbl else "✗",
            # e3 benchmark
            "e3_H": round(b_h,3), "e3_D": round(b_d,3), "e3_A": round(b_a,3),
            "e3_pred": ["H","D","A"][np.argmax([b_h,b_d,b_a])],
        })

    # ── PRINT COMPARISON TABLE ──────────────────────────────────────────────────
    print("=" * 120)
    print(f"{'MATCH':<30} {'SCORE':>5}  {'ELO':^14}  {'FORM':^14}  {'xG-POIS':^14}  {'ENSEMB-V2':^14}  {'ACT':>3}  {'OK':>2}")
    print(f"{'':30}  {'':5}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}  {'H':>4} {'D':>4} {'A':>4}")
    print("-" * 120)

    current_stage = ""
    group_matches = sorted([r for r in results_table if pd.Timestamp(r["date"]) <= pd.Timestamp("2022-12-02")], key=lambda x: x["date"])
    ko_matches    = sorted([r for r in results_table if pd.Timestamp(r["date"]) >  pd.Timestamp("2022-12-02")], key=lambda x: x["date"])

    for stage_label, stage_rows in [("── GROUP STAGE ──", group_matches), ("── KNOCKOUT ──", ko_matches)]:
        print(f"\n  {stage_label}")
        for r in stage_rows:
            print(
                f"{r['match']:<30} {r['score']:>5}  "
                f"{r['elo_H']:>4.2f} {r['elo_D']:>4.2f} {r['elo_A']:>4.2f}  "
                f"{r['form_H']:>4.2f} {r['form_D']:>4.2f} {r['form_A']:>4.2f}  "
                f"{r['xgp_H']:>4.2f} {r['xgp_D']:>4.2f} {r['xgp_A']:>4.2f}  "
                f"{r['v2_H']:>4.2f} {r['v2_D']:>4.2f} {r['v2_A']:>4.2f}  "
                f"{r['actual']:>3}  {r['v2_correct']:>2}"
            )

    # ── SUMMARY METRICS ────────────────────────────────────────────────────────
    y_oh = np.eye(3)[actuals]

    def metrics(preds_list, label):
        arr = np.array(preds_list)
        ll  = log_loss(y_oh, arr)
        acc = np.mean(np.argmax(arr, axis=1) == np.array(actuals))
        bs  = brier_score_loss(
            (np.array(actuals)==0).astype(int), arr[:,0]
        )
        return {"model": label, "log_loss": round(ll,4), "accuracy": round(acc,3),
                "brier": round(bs,4), "correct": int(acc*len(actuals))}

    summary = [
        metrics(preds_elo,  "elo-baseline"),
        metrics(preds_form, "form-last-10"),
        metrics(preds_xgp,  "poisson-xg  "),
        metrics(preds_v2,   "ensemble-v2 "),
        metrics(preds_e3,   "ensemble-e3 (bench)"),
    ]

    print("\n" + "=" * 65)
    print("SUMMARY METRICS — WC 2022 (64 matches)")
    print(f"  Pinnacle benchmark: log-loss ~0.97 | accuracy ~47% | brier ~0.21")
    print("=" * 65)
    print(f"{'Model':<26} {'Log-loss':>9} {'Accuracy':>9} {'Correct':>8} {'Brier':>8}")
    print("-" * 65)
    for s in summary:
        flag = " ◄ best" if s["log_loss"] == min(x["log_loss"] for x in summary) else ""
        print(f"{s['model']:<26} {s['log_loss']:>9.4f} {s['accuracy']:>8.1%} "
              f"{s['correct']:>5}/{len(actuals)} {s['brier']:>9.4f}{flag}")

    # Calibration: 5 bins for ensemble-v2
    print("\n── Calibration (ensemble-v2 home-win probability) ──")
    v2_arr   = np.array(preds_v2)
    home_p   = v2_arr[:,0]
    home_act = (np.array(actuals) == 0).astype(int)
    bins     = [0, 0.2, 0.35, 0.5, 0.65, 1.01]
    print(f"  {'Predicted range':<20} {'Avg pred':>9} {'Actual win%':>12} {'N':>4}")
    for i in range(len(bins)-1):
        mask = (home_p >= bins[i]) & (home_p < bins[i+1])
        if mask.sum() == 0: continue
        print(f"  {bins[i]:.2f} – {bins[i+1]:.2f}         "
              f"{home_p[mask].mean():>9.3f} {home_act[mask].mean():>11.1%} {mask.sum():>4}")

    # ── SAVE RESULTS ──────────────────────────────────────────────────────────
    for model_name, preds_list in [("poisson-xg", preds_xgp), ("ensemble-v2", preds_v2)]:
        out_dir = ROOT / f"results/{model_name}/wc2022-backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, r in enumerate(results_table):
            ph, pd_, pa = preds_list[i]
            pred_lbl = ["H","D","A"][np.argmax([ph,pd_,pa])]
            rows.append({
                "as_of_date": "2022-11-19",
                "match": r["match"], "score": r["score"],
                "p_home": round(ph,4), "p_draw": round(pd_,4), "p_away": round(pa,4),
                "pred": pred_lbl, "actual": r["actual"],
                "correct": "✓" if pred_lbl == r["actual"] else "✗",
                "model_version": model_name,
            })
        df_out = pd.DataFrame(rows)
        df_out.to_csv(out_dir / "predictions_vs_actual.csv", index=False)

    # Full comparison CSV
    comp_dir = ROOT / "results/comparisons/wc2022-backtest"
    comp_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results_table).to_csv(comp_dir / "all_models_comparison.csv", index=False)
    pd.DataFrame(summary).to_csv(comp_dir / "summary_metrics.csv", index=False)

    print(f"\nSaved → results/comparisons/wc2022-backtest/all_models_comparison.csv")
    print(f"Saved → results/comparisons/wc2022-backtest/summary_metrics.csv")


if __name__ == "__main__":
    main()
