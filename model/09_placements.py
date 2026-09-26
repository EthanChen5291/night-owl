"""Step 9: where exactly to put a node INSIDE a ranked hexagon (a layer on top, nothing replaced).

A node stays for days or weeks, so it should sit where rats most likely pass, not where one was seen
today. Each r9 hexagon (~350 m) is split into its H3 r11 spots (~50 m, about half a block; ~49 per
hexagon). Each spot is scored, relative to the other spots in the same hexagon, on:

  sightings    311 rat sightings / signs at the spot, prior 24 months (deduped)
  rats_found   Initial inspections that found rat activity at the spot, prior 24 months
  bldg_risk    highest building-level risk (lots.py) among the spot's buildings
  food         restaurants + litter baskets
  harborage    storm drains (catch basins) + vacant lots

A spot needs a live street tree (the node clamps to a tree guard); the mount is the spot's tree closest
to the spot centre. Output: the top 3 spots per hexagon for silent cells, top-10% risk cells and
plan nodes.

Honest check (--validate): scores built from data up to month T; within hexagons swept in the next 12
months, do top-scored spots have more rats found than the others?

Output: model/out/placements.json  {month, cells: {h3: [{rank, spot_h3, lat, lon, tree_id,
         mount_address, score, reasons[], stats{}}]}}
Run: python3 model/09_placements.py [--top 3] [--validate]
"""
import argparse
import importlib
import json
from pathlib import Path

import duckdb
import h3
import numpy as np
import pandas as pd

from config import PROCESSED, RAW

models = importlib.import_module("03_models")
lots = importlib.import_module("lots")
OUT = Path(__file__).resolve().parent / "out"
SPOT_RES = 11
WEIGHTS = {"sightings": 0.30, "rats_found": 0.25, "bldg_risk": 0.20, "food": 0.15, "harborage": 0.10}


def spot(df: pd.DataFrame, lat="latitude", lng="longitude") -> pd.Series:
    return pd.Series([h3.latlng_to_cell(a, b, SPOT_RES) for a, b in zip(df[lat], df[lng])], index=df.index)


def load_points() -> dict:
    con = duckdb.connect()
    q = lambda sql: con.sql(sql).df()
    pts = {
        "restaurants": q(f"""select distinct CAMIS, Latitude as latitude, Longitude as longitude
            from read_csv_auto('{RAW / "restaurant_inspections.csv"}', sample_size = 50000)
            where Latitude between 40.4 and 41"""),
        "baskets": q(f"""select Latitude as latitude, Longitude as longitude
            from read_csv_auto('{RAW / "dsny_litter_baskets.csv"}') where Latitude between 40.4 and 41"""),
        "basins": q(f"""select LATITUDE as latitude, LONGITUDE as longitude
            from read_csv_auto('{RAW / "dep_catch_basins.csv"}') where LATITUDE between 40.4 and 41"""),
        "trees": q(f"""select tree_id, address, latitude, longitude
            from read_csv_auto('{RAW / "street_trees_2015.csv"}') where status = 'Alive'"""),
    }
    for name, d in pts.items():
        d["spot"] = spot(d)
    return pts


def spot_table(cells: list[str], upto: str, df: pd.DataFrame, pts: dict, bmodel) -> pd.DataFrame:
    """Score every r11 spot inside `cells` using only data up to month `upto`."""
    rows = [(c, s) for c in cells for s in h3.cell_to_children(c, SPOT_RES)]
    t = pd.DataFrame(rows, columns=["h3", "spot"])
    lo = str(pd.Period(upto, "M") - 23)

    comp = pd.read_parquet(PROCESSED / "complaints.parquet",
                           columns=["latitude", "longitude", "month", "is_repeat", "h3"])
    comp = comp[comp.h3.isin(cells) & ~comp.is_repeat & comp.month.between(lo, upto)]
    insp = pd.read_parquet(PROCESSED / "inspections.parquet",
                           columns=["latitude", "longitude", "month", "is_rat", "h3"])
    insp = insp[insp.h3.isin(cells) & insp.month.between(lo, upto)]
    count = lambda d: t.spot.map(spot(d).value_counts()).fillna(0) if len(d) else 0.0
    t["sightings"] = count(comp)
    t["rats_found"] = count(insp[insp.is_rat])
    t["restaurants"] = t.spot.map(pts["restaurants"].spot.value_counts()).fillna(0)
    t["baskets"] = t.spot.map(pts["baskets"].spot.value_counts()).fillna(0)
    t["basins"] = t.spot.map(pts["basins"].spot.value_counts()).fillna(0)
    t["trees"] = t.spot.map(pts["trees"].spot.value_counts()).fillna(0)

    lt = lots.lots()
    lt = lt[lt.h3.isin(cells)].copy()
    lt["spot"] = spot(lt)
    t["vacant"] = t.spot.map(lt[lt.lot_is_vacant == 1].spot.value_counts()).fillna(0)
    cm = df[(df.month == upto) & df.h3.isin(cells)]
    risk = lots.predict_lots(bmodel, cm)
    risk["spot"] = spot(risk)
    t["bldg_risk"] = t.spot.map(risk.groupby("spot").risk.max()).fillna(0)

    t["food"] = t.restaurants + t.baskets
    t["harborage"] = t.basins + t.vacant
    # relative to the other spots in the same hexagon: 0..1 rank within the cell
    for f in WEIGHTS:
        t[f"{f}_rel"] = t.groupby("h3")[f].rank(pct=True, method="average")
        t.loc[t.groupby("h3")[f].transform("max") == 0, f"{f}_rel"] = 0.0  # all zero in cell: no signal
    t["score"] = sum(w * t[f"{f}_rel"] for f, w in WEIGHTS.items())
    return t


