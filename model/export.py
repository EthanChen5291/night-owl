"""Write the map's JSON (contract section 6) from step 3/4 outputs.

cells.json  [{h3, risk_a, risk_b, silence, ci_lo, ci_hi, n_complaints, n_inspections,
              n_fail, income_q, reasons[]}]  + extras: is_silent, data_gap, risk_b_prob
plan.json   written by 04_optimizer.py (re-run here so both come from the same scores)

risk_a / risk_b are percentiles (0-1) among eligible cells so the "city sees /
actually there" toggle uses one colour scale. reasons[] = top-3 Model B feature
contributions (LightGBM SHAP) in plain words.

Run: python3 model/export.py [--out DIR]
"""
import argparse
import importlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from config import PROCESSED

models = importlib.import_module("03_models")
optimizer = importlib.import_module("04_optimizer")

PHRASES = {
    "n_lots": "many properties", "year_built_median": "old building stock",
    "share_pre1940": "mostly pre-1940 buildings", "share_vacant": "vacant lots",
    "share_residential": "mostly residential", "share_mixed_use": "mixed-use buildings",
    "share_commercial": "commercial buildings", "share_industrial": "industrial land",
    "floors_mean": "building height", "units_res": "dense housing",
    "bldg_area": "large building footprint", "retail_area": "retail frontage",
    "com_area": "commercial space", "n_restaurants": "many restaurants",
    "n_litter_baskets": "street litter baskets", "n_catch_basins": "storm drains",
    "n_trees": "street trees", "n_subway_entrances": "subway entrances",
    "share_park": "park land", "dob_permits_3m": "recent construction",
    "rest_04k_12m": "restaurant rat violations", "rest_08a_12m": "restaurant pest-harbourage violations",
    "temp_c": "warm season", "month_of_year": "time of year", "refuse_tons_cd": "high trash volume",
    "median_income": "local income level", "pop_density": "population density",
}


def clean(v):
    if isinstance(v, (float, np.floating)) and (math.isnan(v) or math.isinf(v)):
        return None
    return v.item() if isinstance(v, np.generic) else v


def top_reasons(df: pd.DataFrame, score_month: str, rows: pd.DataFrame) -> list[list[str]]:
    hist = df[(df.month < score_month) & (df.n_sweep > 0)]
    model = models.fit_b(hist)
    contrib = model.predict(rows[models.B_FEATS], pred_contrib=True)[:, :-1]  # drop bias
    names = np.array(models.B_FEATS)
    out = []
    for c in contrib:
        idx = [i for i in np.argsort(-c)[:3] if c[i] > 0]
        out.append([PHRASES.get(n, n) for n in names[idx]])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PROCESSED), help="output folder")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = models.load()
    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    month = scores.month.iloc[0]

    last12 = df[(df.month < month) & (df.month >= str(pd.Period(month, "M") - 12))]
    recent = last12.groupby("h3").agg(n_complaints=("n_complaints", "sum"),
                                      n_inspections=("n_initial", "sum"), n_fail=("n_rat", "sum"))
    s = scores.drop(columns=["n_complaints"]).merge(recent, on="h3", how="left")
    s[["n_complaints", "n_inspections", "n_fail"]] = s[["n_complaints", "n_inspections", "n_fail"]].fillna(0)

    e = s.eligible
    s["risk_a_pct"] = np.nan
    s["risk_b_pct"] = np.nan
    s.loc[e, "risk_a_pct"] = s.loc[e, "complaints_per_capita"].rank(pct=True)
    s.loc[e, "risk_b_pct"] = s.loc[e, "risk_b"].rank(pct=True)
    s["income_q"] = pd.qcut(s.median_income, 5, labels=[1, 2, 3, 4, 5]).astype("float")

    target = df[df.month == month].set_index("h3").loc[s.h3].reset_index()
    s["reasons"] = top_reasons(df, month, target)

    cells = [{k: clean(v) for k, v in {
        "h3": r.h3, "risk_a": r.risk_a_pct, "risk_b": r.risk_b_pct, "silence": r.silence,
        "ci_lo": r.silence_lo, "ci_hi": r.silence_hi, "n_complaints": int(r.n_complaints),
        "n_inspections": int(r.n_inspections), "n_fail": int(r.n_fail), "income_q": r.income_q,
        "reasons": r.reasons,
        # extras beyond the contract (safe to ignore)
        "is_silent": bool(r.is_silent), "data_gap": r.data_gap, "risk_b_prob": r.risk_b,
        "eligible": bool(r.eligible),
    }.items()} for r in s.itertuples()]
    (out / "cells.json").write_text(json.dumps(cells))
    picks = optimizer.plan(scores, 20)
    (out / "plan.json").write_text(json.dumps(picks, indent=2))

    print(f"cells.json: {len(cells):,} cells for {month} ({(out / 'cells.json').stat().st_size / 1e6:.1f} MB)")
    print(f"plan.json: {len(picks)} sites")
    ex = next(c for c in cells if c["is_silent"])
    print("example silent cell:", json.dumps(ex))
