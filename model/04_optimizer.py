"""Step 4: pick N sensor-node sites.

Score = posterior rat risk x data_gap: likely rats AND we know little there.
Greedy: take the best cell, block its ring-1 neighbours (keeps nodes spread out,
~300 m+ apart, well over the 100 m minimum), repeat. Each pick snaps to the live
street tree nearest the cell centre (tree pit = mount point); catch basin fallback.

Output: data/processed/plan.json  [{rank, h3, asset_id, asset_type, lat, lng,
address, score, reason}]  (JSON contract /plan)

Run: python3 model/04_optimizer.py [--n 20] [--cd 303]
"""
import argparse
import json

import duckdb
import h3
import numpy as np
import pandas as pd

from config import H3_RES, PROCESSED, RAW


def load_assets() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect()
    trees = con.sql(f"""select tree_id, address, latitude, longitude
        from read_csv_auto('{RAW / "street_trees_2015.csv"}') where status = 'Alive'""").df()
    basins = con.sql(f"""select UNITID as asset_id, LATITUDE as latitude, LONGITUDE as longitude
        from read_csv_auto('{RAW / "dep_catch_basins.csv"}')""").df()
    for df in (trees, basins):
        df["h3"] = [h3.latlng_to_cell(a, b, H3_RES) for a, b in zip(df.latitude, df.longitude)]
    return trees, basins


def nearest(df: pd.DataFrame, lat: float, lng: float) -> pd.Series:
    d = (df.latitude - lat) ** 2 + ((df.longitude - lng) * np.cos(np.radians(lat))) ** 2
    return df.loc[d.idxmin()]


def reason(row: pd.Series) -> str:
    seen = "no proactive sweep in 24 months" if row.sweeps_24m == 0 else f"{int(row.sweeps_24m)} lots swept in 24 months"
    return (f"model rat risk {row.risk_b:.0%} (top {max(1, round(100 - row.risk_pct * 100))}%), "
            f"{seen}, {int(row.complaints_12m)} complaints last year")


def plan(scores: pd.DataFrame, n: int = 20, cd: int | None = None, assets=None,
         silent_only: bool = False) -> list[dict]:
    s = scores[scores.eligible].copy()
    if cd is not None:
        s = s[s.boro_cd == cd]
    if silent_only:
        s = s[s.is_silent]
    # Nodes are for places we can't already see. Cells where recent sweeps found
    # rats are known problems: they go straight to the DOHMH queue, not a sensor.
    # So score on the model's own belief (risk_b), not the sweep-updated posterior.
    s = s[s.sweep_rats_24m == 0]
    s["risk_pct"] = s.risk_b.rank(pct=True)
    s["score"] = s.risk_b * s.data_gap
    s = s.sort_values("score", ascending=False)

    trees, basins = assets or load_assets()
    blocked, picks = set(), []
    for _, row in s.iterrows():
        if row.h3 in blocked:
            continue
        blocked |= set(h3.grid_disk(row.h3, 1))
        t = trees[trees.h3 == row.h3]
        if len(t):
            a = nearest(t, row.lat, row.lng)
            asset = dict(asset_id=str(a.tree_id), asset_type="tree_pit", address=a.address,
                         lat=float(a.latitude), lng=float(a.longitude))
        else:
            b = basins[basins.h3 == row.h3]
            a = nearest(b if len(b) else basins, row.lat, row.lng)
            asset = dict(asset_id=a.asset_id, asset_type="catch_basin", address=None,
                         lat=float(a.latitude), lng=float(a.longitude))
        picks.append(dict(rank=len(picks) + 1, h3=row.h3, **asset,
                          score=round(float(row.score), 5), reason=reason(row)))
        if len(picks) == n:
            break
    return picks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--cd", type=int, help="community district, e.g. 303")
    ap.add_argument("--silent-only", action="store_true", help="only flagged silent blocks")
    args = ap.parse_args()

    scores = pd.read_parquet(PROCESSED / "scores.parquet")
    picks = plan(scores, args.n, args.cd, silent_only=args.silent_only)
    (PROCESSED / "plan.json").write_text(json.dumps(picks, indent=2))

    e = scores[scores.eligible]
    chosen = e[e.h3.isin([p["h3"] for p in picks])]
    print(f"{len(picks)} sites; {sum(p['asset_type'] == 'tree_pit' for p in picks)} on tree pits")
    for p in picks[:5]:
        print(f"  #{p['rank']} {p['address'] or p['asset_id']}: {p['reason']}")
    print(f"median complaints_12m   picks: {chosen.complaints_12m.median():.0f}   all: {e.complaints_12m.median():.0f}")
    print(f"median income           picks: {chosen.median_income.median():,.0f}   all: {e.median_income.median():,.0f}")
    print(f"never swept (24m)       picks: {(chosen.sweeps_24m == 0).mean():.0%}   all: {(e.sweeps_24m == 0).mean():.0%}")