def reasons(r) -> list[str]:
    out = []
    if r.sightings: out.append(f"{int(r.sightings)} rat sighting{'s' if r.sightings > 1 else ''} (2 yrs)")
    if r.rats_found: out.append(f"rats found {int(r.rats_found)}x by inspectors")
    if r.bldg_risk >= 0.15: out.append(f"high-risk building ({r.bldg_risk:.0%})")
    if r.restaurants: out.append(f"{int(r.restaurants)} restaurant{'s' if r.restaurants > 1 else ''}")
    if r.baskets: out.append(f"{int(r.baskets)} litter basket{'s' if r.baskets > 1 else ''}")
    if r.basins: out.append(f"{int(r.basins)} storm drain{'s' if r.basins > 1 else ''}")
    if r.vacant: out.append("vacant lot")
    return out or ["no strong signal: general coverage"]


def validate(df, pts) -> dict:
    """Features to 2024-08; target: rats found by sweeps 2024-09..2025-08 at each spot."""
    upto = "2024-08"
    insp = pd.read_parquet(PROCESSED / "inspections.parquet",
                           columns=["latitude", "longitude", "month", "is_rat", "is_sweep", "h3"])
    fut = insp[insp.is_sweep & insp.month.between("2024-09", "2025-08")].copy()
    fut["spot"] = spot(fut)
    per = fut.groupby(["h3", "spot"]).agg(n=("is_rat", "size"), rats=("is_rat", "sum")).reset_index()
    ok = per.groupby("h3").spot.transform("size") >= 4           # hexagons with >= 4 swept spots
    per = per[ok]
    cells = sorted(per.h3.unique())
    bmodel = lots.fit(lots.training_rows(df, upto))
    t = spot_table(cells, upto, df, pts, bmodel).merge(per, on=["h3", "spot"], how="inner")
    t["sightings_only"] = t.sightings_rel
    rng = np.random.default_rng(0)
    t["random"] = rng.random(len(t))
    res = {"hexagons": len(cells), "swept_spots": int(len(t))}
    for m in ["score", "sightings_only", "random"]:
        top = t.sort_values(m, ascending=False).groupby("h3").head(3)
        res[f"top3_rat_rate_{m}"] = round(top.rats.sum() / top.n.sum(), 4)
    res["all_swept_spots_rat_rate"] = round(t.rats.sum() / t.n.sum(), 4)
    return res


def main(top: int, do_validate: bool) -> None:
    df = models.load()
    pts = load_points()
    if do_validate:
        v = validate(df, pts)
        print("VALIDATION (features to 2024-08, rats found in sweeps 2024-09..2025-08):")
        print(json.dumps(v, indent=2))
        (OUT / "placements_validation.json").write_text(json.dumps(v, indent=2))

    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    month = scores.month.iloc[0]
    cells_json = json.loads((OUT / "cells.json").read_text())["cells"]
    plan = json.loads((OUT / "plan.json").read_text())
    wanted = sorted({c["h3"] for c in cells_json if c.get("is_silent") or c.get("tier_risk")}
                    | {n["h3"] for n in plan["nodes"]})
    upto = str(pd.Period(month, "M") - 1)
    bmodel = lots.fit(lots.training_rows(df, upto))
    t = spot_table(wanted, month, df, pts, bmodel)
    t = t[t.trees > 0]                                            # needs a tree guard to clamp to

    trees = pts["trees"].set_index("spot")
    out = {}
    for c, g in t.sort_values("score", ascending=False).groupby("h3", sort=False):
        opts = []
        for i, r in enumerate(g.head(top).itertuples()):
            la, lo = h3.cell_to_latlng(r.spot)
            cand = trees.loc[[r.spot]]
            d = (cand.latitude - la) ** 2 + (cand.longitude - lo) ** 2
            tr = cand.iloc[int(np.argmin(d.to_numpy()))]
            opts.append({"rank": i + 1, "spot_h3": r.spot, "lat": round(float(tr.latitude), 6),
                         "lon": round(float(tr.longitude), 6), "tree_id": str(tr.tree_id),
                         "mount_address": tr.address, "score": round(float(r.score), 3),
                         "reasons": reasons(r),
                         "stats": {k: float(getattr(r, k)) for k in
                                   ["sightings", "rats_found", "bldg_risk", "restaurants", "baskets", "basins", "vacant", "trees"]}})
        out[c] = opts
    (OUT / "placements.json").write_text(json.dumps({"month": month, "top": top, "cells": out}))
    print(f"placements.json: {len(out)} hexagons, up to {top} node spots each")
    first = plan["nodes"][0]["h3"]
    for o in out.get(first, []):
        print(f"  plan node #1 option {o['rank']}: tree {o['tree_id']} at {o['mount_address']} "
              f"(score {o['score']}) — {', '.join(o['reasons'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    main(a.top, a.validate)
