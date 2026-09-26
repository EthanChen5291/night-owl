"""Step 6: which buildings to inspect first, inside each silent block and each node site.

Uses the building-level Model B (lots.py). It ranks buildings far better than the cell model
(held-out-district AUC 0.692 vs 0.630), but it does not rank CELLS better in the backtest
(19.7% vs 19.5%, fewer months won), so the cell model stays the main Model B and this is the
"inside this block, start here" list.

Output: model/out/buildings.json  {month, cells: {h3: [{bbl, address, risk, year_built, units,
         floors, bldg_class, has_restaurant}, ...top 5]}}  for silent cells and plan.json nodes.

Run: python3 model/06_buildings.py [--top 5]
"""
import argparse
import importlib
import json
from pathlib import Path

import pandas as pd

from config import PROCESSED

models = importlib.import_module("03_models")
lots = importlib.import_module("lots")
OUT = Path(__file__).resolve().parent / "out"


def main(top: int) -> None:
    df = models.load()
    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    month = scores.month.iloc[0]
    plan = json.loads((OUT / "plan.json").read_text())
    wanted = set(scores[scores.is_silent].h3) | {n["h3"] for n in plan["nodes"]}

    model = lots.fit(lots.training_rows(df, str(pd.Period(month, "M") - 1)))
    x = lots.predict_lots(model, df[(df.month == month) & df.h3.isin(wanted)])
    x = x[x.lot_is_vacant == 0].sort_values("risk", ascending=False)  # vacant lots have no building to enter

    def row(r):
        return {"bbl": r.bbl, "address": r.address, "risk": round(float(r.risk), 3),
                "year_built": None if pd.isna(r.lot_year_built) else int(r.lot_year_built),
                "units": None if pd.isna(r.lot_units_res) else int(r.lot_units_res),
                "floors": None if pd.isna(r.lot_floors) else float(r.lot_floors),
                "bldg_class": r.bldgclass, "has_restaurant": bool(r.lot_has_restaurant)}

    out = {h: [row(r) for r in g.head(top).itertuples()] for h, g in x.groupby("h3", sort=False)}
    (OUT / "buildings.json").write_text(json.dumps({"month": month, "top": top, "cells": out}))
    print(f"buildings.json: {len(out)} cells (silent + node sites), top {top} buildings each")
    n1 = plan["nodes"][0]["h3"]
    print(f"node #1 {n1}:")
    for b in out.get(n1, []):
        print("  ", b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    main(ap.parse_args().top)
