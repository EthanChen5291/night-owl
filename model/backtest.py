#!/usr/bin/env -S uv run --with duckdb --with lightgbm --with h3 --with shap --with scikit-learn --with pandas --with pyarrow --with numpy --with matplotlib python
"""backtest.py: rolling-origin backtest of the Silence Score against the 311 baseline.

For every origin month t from 2016-01 to 2026-07: models trained on data strictly before t
(expanding window, refit every REFIT_EVERY months to stay inside the time budget; between refits the
last models are reused, but the features at month t are always the true lagged features), cells
ranked by silence = pct_b - pct_a and by pct_a alone, precision@50 against the cells that had at least
one l60 = 0 Initial inspection with active rat signs in month t.
Writes model/out/backtest.json (frozen shape), backtest.png and backtest_detail.json (extra series).
"""
from __future__ import annotations

import json
import time

import lightgbm as lgb
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import A_FEATURES, B_FEATURES, COVID, MONTHS, OUT, Timer, check_leakage, dump_json, lgb_params, load_features, percentile_rank
from train import inspection_rows

K = 50
import os
REFIT_EVERY = int(os.environ.get("BARNOWL_REFIT", "6"))
ROUNDS_A, ROUNDS_B, ROUNDS_P = 200, 200, 120
ORIGINS = [m for m in MONTHS if "2016-01" <= m <= "2026-07"]
A_MIN = "2015-04"
DETAIL_KEYS = ("precision_silent", "precision_311", "precision_b_alone", "precision_311_lag3", "precision_silent_highb",
               "precision_random", "hit_rate_silent", "hit_rate_silent_highb", "hit_rate_311", "hit_rate_b", "hit_rate_all",
               "n_insp_silent", "n_insp_silent_highb", "n_insp_311", "n_insp_b")  # give Model A at least 3 months of lag history


