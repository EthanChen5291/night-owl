"""Step 8: NYC rat hotspot rankings (top 10 lists + top-1% tiers).

Two rankings over eligible cells:
  risk    where rats are most likely (Model B), whatever people report
  silent  where rats are likely but complaints are far lower than expected (flagged silent cells)

Output: model/out/hotspots.json  {month, scope, n_cells, top_risk[..], top_silent[..], tiers{..}}
Each entry: rank, h3, neighborhood, borough, cd, lat, lon, rat_risk, silence, complaints_12m,
reasons, top_building. With --boroughs the ranks are recomputed within those boroughs only.

Run: python3 model/08_hotspots.py [--top 10] [--boroughs Manhattan,Brooklyn]
"""
import argparse
import json
from pathlib import Path

import h3

OUT = Path(__file__).resolve().parent / "out"


def main(top: int, boroughs: list[str] | None) -> None:
    data = json.loads((OUT / "cells.json").read_text())
    cells = [c for c in data["cells"] if not boroughs or c.get("borough") in boroughs]
    bld = json.loads((OUT / "buildings.json").read_text())["cells"] if (OUT / "buildings.json").exists() else {}
    n = len(cells)

    def entry(rank, c):
        lat, lon = h3.cell_to_latlng(c["h3"])
        b = bld.get(c["h3"], [])
        return {"rank": rank, "h3": c["h3"], "neighborhood": c.get("neighborhood"), "borough": c.get("borough"),
                "cd": c["cd"], "lat": round(lat, 6), "lon": round(lon, 6),
                "rat_risk": c["score_b"], "silence": c["silence"], "complaints_12m": c["n_complaints_12m"],
                "reasons": [r["feature"] for r in c["reasons"]],
                "top_building": b[0]["address"] if b else None}

    by_risk = sorted(cells, key=lambda c: -c["score_b"])
    by_silent = sorted((c for c in cells if c["is_silent"]), key=lambda c: -c["silence"])
    k1 = max(1, round(n * 0.01))
    tiers = {"top_1pct_risk_cells": k1,
             "top_1pct_risk_by_borough": {},
             "top_1pct_silent_by_borough": {}}
    for c in by_risk[:k1]:
        tiers["top_1pct_risk_by_borough"][c["borough"]] = tiers["top_1pct_risk_by_borough"].get(c["borough"], 0) + 1
    for c in by_silent[:k1]:
        tiers["top_1pct_silent_by_borough"][c["borough"]] = tiers["top_1pct_silent_by_borough"].get(c["borough"], 0) + 1

    res = {"month": data["month"], "scope": boroughs or "all NYC", "n_cells": n,
           "top_risk": [entry(i + 1, c) for i, c in enumerate(by_risk[:top])],
           "top_silent": [entry(i + 1, c) for i, c in enumerate(by_silent[:top])],
           "tiers": tiers}
    name = "hotspots.json" if not boroughs else f"hotspots_{'_'.join(b.lower().replace(' ', '') for b in boroughs)}.json"
    (OUT / name).write_text(json.dumps(res, indent=1))

    for title, key in [("TOP RAT-RISK HOTSPOTS", "top_risk"), ("TOP SILENT HOTSPOTS (rats likely, few complaints)", "top_silent")]:
        print(f"\n{title} — {res['scope']}")
        for e in res[key]:
            print(f"{e['rank']:>2}. {e['neighborhood']} ({e['borough']}, CD {e['cd']})  risk {e['rat_risk']:.1%}  "
                  f"silence {e['silence']:+.0f}  complaints/yr {e['complaints_12m']}  bldg: {e['top_building']}")
    print(f"\ntop 1% = {k1} cells; risk by borough {tiers['top_1pct_risk_by_borough']}; "
          f"silent by borough {tiers['top_1pct_silent_by_borough']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--boroughs", help="comma list, e.g. Manhattan,Brooklyn")
    a = ap.parse_args()
    main(a.top, a.boroughs.split(",") if a.boroughs else None)
