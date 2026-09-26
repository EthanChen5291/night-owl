"""Step 7: building-level backtest. Which BUILDINGS should an inspector check first?

Every month (2016-01 ..), among the buildings DOHMH swept that month, each method picks its top K:
  building   building-level Model B (lots.py), trained only on earlier months
  hexagon    cell-level Model B; every building gets its cell's score
  complaints rat complaints about that building (same BBL) in the prior 12 months
  positives  rats found at that building by any Initial inspection in the prior 24 months
  random     all swept buildings (base rate)

Two ways to count a hit, because rats range 30-150 m (NYC: Combs 2017; Vancouver: 99% of relatives
in the same block), so signs often turn up next door rather than at the exact building:
  exact  inspectors found rat activity at that building
  block  rat activity was found somewhere on that building's tax block that day

Also "fresh": buildings with no Initial inspection in the prior 24 months (no history to use).

Output: model/out/building_backtest.json
Run: python3 model/07_building_backtest.py [--k 500] [--start 2016-01]
"""
import argparse
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import PROCESSED

models = importlib.import_module("03_models")
lots = importlib.import_module("lots")
OUT = Path(__file__).resolve().parent / "out"
REFIT_EVERY = 6
METHODS = ["building", "hexagon", "complaints", "positives"]


def main(k: int, start: str) -> None:
    df = models.load()
    insp = pd.read_parquet(PROCESSED / "inspections.parquet",
                           columns=["bbl", "h3", "month", "date", "boro_code", "block", "is_sweep", "is_rat"])
    comp = pd.read_parquet(PROCESSED / "complaints.parquet", columns=["bbl", "month", "is_repeat"])
    comp = comp[comp.bbl.notna() & ~comp.is_repeat]
    # did anyone on the same tax block have rats that day?
    insp["block_rat"] = insp.groupby(["boro_code", "block", "date"]).is_rat.transform("max")

    months = sorted(m for m in df.month.unique() if start <= m < df.month.max())
    rng = np.random.default_rng(0)
    series, bmodel, cmodel = [], None, None
    for i, m in enumerate(months):
        prev = str(pd.Period(m, "M") - 1)
        if bmodel is None or i % REFIT_EVERY == 0:
            bmodel = lots.fit(lots.training_rows(df, prev))
            cmodel = models.fit_b(df[(df.month < m) & (df.n_sweep > 0)])
        cm = df[(df.month == m) & df.real_cd]
        swept = insp[insp.is_sweep & (insp.month == m) & insp.h3.isin(cm.h3)].drop_duplicates("bbl")
        if len(swept) < k:
            continue
        x = swept.merge(cm[["h3"] + models.B_FEATS], on="h3").merge(
            lots.lots()[["bbl"] + lots.LOT_FEATS], on="bbl", how="left")
        x["building"] = bmodel.predict_proba(x[lots.FEATS])[:, 1]
        x["hexagon"] = cmodel.predict(x[models.B_FEATS])
        m12, m24 = str(pd.Period(m, "M") - 12), str(pd.Period(m, "M") - 24)
        x["complaints"] = x.bbl.map(comp[(comp.month >= m12) & (comp.month < m)].groupby("bbl").size()).fillna(0)
        past = insp[(insp.month >= m24) & (insp.month < m)]
        x["positives"] = x.bbl.map(past.groupby("bbl").is_rat.sum()).fillna(0)
        # buildings with NO Initial inspection in the prior 24 months: the silent-block case,
        # where "rats found here before" has nothing to go on
        x["fresh"] = ~x.bbl.isin(set(past.bbl))
        x["_tie"] = rng.random(len(x))

        row = {"month": m, "n_swept_buildings": int(len(x)),
               "random_exact": round(x.is_rat.mean(), 4), "random_block": round(x.block_rat.mean(), 4)}
        for meth in METHODS:
            top = x.sort_values([meth, "_tie"], ascending=False).head(k)
            row[f"{meth}_exact"] = round(top.is_rat.mean(), 4)
            row[f"{meth}_block"] = round(top.block_rat.mean(), 4)
        f = x[x.fresh]
        kf = max(min(k // 5, len(f) // 10), 10)
        row["n_fresh_buildings"] = int(len(f))
        row["fresh_random_exact"] = round(f.is_rat.mean(), 4)
        for meth in ["building", "hexagon", "complaints"]:
            row[f"fresh_{meth}_exact"] = round(f.sort_values([meth, "_tie"], ascending=False).head(kf).is_rat.mean(), 4)
        series.append(row)
        print(f"{m}  exact: bldg {row['building_exact']:.3f} hex {row['hexagon_exact']:.3f} "
              f"compl {row['complaints_exact']:.3f} pos {row['positives_exact']:.3f} rand {row['random_exact']:.3f} | "
              f"block: bldg {row['building_block']:.3f} hex {row['hexagon_block']:.3f}")

    s = pd.DataFrame(series)
    summary = {"k": k, "n_months": len(s), "window": [s.month.min(), s.month.max()]}
    for hit in ["exact", "block"]:
        summary[hit] = {meth: round(s[f"{meth}_{hit}"].mean(), 4) for meth in METHODS + ["random"]}
        for meth in ["hexagon", "complaints", "positives"]:
            summary[hit][f"building_beats_{meth}_months"] = int((s[f"building_{hit}"] > s[f"{meth}_{hit}"]).sum())
    summary["fresh_exact"] = {meth: round(s[f"fresh_{meth}_exact"].mean(), 4)
                              for meth in ["building", "hexagon", "complaints", "random"]}
    summary["fresh_exact"]["building_beats_hexagon_months"] = int((s.fresh_building_exact > s.fresh_hexagon_exact).sum())
    summary["fresh_exact"]["building_beats_complaints_months"] = int((s.fresh_building_exact > s.fresh_complaints_exact).sum())
    summary["fresh_exact"]["building_beats_random_months"] = int((s.fresh_building_exact > s.fresh_random_exact).sum())
    summary["fresh_exact"]["median_fresh_buildings_per_month"] = int(s.n_fresh_buildings.median())
    OUT.mkdir(exist_ok=True)
    (OUT / "building_backtest.json").write_text(json.dumps({"summary": summary, "series": series}, indent=1))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=500)
    ap.add_argument("--start", default="2016-01")
    a = ap.parse_args()
    main(a.k, a.start)
