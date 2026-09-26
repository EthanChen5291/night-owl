#!/usr/bin/env -S uv run --with duckdb --with lightgbm --with h3 --with shap --with scikit-learn --with pandas --with pyarrow --with numpy --with matplotlib python
"""train.py: Model A (what the city sees), propensity + Model B (what's there), spatial CV, ablations,
RMZ holdout, calibration, bootstrap ensemble -> model/out/*.txt and model/out/metrics.json.

Model A: LightGBM Poisson on rodent complaints per cell x month, offset log(1 + residential units),
         every feature including lagged complaints and inspection history.
Model B: LightGBM binary on `active` for the l60 = 0 Initial inspections (no complaint on the lot in the
         prior 60 days), physical/environmental features only, weighted by 1 / P(cell-month gets an
         l60 = 0 inspection) from a propensity model, weights clipped at the 1st/99th percentile.
CV: GroupKFold(5) by community district. Holdout: RMZ cells, last 12 months.
"""
from __future__ import annotations

import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, mean_poisson_deviance, roc_auc_score
from sklearn.model_selection import GroupKFold

from common import (A_FEATURES, A_ONLY_FEATURES, ACS_ABLATION, B_FEATURES, MONTHS, OUT, RMZ_ABLATION, Timer,
                    check_leakage, dump_json, lgb_params, load_features)

N_ROUNDS_A, N_ROUNDS_B, N_ROUNDS_P, N_BOOT = 400, 400, 200, 5
A_START = "2016-01"  # first month with a full 12-month lag history


def inspection_rows(feats: pd.DataFrame) -> pd.DataFrame:
    """One row per l60 = 0 Initial inspection, joined to its cell-month feature row."""
    import duckdb
    import h3

    from common import H3_RES, PARQUET
    ins = duckdb.connect().execute(f"""
        select inspection_date, latitude, longitude, active from read_parquet('{PARQUET / 'initial_inspections_linked.parquet'}')
        where l60 = 0 and latitude is not null""").df()
    ins["h3"] = [h3.latlng_to_cell(a, b, H3_RES) if (40.4 < a < 41 and -74.4 < b < -73.6) else None
                 for a, b in zip(ins.latitude.values, ins.longitude.values)]
    ins["month"] = ins.inspection_date.dt.strftime("%Y-%m")
    ins = ins[["h3", "month", "active"]].dropna()
    rows = ins.merge(feats.drop(columns=["n_active_l60_0"]), on=["h3", "month"], how="inner")
    rows["active"] = rows.active.astype(int)
    return rows


def group_folds(groups: pd.Series, n=5):
    g = groups.fillna("none").astype(str).values
    return list(GroupKFold(n_splits=n).split(np.zeros(len(g)), groups=g))


def cv_poisson(X, y, offset, folds):
    oof = np.zeros(len(y))
    for tr, te in folds:
        d = lgb.Dataset(X[tr], y[tr], init_score=offset[tr])
        m = lgb.train(lgb_params("poisson"), d, N_ROUNDS_A)
        oof[te] = np.exp(m.predict(X[te], raw_score=True) + offset[te])
    return oof


def cv_binary(X, y, w, folds, seed=0):
    oof = np.zeros(len(y))
    for tr, te in folds:
        d = lgb.Dataset(X[tr], y[tr], weight=None if w is None else w[tr])
        m = lgb.train(lgb_params("binary", seed=seed), d, N_ROUNDS_B)
        oof[te] = m.predict(X[te])
    return oof


def binary_metrics(y, p):
    return {"auc": round(float(roc_auc_score(y, p)), 4), "brier": round(float(brier_score_loss(y, p)), 4)}


def precision_at_k_cells(rows: pd.DataFrame, p: np.ndarray, k=50) -> float:
    """Rank cells by mean predicted P(active) over the slice; share of the top-k cells with any active find."""
    d = pd.DataFrame({"h3": rows.h3.values, "p": p, "y": rows.active.values})
    g = d.groupby("h3").agg(p=("p", "mean"), y=("y", "max")).sort_values("p", ascending=False)
    return round(float(g.y.head(k).mean()), 4)


