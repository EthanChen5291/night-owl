"""Step 3: Model A, A-variant, Model B (x5 copies), Silence Score.

Model A        what the city sees: rat complaints per cell-month (Poisson), all features
A-variant      same target, B's features only, so the Silence Score compares labels,
               not model capacity
Model B        what's actually there: P(rat signs | sweep inspection), physical only.
               Trained on sweep cell-months, label = share of swept lots with rats.
Uncertainty    5 copies of A-variant and B, each on a bootstrap resample of community
               districts. Spread across copies = epistemic uncertainty.

Outputs (data/processed/): scores.parquet (one row per cell for the scoring month),
metrics.json (spatial CV).
Backtest hook: train_until(month_T) -> per-cell scores for month T+1.

Run: python3 model/03_models.py [--month YYYY-MM]
"""
import argparse
import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import PROCESSED

N_COPIES = 5
A_TRAIN_FROM = "2018-01"  # enough history, keeps Model A fast
MIN_LOTS = 20             # cells with fewer tax lots aren't ranked for silence
PRIOR_LOTS = 20           # Model B's prediction counts as this many inspected lots

PHYSICAL = [
    "n_lots", "year_built_median", "share_pre1940", "share_vacant", "share_residential",
    "share_mixed_use", "share_commercial", "share_industrial", "floors_mean", "units_res",
    "bldg_area", "retail_area", "com_area", "n_restaurants", "n_litter_baskets",
    "n_catch_basins", "n_trees", "n_subway_entrances", "share_park",
    "dob_permits_3m", "rest_04k_12m", "rest_08a_12m", "temp_c", "month_of_year",
    "refuse_tons_cd",
]
CONTROLS = ["median_income", "pop_density"]           # controls only, per the spec
B_FEATS = PHYSICAL + CONTROLS                          # never complaint/inspection counts, never HPD
A_FEATS = B_FEATS + ["hpd_rodent_12m", "complaints_1m", "complaints_12m"]
# limited_english_share is deliberately in neither model: it's the bias we measure.

PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=50,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def load() -> pd.DataFrame:
    panel = pd.read_parquet(PROCESSED / "panel.parquet")
    static = pd.read_parquet(PROCESSED / "features_static.parquet")
    df = panel.merge(static, on="h3", how="left")
    df["boro_cd"] = df.boro_cd.fillna(0).astype(int)
    return df


def fit_a(rows: pd.DataFrame, feats: list, seed: int = 0, weight=None):
    m = lgb.LGBMRegressor(objective="poisson", random_state=seed, **PARAMS)
    return m.fit(rows[feats], rows.n_complaints, sample_weight=weight)


def fit_b(rows: pd.DataFrame, seed: int = 0, weight=None):
    """Label = share of swept lots with rat activity; weight = number of swept lots."""
    w = rows.n_sweep.to_numpy(float) * (1 if weight is None else weight)
    m = lgb.LGBMRegressor(objective="cross_entropy", random_state=seed, **PARAMS)
    return m.fit(rows[B_FEATS], rows.n_sweep_rat / rows.n_sweep, sample_weight=w)


def cd_bootstrap(rows: pd.DataFrame, rng) -> np.ndarray:
    """Resample community districts with replacement; return a per-row weight."""
    cds = rows.boro_cd.unique()
    counts = pd.Series(rng.choice(cds, size=len(cds), replace=True)).value_counts()
    return rows.boro_cd.map(counts).fillna(0).to_numpy(float)


def pct(x: np.ndarray) -> np.ndarray:
    return rankdata(x) / len(x)


