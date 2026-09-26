"""Is a quiet block quiet because it has no rats? Two tests on real sweeps.

Test 1: proactive sweeps grouped by how much the area complained in the prior
        12 months. If silence meant "no rats", rat rates would fall as fast as
        complaints do.
Test 2: out of time. Train only to end of 2023, then among QUIET cells swept in
        2024, compare rat rates by the model's risk tier.

Limit: both only cover quiet areas that happened to get swept (mostly Rat
Mitigation Zones). Never-swept areas have no ground truth; that's what nodes are for.

Run: python3 model/validate_silence.py   -> prints tables, writes validation.json
"""
import importlib
import json
import warnings

import pandas as pd

from config import PROCESSED

warnings.filterwarnings("ignore")
models = importlib.import_module("03_models")
df = models.load()
res = {}

# ---- Test 1
d = df[df.real_cd & (df.n_lots >= models.MIN_LOTS) & (df.pop_density > 0) & (df.month >= "2015-01")].copy()
d["complaints_per_1k"] = d.complaints_12m / d.pop_density * 1e3
sw = d[d.n_sweep > 0].copy()
sw["level"] = pd.cut(sw.complaints_per_1k.rank(pct=True), [0, .25, .5, .75, 1],
                     labels=["quietest", "quiet", "loud", "loudest"])
t1 = sw.groupby("level", observed=True).agg(
    cells=("h3", "nunique"), lots_swept=("n_sweep", "sum"), rats=("n_sweep_rat", "sum"),
    complaints_per_1k=("complaints_per_1k", "mean"))
t1["rat_rate"] = t1.rats / t1.lots_swept
q, l = t1.loc["quietest"], t1.loc["loudest"]
zero = sw[sw.complaints_12m == 0]
res["test1"] = {
    "table": t1.round(4).reset_index().to_dict(orient="records"),
    "complaint_ratio_loudest_vs_quietest": round(l.complaints_per_1k / q.complaints_per_1k, 1),
    "rat_rate_ratio_loudest_vs_quietest": round(l.rat_rate / q.rat_rate, 1),
    "rat_rate_zero_complaint_cells": round(zero.n_sweep_rat.sum() / zero.n_sweep.sum(), 4),
}
print("TEST 1: sweeps by prior-12-month complaint level (per 1k residents)")
print(t1[["cells", "lots_swept", "rat_rate", "complaints_per_1k"]].round(3).to_string())
print(f"complaints {res['test1']['complaint_ratio_loudest_vs_quietest']}x apart, "
      f"rats only {res['test1']['rat_rate_ratio_loudest_vs_quietest']}x; "
      f"zero-complaint cells: {res['test1']['rat_rate_zero_complaint_cells']:.1%} rats\n")

# ---- Test 2
s = models.train_until(df, "2023-12", "2024-01")[["h3", "is_silent", "risk_b", "eligible"]]
fut = df[df.month.between("2024-01", "2024-12")].groupby("h3")[["n_sweep", "n_sweep_rat"]].sum()
past = df[df.month.between("2023-01", "2023-12")].groupby("h3").n_complaints.sum().rename("c23")
x = (s[s.eligible].set_index("h3").join(fut).join(past)
     .fillna({"n_sweep": 0, "n_sweep_rat": 0, "c23": 0}))
x = x[x.n_sweep > 0]
quiet = x[x.c23 <= x.c23.quantile(0.5)].copy()
quiet["tier"] = pd.qcut(quiet.risk_b.rank(method="first"), 3, labels=["low", "mid", "high"])


def rate(g):
    return pd.Series({"cells": len(g), "lots": g.n_sweep.sum(),
                      "rat_rate": g.n_sweep_rat.sum() / g.n_sweep.sum()})


t2 = quiet.groupby("tier", observed=True).apply(rate)
t2s = quiet.groupby("is_silent").apply(rate)
res["test2"] = {"by_risk_tier": t2.round(4).reset_index().to_dict(orient="records"),
                "by_silent_flag": t2s.round(4).reset_index().to_dict(orient="records")}
