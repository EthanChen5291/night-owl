"""Write the map/API JSON (the contract in web/src/types.ts) from step 3/4 outputs.

model/out/cells.json  {month, generated_at, cells: [{h3, score_a, score_b, pct_a, pct_b, silence,
                       ci_b, posterior, reasons[{feature, shap}], cd, rmz, n_inspections,
                       last_event_at}]}  + extras (is_silent, data_gap, n_complaints_12m)
model/out/plan.json   {month, k, nodes: [{rank, h3, lat, lon, tree_id, expected_gain, silence, reason}]}

api/store.py recomputes pct_b (from score_b) and silence = pct_b - pct_a over the whole file, so:
  - only eligible cells are written (real building stock + residents), otherwise parks and rail
    yards distort the ranks;
  - pct_a is the percentile of predicted complaints PER RESIDENT (A-variant), the fair comparison;
  - score_b is Model B's belief, so the server's recomputed silence matches ours.

Run: python3 model/export.py [--k 20]
"""
import argparse
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist

from config import PROCESSED

models = importlib.import_module("03_models")
optimizer = importlib.import_module("04_optimizer")
OUT = Path(__file__).resolve().parent / "out"

# Wire names for reasons[] (the popup shows them with "_" -> " ")
NAMES = {
    "n_lots": "many_properties", "year_built_median": "building_age",
    "share_pre1940": "pre_1940_buildings", "share_vacant": "vacant_lots",
    "share_residential": "residential_share", "share_mixed_use": "mixed_use_buildings",
    "share_commercial": "commercial_share", "share_industrial": "industrial_land",
    "floors_mean": "building_height", "units_res": "housing_units", "bldg_area": "building_area",
    "retail_area": "retail_space", "com_area": "commercial_space", "n_restaurants": "restaurants",
    "n_litter_baskets": "litter_baskets", "n_catch_basins": "storm_drains", "n_trees": "street_trees",
    "n_subway_entrances": "subway_entrances", "share_park": "park_land",
    "dob_permits_3m": "construction_3mo", "temp_c": "temperature", "month_of_year": "season",
    "refuse_tons_cd": "district_trash_tons", "median_income": "median_income",
    "pop_density": "population_density",
}


def pct100(x) -> np.ndarray:
    """0..100 average-rank percentile, same rule as api/posterior.percentile_rank."""
    r = pd.Series(x).rank(method="average").to_numpy() - 1
    return np.round(100 * r / max(len(r) - 1, 1), 1)


NOT_A_PLACE = {"temp_c", "month_of_year", "refuse_tons_cd"}  # seasonal/citywide: not "why this block"


def shap_reasons(df: pd.DataFrame, month: str, rows: pd.DataFrame) -> list[list[dict]]:
    model = models.fit_b(df[(df.month < month) & (df.n_sweep > 0)])
    contrib = model.predict(rows[models.B_FEATS], pred_contrib=True)[:, :-1]  # drop bias column
    place = np.array([f not in NOT_A_PLACE for f in models.B_FEATS])
    out = []
    for c in contrib:
        c = np.where(place, c, 0.0)
        top = np.argsort(-np.abs(c))[:3]
        out.append([{"feature": NAMES.get(models.B_FEATS[i], models.B_FEATS[i]),
                     "shap": round(float(c[i]), 4)} for i in top])
    return out


def main(k: int) -> None:
    OUT.mkdir(exist_ok=True)
    df = models.load()
    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    month = scores.month.iloc[0]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    last12 = df[(df.month < month) & (df.month >= str(pd.Period(month, "M") - 12))]
    recent = last12.groupby("h3").agg(n_inspections=("n_initial", "sum"),
                                      n_complaints_12m=("n_complaints", "sum"))
    s = scores[scores.eligible].merge(recent, on="h3", how="left").reset_index(drop=True)
    s[["n_inspections", "n_complaints_12m"]] = s[["n_inspections", "n_complaints_12m"]].fillna(0)

    s["pct_a"] = pct100(s.complaints_per_capita)
    s["pct_b"] = pct100(s.risk_b)
    s["silence100"] = (s.pct_b - s.pct_a).round(1)
    # Posterior as of the scoring month: B is the prior worth PRIOR_LOTS lots, sweeps update it.
    n0 = models.PRIOR_LOTS + s.sweeps_24m
    a, b = s.risk_post * n0, (1 - s.risk_post) * n0
    lo, hi = beta_dist.ppf(0.025, a, b), beta_dist.ppf(0.975, a, b)
    target = df[df.month == month].set_index("h3").loc[s.h3].reset_index()
    reasons = shap_reasons(df, month, target)

    cells = [{
        "h3": r.h3,
        "score_a": round(float(r.risk_a), 3),              # expected rat complaints this month
        "score_b": round(float(r.risk_b), 4),              # P(active rat signs | inspected)
        "pct_a": float(r.pct_a), "pct_b": float(r.pct_b), "silence": float(r.silence100),
        "ci_b": [round(float(lo[i]), 4), round(float(hi[i]), 4)],
        "posterior": {"alpha": round(float(a[i]), 4), "beta": round(float(b[i]), 4), "n_events": 0},
        "reasons": reasons[i],
        "cd": str(int(r.boro_cd)),
        "rmz": None,                                       # TODO: Ethan's RMZ polygons
        "n_inspections": int(r.n_inspections),
        "last_event_at": None,
        # extras (not in types.ts; safe to ignore)
        "is_silent": bool(r.is_silent), "data_gap": round(float(r.data_gap), 3),
        "n_complaints_12m": int(r.n_complaints_12m),
    } for i, r in enumerate(s.itertuples())]
    (OUT / "cells.json").write_text(json.dumps({"month": month, "generated_at": now, "cells": cells}))

    sil = s.set_index("h3").silence100
    picks = optimizer.plan(scores, k)
    nodes = [{"rank": p["rank"], "h3": p["h3"], "lat": p["lat"], "lon": p["lng"],
              "tree_id": p["asset_id"], "expected_gain": p["score"],
              "silence": float(sil.get(p["h3"], 0.0)),
              "reason": f"{p['reason']}; mount: {p['address'] or p['asset_type']}"} for p in picks]
    (OUT / "plan.json").write_text(json.dumps({"month": month, "k": len(nodes), "nodes": nodes}, indent=1))

    print(f"model/out/cells.json: {len(cells):,} cells for {month} "
          f"({(OUT / 'cells.json').stat().st_size / 1e6:.1f} MB), silent: {int(s.is_silent.sum())}")
    print(f"model/out/plan.json: {len(nodes)} nodes")
    print("example:", json.dumps(next(c for c in cells if c["is_silent"]))[:600])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=20)
    main(ap.parse_args().k)