def train_until(df: pd.DataFrame, month_T: str, score_month: str | None = None) -> pd.DataFrame:
    """Train on months <= month_T; score every cell at score_month (default T+1)."""
    score_month = score_month or str(pd.Period(month_T, "M") + 1)
    hist = df[df.month <= month_T]
    a_rows = hist[hist.month >= A_TRAIN_FROM]
    b_rows = hist[hist.n_sweep > 0]
    target = df[df.month == score_month].reset_index(drop=True)

    risk_a = fit_a(a_rows, A_FEATS).predict(target[A_FEATS])
    rng = np.random.default_rng(0)
    b_copies, av_copies = [], []
    for k in range(N_COPIES):
        wa, wb = cd_bootstrap(a_rows, rng), cd_bootstrap(b_rows, rng)
        av_copies.append(fit_a(a_rows, B_FEATS, seed=k, weight=wa).predict(target[B_FEATS]))
        b_copies.append(fit_b(b_rows, seed=k, weight=wb).predict(target[B_FEATS]))
    B, AV = np.array(b_copies), np.array(av_copies)

    # Compare reporting per PERSON (complaints come from people) with B's chance of
    # rats. Raw counts or per-lot rates make low-density areas look "silent" just
    # because fewer people live there. Rank only among cells with real building
    # stock and residents (skips parks, rail yards, water edges).
    pop = target.pop_density.to_numpy(float)
    ok = (target.n_lots.to_numpy(float) >= MIN_LOTS) & target.real_cd.to_numpy() & (pop > 0)
    silence = np.full((N_COPIES, len(target)), np.nan)
    for k in range(N_COPIES):
        silence[k, ok] = pct(B[k, ok]) - pct(AV[k, ok] / pop[ok])

    # Epistemic uncertainty from data sparsity (tree copies agree on unseen areas, so
    # their spread alone is false confidence). Beta-Binomial: B's prediction is the
    # prior, worth PRIOR_LOTS pseudo-inspections; each swept lot in the last 24 months
    # narrows it. Never-swept cells keep a wide posterior. Sensor detections later
    # update the same posterior.
    recent = hist[hist.month > str(pd.Period(month_T, "M") - 24)]
    obs = recent.groupby("h3")[["n_sweep", "n_sweep_rat"]].sum()
    n = target.h3.map(obs.n_sweep).fillna(0).to_numpy()
    r = target.h3.map(obs.n_sweep_rat).fillna(0).to_numpy()
    prior = B.mean(0)
    post_mean = (PRIOR_LOTS * prior + r) / (PRIOR_LOTS + n)
    post_sd = np.sqrt(post_mean * (1 - post_mean) / (PRIOR_LOTS + n + 1))

    out = target[["h3", "month", "lat", "lng", "boro_cd", "real_cd", "n_lots", "n_complaints",
                  "complaints_12m", "median_income", "pop_density", "limited_english_share"]].copy()
    out["risk_a"] = risk_a
    out["risk_a_var"] = AV.mean(0)
    out["complaints_per_capita"] = AV.mean(0) / np.maximum(pop, 1)
    out["risk_b"] = prior
    out["risk_b_model_sd"] = B.std(0)
    out["sweeps_24m"] = n
    out["sweep_rats_24m"] = r
    out["risk_post"] = post_mean
    out["uncertainty"] = np.sqrt(post_sd ** 2 + B.std(0) ** 2)
    # Share of the estimate that is still the model's guess (1 = never swept).
    # Absolute sd grows with the rate itself, so this is the cleaner "how little do
    # we know here" signal for siting. Empirically it's highest where complaints
    # are lowest (97% of the quietest quartile unswept vs 55% of the loudest).
    out["data_gap"] = PRIOR_LOTS / (PRIOR_LOTS + n)
    out["eligible"] = ok
    out["silence"] = silence.mean(0)
    out["silence_lo"] = silence.min(0)
    out["silence_hi"] = silence.max(0)
    # Silent = high B, low A: B ranks it in the top 40%, every copy agrees B ranks
    # it above A (interval excludes zero), and meaningfully so (top-quarter gap).
    b_pct = np.full(len(target), np.nan)
    b_pct[ok] = pct(prior[ok])
    out["is_silent"] = ok & (b_pct >= 0.6) & (out.silence_lo > 0) & (out.silence > 0.25)
    return out