print("TEST 2: quiet cells swept in 2024, by end-2023 model risk tier")
print(t2.round(3).to_string())
print(t2s.rename(index={True: "flagged silent", False: "not flagged"}).round(3).to_string())

# ---- Test 3: independent evidence where DOHMH never swept.
# Restaurant cycle inspections are scheduled (not complaint-driven) and citywide.
# Model B never sees them. Among cells with NO sweep 2022-2024, does B's end-2023
# risk predict 2024 restaurant rat violations (04K) per restaurant inspection?
import duckdb, h3
from config import H3_RES, RAW

rest = duckdb.sql(f"""
    select Latitude as lat, Longitude as lng, CAMIS, "INSPECTION DATE" as d,
           max(case when "VIOLATION CODE" = '04K' then 1 else 0 end) as rat
    from read_csv_auto('{RAW / "restaurant_inspections.csv"}', sample_size = 50000)
    where "INSPECTION TYPE" like 'Cycle Inspection%' and year("INSPECTION DATE") = 2024
      and Latitude between 40.4 and 41
    group by all""").df()
rest["h3"] = [h3.latlng_to_cell(a, b, H3_RES) for a, b in zip(rest.lat, rest.lng)]
r = rest.groupby("h3").agg(insp=("rat", "size"), rat=("rat", "sum"))
swept = df[df.month.between("2022-01", "2024-12")].groupby("h3").n_sweep.sum()
never = s[s.eligible & ~s.h3.isin(swept[swept > 0].index)].set_index("h3").join(r, how="inner")
never["tier"] = pd.qcut(never.risk_b.rank(method="first"), 3, labels=["low", "mid", "high"])
t3 = never.groupby("tier", observed=True).apply(lambda g: pd.Series({
    "cells": len(g), "restaurant_inspections": g.insp.sum(), "rat_violation_rate": g.rat.sum() / g.insp.sum()}))
t3s = never.groupby("is_silent").apply(lambda g: pd.Series({
    "cells": len(g), "restaurant_inspections": g.insp.sum(), "rat_violation_rate": g.rat.sum() / g.insp.sum()}))
res["test3"] = {"by_risk_tier": t3.round(4).reset_index().to_dict(orient="records"),
                "by_silent_flag": t3s.round(4).reset_index().to_dict(orient="records")}
print("\nTEST 3: NEVER-swept cells, 2024 restaurant rat violations (04K) by end-2023 model tier")
print(t3.round(4).to_string())
print(t3s.rename(index={True: "flagged silent", False: "not flagged"}).round(4).to_string())

# ---- Test 4: how the silent-block equity result depends on normalising Model A
from scipy.stats import rankdata

cur = pd.read_parquet(PROCESSED / "scores.parquet").merge(
    df[df.month == df.month.max()][["h3", "units_res"]], on="h3")
e = cur[cur.eligible]
pr = lambda x: rankdata(x) / len(x)
rows = []
for label, a in {"raw count": e.risk_a_var, "per property": e.risk_a_var / e.n_lots,
                 "per home": e.risk_a_var / e.units_res.clip(lower=1),
                 "per resident (used)": e.risk_a_var / e.pop_density}.items():
    sil = e[(pr(e.risk_b) >= 0.6) & (pr(e.risk_b) - pr(a) > 0.25)]
    rows.append({"normalisation": label, "silent_cells": len(sil),
                 "median_income": sil.median_income.median(),
                 "limited_english": sil.limited_english_share.median()})
rows.append({"normalisation": "ALL eligible", "silent_cells": len(e),
             "median_income": e.median_income.median(), "limited_english": e.limited_english_share.median()})
t4 = pd.DataFrame(rows)
res["test4"] = t4.round(3).to_dict(orient="records")
print("\nTEST 4: silent-block profile under each normalisation of Model A")
print(t4.round(3).to_string(index=False))

(PROCESSED / "validation.json").write_text(json.dumps(res, indent=2, default=str))