def main() -> None:
    t0 = time.time()
    check_leakage(B_FEATURES)
    feats = load_features().sort_values(["month", "h3"]).reset_index(drop=True)
    feats["cd_code"] = pd.to_numeric(feats.cd, errors="coerce").fillna(0).astype(int)
    P_FEATURES = B_FEATURES + ["cd_code"]
    with Timer("inspection rows"):
        rows = inspection_rows(feats[["h3", "month", "cd", "rmz"] + B_FEATURES + ["n_active_l60_0"]])
        rows = rows.sort_values("month").reset_index(drop=True)
    month_arr = feats.month.values
    row_month = rows.month.values
    XA_all = feats[A_FEATURES].values.astype(np.float32)
    XP_all = feats[P_FEATURES].values.astype(np.float32)
    XB_rows = rows[B_FEATURES].values.astype(np.float32)
    yA_all = feats.complaints.values.astype(float)
    offA_all = np.log1p(feats.pluto_res_units.values.astype(float))
    yP_all = (feats.n_initial_l60_0.values > 0).astype(int)
    yB = rows.active.values

    series, detail = [], []
    mA = mP = mB = None
    for i, t in enumerate(ORIGINS):
        if i % REFIT_EVERY == 0:
            with Timer(f"refit @ {t}"):
                trA = (month_arr < t) & (month_arr >= A_MIN)
                mA = lgb.train(lgb_params("poisson"), lgb.Dataset(XA_all[trA], yA_all[trA], init_score=offA_all[trA]), ROUNDS_A)
                trP = month_arr < t
                mP = lgb.train(lgb_params("binary"), lgb.Dataset(XP_all[trP], yP_all[trP]), ROUNDS_P)
                p_ins = np.clip(mP.predict(XP_all[trP]), 0.02, 1.0)
                w_panel = pd.Series(yP_all[trP].mean() / p_ins, index=pd.MultiIndex.from_arrays([feats.h3.values[trP], month_arr[trP]]))
                trB = row_month < t
                w = w_panel.reindex(pd.MultiIndex.from_arrays([rows.h3.values[trB], row_month[trB]])).values
                w = np.clip(w, *np.percentile(w, [1, 99]))
                mB = lgb.train(lgb_params("binary"), lgb.Dataset(XB_rows[trB], yB[trB], weight=w), ROUNDS_B)
        sel = month_arr == t
        score_a = np.exp(mA.predict(XA_all[sel], raw_score=True) + offA_all[sel])
        score_b = mB.predict(XA_all[sel][:, :len(B_FEATURES)])  # B_FEATURES are the first columns of A_FEATURES
        pct_a, pct_b = percentile_rank(score_a), percentile_rank(score_b)
        silence = pct_b - pct_a
        pos = feats.n_active_l60_0.values[sel] > 0
        n_insp = feats.n_initial_l60_0.values[sel] > 0

        def prec(score):
            top = np.argsort(-score, kind="stable")[:K]
            return float(pos[top].mean())

        def hit_rate(score):
            """P(active | inspected) among the top-k: share of inspected top-k cells with an active find."""
            top = np.argsort(-score, kind="stable")[:K]
            n = n_insp[top].sum()
            return (float(pos[top].sum() / n) if n else float("nan")), int(n)

        high_b = np.where(pct_b >= 80, silence + 1e-3 * pct_b, -1e9)  # silent among high-B cells

        # complaints baseline as in the plan (trailing 3-month 311 count) for the detail file
        base311 = feats.complaints_lag3.values[sel] + 1e-3 * pct_a
        rec = {"month": t, "precision_silent": round(prec(silence + 1e-3 * pct_b), 4), "precision_311": round(prec(pct_a), 4),
               "n_positives": int(pos.sum())}
        series.append(rec)
        hr_s, n_s = hit_rate(silence + 1e-3 * pct_b)
        hr_h, n_h = hit_rate(high_b)
        hr_a, n_a = hit_rate(pct_a)
        hr_b, n_b = hit_rate(pct_b)
        detail.append({**rec, "precision_b_alone": round(prec(pct_b), 4), "precision_311_lag3": round(prec(base311), 4),
                       "precision_silent_highb": round(prec(high_b), 4),
                       "precision_random": round(float(pos.mean()), 4), "n_cells_inspected": int(n_insp.sum()),
                       "hit_rate_silent": hr_s, "n_insp_silent": n_s, "hit_rate_silent_highb": hr_h, "n_insp_silent_highb": n_h,
                       "hit_rate_311": hr_a, "n_insp_311": n_a, "hit_rate_b": hr_b, "n_insp_b": n_b,
                       "hit_rate_all": round(float(pos.sum() / max(n_insp.sum(), 1)), 4)})
        if i % 12 == 0:
            print(t, rec, flush=True)

    ms = np.mean([s["precision_silent"] for s in series])
    m3 = np.mean([s["precision_311"] for s in series])
    out = {"window": [ORIGINS[0], ORIGINS[-1]], "k": K, "series": series,
           "summary": {"mean_precision_silent": round(float(ms), 4), "mean_precision_311": round(float(m3), 4),
                       "lift": round(float(ms / m3), 4) if m3 > 0 else None},
           "synthetic": False}
    dump_json(out, OUT / "backtest.json")
    def clean(v):
        return None if isinstance(v, float) and np.isnan(v) else v

    dump_json({"refit_every_months": REFIT_EVERY, "rounds": [ROUNDS_A, ROUNDS_B, ROUNDS_P],
               "series": [{k: clean(v) for k, v in d.items()} for d in detail],
               "summary": {k: round(float(np.nanmean([d[k] for d in detail])), 4) for k in DETAIL_KEYS}},
              OUT / "backtest_detail.json")
    # the extra series are gitignored with backtest_detail.json; keep their means in the committed metrics.json
    mpath = OUT / "metrics.json"
    if mpath.exists():
        m = json.loads(mpath.read_text())
        m["backtest"] = {"window": out["window"], "k": K, "refit_every_months": REFIT_EVERY, "rounds": [ROUNDS_A, ROUNDS_B, ROUNDS_P],
                         "summary": out["summary"],
                         "detail_means": {k: round(float(np.nanmean([d[k] for d in detail])), 4) for k in DETAIL_KEYS},
                         "runtime_s": round(time.time() - t0, 1)}
        dump_json(m, mpath)
    print("summary", out["summary"])
    for k in DETAIL_KEYS:
        print(f"  {k:26s} {np.nanmean([d[k] for d in detail]):.4f}")

    # ---------------------------------------------------------------- the one chart
    x = pd.to_datetime([s["month"] for s in series])
    ys = np.array([s["precision_silent"] for s in series])
    y3 = np.array([s["precision_311"] for s in series])
    blue, orange, ink, muted = "#2a78d6", "#eb6834", "#1a1a19", "#6b6a63"
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.axvspan(pd.Timestamp(COVID[0]), pd.Timestamp(COVID[1]) + pd.offsets.MonthEnd(0), color="#e9e8e2", lw=0, zorder=0)
    ax.text(pd.Timestamp("2020-09-15"), 0.98, "COVID", ha="center", va="top", fontsize=9, color=muted)
    ax.plot(x, y3, color=orange, lw=2, label=f"311 baseline (top-{K} by predicted complaints)", zorder=2)
    ax.plot(x, ys, color=blue, lw=2, label=f"Silence Score (top-{K} by pct_b - pct_a)", zorder=3)
    ax.text(x[-1] + pd.Timedelta(days=20), ys[-1], f"silent {ms:.2f} mean", color=blue, fontsize=9, va="center")
    ax.text(x[-1] + pd.Timedelta(days=20), y3[-1], f"311 {m3:.2f} mean", color=orange, fontsize=9, va="center")
    ax.set_ylim(0, 1.0)
    ins_s = np.nanmean([d["n_insp_silent"] for d in detail])
    ins_3 = np.nanmean([d["n_insp_311"] for d in detail])
    ax.text(0.0, -0.22, f"A positive is a cell with an active l60=0 Initial inspection in the month, so a cell only scores if the city "
            f"looked there: on average {ins_s:.1f} of the {K} silent cells get inspected in a month vs {ins_3:.1f} of the 311 cells.",
            transform=ax.transAxes, fontsize=7.5, color=muted, va="top")
    ax.set_xlim(x[0] - pd.Timedelta(days=15), x[-1] + pd.Timedelta(days=420))
    ax.set_ylabel(f"precision@{K}: share of ranked cells with an active\nl60=0 inspection next month", fontsize=9, color=ink)
    ax.set_title(f"Rolling-origin backtest {ORIGINS[0]} to {ORIGINS[-1]}, all NYC, {feats.h3.nunique()} cells, "
                 f"refit every {REFIT_EVERY} months; lift {out['summary']['lift']:.2f}x", fontsize=10, color=ink, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#d0cfc7")
    ax.tick_params(colors=muted, labelsize=8)
    ax.grid(axis="y", color="#ecebe5", lw=0.8)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT / "backtest.png")
    print(f"[backtest total] {time.time() - t0:.1f}s -> backtest.json, backtest.png")


if __name__ == "__main__":
    main()