def main() -> None:
    t0 = time.time()
    check_leakage(B_FEATURES)
    feats = load_features()
    feats["cd_code"] = pd.to_numeric(feats.cd, errors="coerce").fillna(0).astype(int)
    metrics: dict = {"n_cells": int(feats.h3.nunique()), "n_cell_months": int(len(feats)),
                     "months": [MONTHS[0], MONTHS[-1]], "scope": sorted(feats.borough.unique().tolist())}

    # ------------------------------------------------------------------ Model A
    with Timer("model A cv"):
        a = feats[feats.month >= A_START].reset_index(drop=True)
        XA = a[A_FEATURES].values.astype(np.float32)
        yA = a.complaints.values.astype(float)
        offA = np.log1p(a.pluto_res_units.values.astype(float))
        foldsA = group_folds(a.cd)
        oofA = cv_poisson(XA, yA, offA, foldsA)
        null_dev = mean_poisson_deviance(yA, np.full(len(yA), yA.mean()))
        dev = mean_poisson_deviance(yA, np.maximum(oofA, 1e-6))
        a["oof"] = oofA
        per_month = a.groupby("month").apply(lambda d: spearmanr(d.oof, d.complaints).correlation if d.complaints.sum() > 0 else np.nan)
        metrics["model_a"] = {
            "objective": "poisson", "offset": "log1p(pluto_res_units)", "n_rows": int(len(a)), "n_features": len(A_FEATURES),
            "cv": "GroupKFold(5) by community district",
            "poisson_deviance": round(float(dev), 4), "null_deviance": round(float(null_dev), 4),
            "deviance_explained": round(float(1 - dev / null_dev), 4),
            "spearman_all_rows": round(float(spearmanr(oofA, yA).correlation), 4),
            "spearman_per_month_mean": round(float(per_month.mean()), 4),
        }
        print(metrics["model_a"])

    # ------------------------------------------------------------------ propensity -> IPW weights
    with Timer("propensity"):
        P_FEATURES = B_FEATURES + ["cd_code"]
        XP = feats[P_FEATURES].values.astype(np.float32)
        yP = (feats.n_initial_l60_0.values > 0).astype(int)
        foldsP = group_folds(feats.cd)
        oofP = np.zeros(len(yP))
        for tr, te in foldsP:
            m = lgb.train(lgb_params("binary"), lgb.Dataset(XP[tr], yP[tr]), N_ROUNDS_P)
            oofP[te] = m.predict(XP[te])
        marginal = yP.mean()
        feats["p_insp"] = np.clip(oofP, 0.02, 1.0)
        feats["ipw_raw"] = marginal / feats.p_insp
        metrics["propensity"] = {"auc": round(float(roc_auc_score(yP, oofP)), 4), "marginal_rate": round(float(marginal), 4),
                                 "features": "B features + community district code"}
        print(metrics["propensity"])

    # ------------------------------------------------------------------ Model B rows
    with Timer("model B rows"):
        rows = inspection_rows(feats[["h3", "month", "cd", "rmz", "ipw_raw"] + A_FEATURES + ["n_active_l60_0"]])
        lo, hi = np.percentile(rows.ipw_raw, [1, 99])
        rows["w"] = np.clip(rows.ipw_raw, lo, hi)
        w = rows.w.values
        ess = float(w.sum() ** 2 / (w ** 2).sum())
        y = rows.active.values
        foldsB = group_folds(rows.cd)
        last12 = MONTHS[-12]
        hold = (rows.rmz.notna() & (rows.month >= last12)).values
        metrics["model_b_data"] = {"n_rows": int(len(rows)), "active_rate": round(float(y.mean()), 4),
                                   "weight_clip": [round(float(lo), 3), round(float(hi), 3)],
                                   "effective_sample_size": round(ess), "n_holdout_rmz_last12": int(hold.sum()),
                                   "holdout_active_rate": round(float(y[hold].mean()), 4)}
        print(metrics["model_b_data"])

    variants = {
        "B_full": (B_FEATURES, True),
        "B_no_rmz": ([f for f in B_FEATURES if f not in RMZ_ABLATION], True),
        "B_no_acs": ([f for f in B_FEATURES if f not in ACS_ABLATION], True),
        "B_unweighted": (B_FEATURES, False),
        "B_plus_A_features_leakage": (A_FEATURES, True),
    }
    metrics["model_b"] = {}
    oof_full = None
    for name, (cols, weighted) in variants.items():
        with Timer(name):
            X = rows[cols].values.astype(np.float32)
            ww = w if weighted else None
            oof = cv_binary(X, y, ww, foldsB)
            res = {"n_features": len(cols), "weighted": weighted, "cv": binary_metrics(y, oof)}
            # RMZ holdout: fit on everything outside the slice, evaluate on the slice
            m = lgb.train(lgb_params("binary"), lgb.Dataset(X[~hold], y[~hold], weight=None if ww is None else ww[~hold]), N_ROUNDS_B)
            ph = m.predict(X[hold])
            res["holdout_rmz_last12"] = binary_metrics(y[hold], ph)
            res["holdout_rmz_last12"]["precision_at_50_cells"] = precision_at_k_cells(rows[hold], ph)
            metrics["model_b"][name] = res
            print(name, res)
            if name == "B_full":
                oof_full = oof

    # ------------------------------------------------------------------ calibration + final fits
    with Timer("calibration + final fits"):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(oof_full, y, sample_weight=w)
        cal = {"x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_]}
        dump_json(cal, OUT / "model_b_calibration.json")
        metrics["model_b"]["B_full"]["cv_calibrated"] = binary_metrics(y, iso.predict(oof_full))

        mA = lgb.train(lgb_params("poisson"), lgb.Dataset(XA, yA, init_score=offA), N_ROUNDS_A)
        mA.save_model(str(OUT / "model_a.txt"))
        mP = lgb.train(lgb_params("binary"), lgb.Dataset(XP, yP), N_ROUNDS_P)
        mP.save_model(str(OUT / "propensity.txt"))
        XB = rows[B_FEATURES].values.astype(np.float32)
        mB = lgb.train(lgb_params("binary"), lgb.Dataset(XB, y, weight=w), N_ROUNDS_B)
        mB.save_model(str(OUT / "model_b.txt"))
        rng = np.random.default_rng(0)
        for i in range(N_BOOT):
            idx = rng.integers(0, len(y), len(y))
            mb = lgb.train(lgb_params("binary", seed=100 + i), lgb.Dataset(XB[idx], y[idx], weight=w[idx]), N_ROUNDS_B)
            mb.save_model(str(OUT / f"model_b_boot_{i}.txt"))
        imp = sorted(zip(B_FEATURES, mB.feature_importance("gain")), key=lambda t: -t[1])[:10]
        metrics["model_b"]["B_full"]["top_gain_features"] = [f for f, _ in imp]

    metrics["features"] = {"A": A_FEATURES, "B": B_FEATURES, "A_only": A_ONLY_FEATURES, "propensity": P_FEATURES}
    metrics["params"] = {"rounds_A": N_ROUNDS_A, "rounds_B": N_ROUNDS_B, "rounds_propensity": N_ROUNDS_P,
                         "bootstrap_models": N_BOOT, "lgb": lgb_params("binary")}
    metrics["runtime_s"] = round(time.time() - t0, 1)
    dump_json(metrics, OUT / "metrics.json")
    print(f"[train total] {metrics['runtime_s']}s -> {OUT / 'metrics.json'}")


if __name__ == "__main__":
    main()
