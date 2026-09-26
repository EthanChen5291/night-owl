#!/usr/bin/env -S uv run --with duckdb --with lightgbm --with h3 --with shap --with scikit-learn --with pandas --with pyarrow --with numpy --with matplotlib python
"""score.py: score the latest month with the trained models and write the files the API serves.

model/out/cells_<month>.json and cells.json  GET /cells shape (city/cells.fixture.json)
model/out/plan.json                          GET /plan shape, k = 8 greedy placements snapped to tree pits
"""
from __future__ import annotations

import datetime as dt
import json
import math
import time

import h3
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from common import A_FEATURES, B_FEATURES, MONTHS, OUT, TREES_JSON, Timer, check_leakage, dump_json, load_features, percentile_rank

N0 = 10.0          # Beta-Binomial prior strength
K_PLAN = 8
EXCLUSION_M = 100.0
PLAN_BOROUGH = "MN"  # the renderer covers Lower Manhattan; the planner only places nodes there


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_tree_pits() -> pd.DataFrame | None:
    """2015 street-tree pits. There is no street_trees parquet in the bake; the renderer's trees.json
    (Lower Manhattan bbox, local 0.1 m coordinates, no tree ids) is the fallback."""
    if not TREES_JSON.exists():
        return None
    meta_path = TREES_JSON.parent / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"origin": [40.7165, -73.99], "mPerDegLat": 110574.0, "mPerDegLng": 84374.6}
    raw = json.loads(TREES_JSON.read_text())
    if not raw:
        return None
    if isinstance(raw[0], dict):  # {id, x, y, h3} form
        x = np.array([t["x"] for t in raw], float)
        y = np.array([t["y"] for t in raw], float)
        ids = [str(t.get("id", i)) for i, t in enumerate(raw)]
    else:  # [x_dm, y_dm, dbh] form (coordinates in 0.1 m)
        arr = np.array(raw, float)
        x, y = arr[:, 0] / 10.0, arr[:, 1] / 10.0
        ids = [f"tree-{i}" for i in range(len(arr))]
    lat = meta["origin"][0] + y / meta["mPerDegLat"]
    lon = meta["origin"][1] + x / meta["mPerDegLng"]
    df = pd.DataFrame({"tree_id": ids, "lat": lat, "lon": lon})
    df["h3"] = [h3.latlng_to_cell(a, b, 9) for a, b in zip(lat, lon)]
    return df


