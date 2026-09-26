"""Step 5: rolling backtest, scored on proactive sweeps only.

For every month M (2016-01 ..): Model B is trained only on months before M (refit every
REFIT_EVERY months; features at M are always M's own lagged features, so no leakage).
Among the cells DOHMH actually swept in M, each method picks its top K:

  model      Model B risk
  complaints most rat complaints in the prior 12 months (how the city works today)
  positives  most rats found by any inspection in the prior 12 months
  random     all swept cells (the base rate)

Score = share of swept lots in the picked cells where inspectors found rat activity.
Why only swept cells: silent blocks are rarely inspected, so counting "inspected and found
rats" anywhere grades the model on where DOHMH goes, not where rats are.

Output: model/out/backtest.json in the web contract
  {window, k, series[{month, precision_silent, precision_311, n_positives, ...}], summary, synthetic}
precision_silent = our model, precision_311 = complaints baseline (names fixed by web/src/types.ts).

Run: python3 model/05_backtest.py [--k 50] [--start 2016-01]
"""
import argparse
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

models = importlib.import_module("03_models")
OUT = Path(__file__).resolve().parent / "out"
REFIT_EVERY = 6


def lagged(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """Sum of `col` over the `window` months strictly before each row's month."""
    return (df.groupby("h3", sort=False)[col]
            .transform(lambda s: s.shift(1).rolling(window, min_periods=1).sum()).fillna(0))


def pick_rate(month_rows: pd.DataFrame, score: pd.Series, k: int, rng) -> float:
    """Rat rate over swept lots in the top-k cells by `score` (random tie-break)."""
    tie = rng.random(len(month_rows))
    top = month_rows.assign(_s=score.to_numpy(), _t=tie).sort_values(["_s", "_t"], ascending=False).head(k)
    return top.n_sweep_rat.sum() / top.n_sweep.sum()


def main(k: int, start: str, level: str = "cell", out: str = "backtest.json") -> None:
    if level == "lot":
        lots = importlib.import_module("lots")
    df = models.load().sort_values(["h3", "month"]).reset_index(drop=True)
    df["rats_12m"] = lagged(df, "n_rat", 12)          # any Initial inspection that found rats
    # The latest month is still in progress (data ends mid-month), so it's left out.
    months = sorted(m for m in df.month.unique() if start <= m < df.month.max())
    rng = np.random.default_rng(0)

    series, model = [], None
    for i, m in enumerate(months):
        if model is None or i % REFIT_EVERY == 0:
            prev = str(pd.Period(m, "M") - 1)
            if level == "lot":
                model = lots.fit(lots.training_rows(df, prev))
            else:
                model = models.fit_b(df[(df.month < m) & (df.n_sweep > 0)])
        rows = df[(df.month == m) & (df.n_sweep > 0) & df.real_cd].reset_index(drop=True)
        if len(rows) < k:
            continue
        if level == "lot":  # mean risk over ALL lots in each cell (not only the swept ones)
            risk = rows.h3.map(lots.cell_scores(model, rows)).fillna(0).reset_index(drop=True)
        else:
            risk = pd.Series(model.predict(rows[models.B_FEATS]))
        # Quiet blocks only (bottom half of prior-12-month complaints among swept cells):
        # the silent-block claim itself. Complaints can't rank these, so compare to random.
        quiet = (rows.complaints_12m <= rows.complaints_12m.median()).to_numpy()
        q, kq = rows[quiet].reset_index(drop=True), max(k // 2, 10)
        series.append({
            "quiet_model": round(pick_rate(q, risk[quiet].reset_index(drop=True), kq, rng), 4),
            "quiet_random": round(q.n_sweep_rat.sum() / max(q.n_sweep.sum(), 1), 4),
            "month": m,
            "precision_silent": round(pick_rate(rows, risk, k, rng), 4),
            "precision_311": round(pick_rate(rows, rows.complaints_12m, k, rng), 4),
            "precision_positives": round(pick_rate(rows, rows.rats_12m, k, rng), 4),
            "precision_random": round(rows.n_sweep_rat.sum() / rows.n_sweep.sum(), 4),
            "n_positives": int(rows.n_sweep_rat.sum()),
            "n_swept_cells": int(len(rows)),
        })
        print(f"{m}  model {series[-1]['precision_silent']:.3f}  complaints {series[-1]['precision_311']:.3f}  "
              f"positives {series[-1]['precision_positives']:.3f}  random {series[-1]['precision_random']:.3f}  "
              f"({len(rows)} swept cells)")

    s = pd.DataFrame(series)
    summary = {
        "mean_precision_silent": round(s.precision_silent.mean(), 4),
        "mean_precision_311": round(s.precision_311.mean(), 4),
        "mean_precision_positives": round(s.precision_positives.mean(), 4),
        "mean_precision_random": round(s.precision_random.mean(), 4),
        "lift": round(s.precision_silent.mean() / s.precision_311.mean(), 3),  # read by web BacktestChart
        "lift_vs_311": round(s.precision_silent.mean() / s.precision_311.mean(), 3),
        "lift_vs_positives": round(s.precision_silent.mean() / s.precision_positives.mean(), 3),
        "months_beating_311": int((s.precision_silent > s.precision_311).sum()),
        "months_beating_positives": int((s.precision_silent > s.precision_positives).sum()),
        "quiet_mean_model": round(s.quiet_model.mean(), 4),
        "quiet_mean_random": round(s.quiet_random.mean(), 4),
        "quiet_months_beating_random": int((s.quiet_model > s.quiet_random).sum()),
        "n_months": len(s),
        "scored_on": "cells swept (proactive Initial inspections, >=10 lots on a block in a day) that month",
    }
    OUT.mkdir(exist_ok=True)
    summary["model_level"] = level
    (OUT / out).write_text(json.dumps(
        {"window": [s.month.min(), s.month.max()], "k": k, "series": series,
         "summary": summary, "synthetic": False}, indent=1))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--start", default="2016-01")
    ap.add_argument("--model", choices=["cell", "lot"], default="cell", help="cell- or building-level Model B")
    ap.add_argument("--out", default="backtest.json")
    a = ap.parse_args()
    main(a.k, a.start, a.model, a.out)
