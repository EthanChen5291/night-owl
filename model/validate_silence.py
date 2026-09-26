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

(PROCESSED / "validation.json").write_text(json.dumps(res, indent=2, default=str))