def main() -> None:
    t0 = time.time()
    check_leakage(B_FEATURES)
    feats = load_features()
    month = feats.month.max()
    cur = feats[feats.month == month].reset_index(drop=True)
    n_insp = feats.groupby("h3").n_initial_l60_0.sum()
    with Timer("models"):
        mA = lgb.Booster(model_file=str(OUT / "model_a.txt"))
        mB = lgb.Booster(model_file=str(OUT / "model_b.txt"))
        boots = [lgb.Booster(model_file=str(p)) for p in sorted(OUT.glob("model_b_boot_*.txt"))]
        cal = json.loads((OUT / "model_b_calibration.json").read_text())
        calibrate = lambda p: np.interp(p, cal["x"], cal["y"])

    with Timer("score"):
        XA = cur[A_FEATURES].values.astype(np.float32)
        XB = cur[B_FEATURES].values.astype(np.float32)
        score_a = np.exp(mA.predict(XA, raw_score=True) + np.log1p(cur.pluto_res_units.values.astype(float)))
        raw_b = mB.predict(XB)
        score_b = calibrate(raw_b)
        boot = np.column_stack([calibrate(m.predict(XB)) for m in boots]) if boots else score_b[:, None]
        lo, hi = boot.min(axis=1), boot.max(axis=1)
        lo, hi = np.minimum(lo, score_b), np.maximum(hi, score_b)
        pct_a, pct_b = percentile_rank(score_a), percentile_rank(score_b)
        silence = pct_b - pct_a
        expl = shap.TreeExplainer(mB)
        sv = expl.shap_values(XB)
        if isinstance(sv, list):
            sv = sv[-1]

    cells = []
    for i, r in cur.iterrows():
        order = np.argsort(-np.abs(sv[i]))[:3]
        cells.append({
            "h3": r.h3,
            "score_a": round(float(score_a[i]), 3),
            "score_b": round(float(score_b[i]), 3),
            "pct_a": round(float(pct_a[i]), 1),
            "pct_b": round(float(pct_b[i]), 1),
            "silence": round(float(silence[i]), 1),
            "ci_b": [round(float(lo[i]), 3), round(float(hi[i]), 3)],
            "posterior": {"alpha": round(float(score_b[i] * N0), 3), "beta": round(float((1 - score_b[i]) * N0), 3), "n_events": 0},
            "reasons": [{"feature": B_FEATURES[j], "shap": round(float(sv[i, j]), 3)} for j in order],
            "cd": r.cd if isinstance(r.cd, str) else None,
            "rmz": r.rmz if isinstance(r.rmz, str) else None,
            "n_inspections": int(n_insp.get(r.h3, 0)),
            "last_event_at": None,
        })
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    doc = {"month": month, "generated_at": generated, "cells": cells}
    dump_json(doc, OUT / f"cells_{month}.json")
    dump_json(doc, OUT / "cells.json")
    print(f"cells_{month}.json: {len(cells)} cells, score_b mean {score_b.mean():.3f} [{score_b.min():.3f}, {score_b.max():.3f}], "
          f"score_a mean {score_a.mean():.3f}, silence sd {silence.std():.1f}")

    # ---------------------------------------------------------------- greedy node placement
    with Timer("plan"):
        pits = load_tree_pits()
        by_h3 = {c["h3"]: c for c in cells}
        cand = cur[(cur.borough == PLAN_BOROUGH)].copy()
        cand["gain"] = [(lambda a, b: (a * b) / ((a + b) ** 2 * (a + b + 1)))(by_h3[c]["posterior"]["alpha"], by_h3[c]["posterior"]["beta"])
                        * by_h3[c]["score_b"] * 100.0 for c in cand.h3]
        cand["silence"] = [by_h3[c]["silence"] for c in cand.h3]
        cand = cand[cand.silence > 0].sort_values("gain", ascending=False)
        pits_by_cell = {k: g for k, g in pits.groupby("h3")} if pits is not None else {}
        chosen, nodes, skipped_no_pit = [], [], 0
        for _, r in cand.iterrows():
            if len(nodes) >= K_PLAN:
                break
            c = by_h3[r.h3]
            if pits is not None:
                g = pits_by_cell.get(r.h3)
                if g is None:
                    skipped_no_pit += 1
                    continue
                g = g.assign(d=[haversine_m(r.lat, r.lon, a, b) for a, b in zip(g.lat, g.lon)]).sort_values("d")
                pick = None
                for _, p in g.iterrows():
                    if all(haversine_m(p.lat, p.lon, q[0], q[1]) >= EXCLUSION_M for q in chosen):
                        pick = p
                        break
                if pick is None:
                    continue
                lat, lon, tid = float(pick.lat), float(pick.lon), str(pick.tree_id)
            else:
                lat, lon, tid = float(r.lat), float(r.lon), f"centroid-{r.h3}"
                if any(haversine_m(lat, lon, q[0], q[1]) < EXCLUSION_M for q in chosen):
                    continue
            chosen.append((lat, lon))
            top = c["reasons"][0]["feature"]
            nodes.append({
                "rank": len(nodes) + 1, "h3": r.h3, "lat": round(lat, 6), "lon": round(lon, 6), "tree_id": tid,
                "expected_gain": round(float(r.gain), 4), "silence": c["silence"],
                "reason": f"P(active) {c['score_b']:.2f} [{c['ci_b'][0]:.2f}-{c['ci_b'][1]:.2f}], silence {c['silence']:+.0f}; top driver {top}",
            })
        dump_json({"month": month, "k": K_PLAN, "nodes": nodes}, OUT / "plan.json")
        src = "trees.json pits" if pits is not None else "cell centroids (no tree data)"
        print(f"plan.json: {len(nodes)} nodes from {len(cand)} silent {PLAN_BOROUGH} candidates, snapped to {src}; "
              f"{skipped_no_pit} candidates skipped for lack of a pit")
        for n in nodes:
            print("  ", n["rank"], n["h3"], n["tree_id"], n["expected_gain"], n["reason"])
    print(f"[score total] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