def spatial_cv(df: pd.DataFrame, until: str) -> dict:
    """Hold out whole community districts. Model B vs a logistic baseline; A vs last-12m."""
    real = df[df.real_cd & (df.month <= until)]
    b_rows = real[real.n_sweep > 0].reset_index(drop=True)
    a_rows = real[real.month >= A_TRAIN_FROM].reset_index(drop=True)
    gkf = GroupKFold(n_splits=5)

    def weighted_auc(rows, p):
        pos, neg = rows.n_sweep_rat.to_numpy(), (rows.n_sweep - rows.n_sweep_rat).to_numpy()
        y = np.r_[np.ones(len(p)), np.zeros(len(p))]
        return roc_auc_score(y, np.r_[p, p], sample_weight=np.r_[pos, neg])

    auc_b, auc_lr, calib = [], [], []
    for tr, te in gkf.split(b_rows, groups=b_rows.boro_cd):
        trn, tst = b_rows.iloc[tr], b_rows.iloc[te]
        p = fit_b(trn).predict(tst[B_FEATS])
        lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                           LogisticRegression(max_iter=1000))
        # expand to one row per (cell-month, outcome) with weights for the baseline
        X = pd.concat([trn[B_FEATS], trn[B_FEATS]])
        y = np.r_[np.ones(len(trn)), np.zeros(len(trn))]
        w = np.r_[trn.n_sweep_rat, trn.n_sweep - trn.n_sweep_rat]
        lr.fit(X, y, logisticregression__sample_weight=w)
        auc_b.append(weighted_auc(tst, p))
        auc_lr.append(weighted_auc(tst, lr.predict_proba(tst[B_FEATS])[:, 1]))
        calib.append(pd.DataFrame({"p": p, "rate": tst.n_sweep_rat / tst.n_sweep, "w": tst.n_sweep}))

    cal = pd.concat(calib)
    cal["bin"] = pd.qcut(cal.p, 10, labels=False, duplicates="drop")
    cal_tbl = cal.groupby("bin").apply(
        lambda g: pd.Series({"predicted": np.average(g.p, weights=g.w),
                             "observed": np.average(g.rate, weights=g.w)}), include_groups=False)

    rho_a, rho_base = [], []
    for tr, te in gkf.split(a_rows, groups=a_rows.boro_cd):
        tst = a_rows.iloc[te]
        p = fit_a(a_rows.iloc[tr], A_FEATS).predict(tst[A_FEATS])
        rho_a.append(spearmanr(p, tst.n_complaints).statistic)
        rho_base.append(spearmanr(tst.complaints_12m, tst.n_complaints).statistic)

    return {
        "model_b_auc_heldout_districts": round(float(np.mean(auc_b)), 3),
        "logistic_baseline_auc": round(float(np.mean(auc_lr)), 3),
        "model_b_calibration": cal_tbl.round(3).to_dict(orient="index"),
        "model_a_spearman_heldout_districts": round(float(np.mean(rho_a)), 3),
        "last_12m_complaints_spearman": round(float(np.mean(rho_base)), 3),
        "n_b_rows": int(len(b_rows)), "n_a_rows": int(len(a_rows)),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="scoring month YYYY-MM (default: latest in panel)")
    ap.add_argument("--skip-cv", action="store_true")
    args = ap.parse_args()

    df = load()
    score_month = args.month or df.month.max()
    until = str(pd.Period(score_month, "M") - 1)

    if not args.skip_cv:
        metrics = spatial_cv(df, until)
        (PROCESSED / "metrics.json").write_text(json.dumps(metrics, indent=2))
        print(json.dumps({k: v for k, v in metrics.items() if k != "model_b_calibration"}, indent=2))
        print("calibration (predicted vs observed, by decile):")
        for b, r in metrics["model_b_calibration"].items():
            print(f"  {b}: {r['predicted']:.3f} vs {r['observed']:.3f}")

    scores = train_until(df, until, score_month)
    scores.to_parquet(PROCESSED / "scores.parquet", index=False)
    s = scores[scores.eligible]
    print(f"\nscored {len(scores):,} cells for {score_month} ({len(s):,} eligible); "
          f"silent cells: {s.is_silent.sum():,}")
    print(f"median complaints_12m   all: {s.complaints_12m.median():.0f}   "
          f"silent: {s[s.is_silent].complaints_12m.median():.0f}")
    print(f"median income           all: {s.median_income.median():,.0f}   "
          f"silent: {s[s.is_silent].median_income.median():,.0f}")
