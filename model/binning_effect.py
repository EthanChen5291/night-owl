"""Did the Nov 2024 bin rule (homes with 1-9 units) cut complaints, rats, or both?

Before/after with a comparison group (difference-in-differences):
  before = 2023-12 .. 2024-10, after = 2024-12 .. 2025-10 (same months, Nov 2024 skipped)
  treated = cells where most lots are 1-9 unit homes (top third by share_small_homes)
  control = cells with few small homes (bottom third)
Outcomes: 311 rat complaints per cell-month (deduped), and the share of swept lots where
inspectors found rats. If complaints fall more than rats, complaints overstate the win.

Run: python3 model/binning_effect.py   -> prints the table, writes out/binning_effect.json
"""
import importlib
import json
from pathlib import Path

import pandas as pd

models = importlib.import_module("03_models")
OUT = Path(__file__).resolve().parent / "out"

df = models.load()
d = df[df.real_cd & (df.n_lots >= models.MIN_LOTS)].copy()
d["period"] = None
d.loc[d.month.between("2023-12", "2024-10"), "period"] = "before"
d.loc[d.month.between("2024-12", "2025-10"), "period"] = "after"
d = d[d.period.notna()]

tiers = d.drop_duplicates("h3").set_index("h3").share_small_homes.rank(pct=True)
d["group"] = d.h3.map(tiers.apply(lambda q: "many small homes" if q > 2 / 3 else ("few small homes" if q <= 1 / 3 else None)))
d = d[d.group.notna()]

t = d.groupby(["group", "period"]).agg(
    cells=("h3", "nunique"), complaints_per_cell_month=("n_complaints", "mean"),
    lots_swept=("n_sweep", "sum"), rats_found=("n_sweep_rat", "sum"))
t["sweep_rat_rate"] = t.rats_found / t.lots_swept
print(t.round(4).to_string())

res = {}
for g in t.index.get_level_values(0).unique():
    b, a = t.loc[(g, "before")], t.loc[(g, "after")]
    res[g] = {"complaints_change": round(a.complaints_per_cell_month / b.complaints_per_cell_month - 1, 4),
              "sweep_rat_rate_change": round(a.sweep_rat_rate / b.sweep_rat_rate - 1, 4),
              "lots_swept_before": int(b.lots_swept), "lots_swept_after": int(a.lots_swept)}
res["difference_in_differences"] = {
    k: round(res["many small homes"][k] - res["few small homes"][k], 4)
    for k in ["complaints_change", "sweep_rat_rate_change"]}
print(json.dumps(res, indent=2))
OUT.mkdir(exist_ok=True)
(OUT / "binning_effect.json").write_text(json.dumps({"table": t.round(4).reset_index().to_dict(orient="records"),
                                                     "summary": res}, indent=2))
