#!/usr/bin/env python3
"""Synthetic stand-in for model/out/backtest.json (rolling-origin precision@k of the silent ranking vs a
311-count ranking, 2016-01 -> 2026-07). Deterministic; regenerate with `python3 api/fixtures/make_backtest.py`.
The real file, when the model exists, wins in the /backtest fallback chain."""
import json
import math
import random
from pathlib import Path

random.seed(320)
K = 50
months = []
y, m = 2016, 1
while (y, m) <= (2026, 7):
    months.append(f"{y:04d}-{m:02d}")
    m += 1
    if m > 12:
        y, m = y + 1, 1

series = []
for i, mo in enumerate(months):
    yy, mm = int(mo[:4]), int(mo[5:])
    season = 0.04 * math.sin((mm - 4) / 12 * 2 * math.pi)  # rats peak late summer
    trend = 0.012 * (yy - 2016)  # containerisation + more proactive inspections
    covid = (yy, mm) >= (2020, 4) and (yy, mm) <= (2021, 3)
    silent = 0.31 + season + trend + random.gauss(0, 0.022)
    three11 = 0.19 + 0.6 * season + 0.4 * trend + random.gauss(0, 0.02)
    n_pos = 412 + 90 * math.sin((mm - 4) / 12 * 2 * math.pi) + 6 * (yy - 2016) + random.gauss(0, 28)
    if covid:
        silent -= 0.07 + random.gauss(0, 0.02)  # fewer, noisier inspections
        three11 -= 0.02 + random.gauss(0, 0.015)
        n_pos *= 0.38
    series.append({
        "month": mo,
        "precision_silent": round(max(0.05, min(0.6, silent)), 3),
        "precision_311": round(max(0.05, min(0.6, three11)), 3),
        "n_positives": int(max(60, n_pos)),
    })

ms = sum(s["precision_silent"] for s in series) / len(series)
m3 = sum(s["precision_311"] for s in series) / len(series)
out = {
    "synthetic": True,
    "note": "placeholder numbers until model/out/backtest.json exists; shape is final",
    "window": [months[0], months[-1]],
    "k": K,
    "metric": "precision@k on l60=0 Initial inspections in the following month",
    "series": series,
    "summary": {
        "mean_precision_silent": round(ms, 4),
        "mean_precision_311": round(m3, 4),
        "lift": round(ms / m3, 3),
        "n_months": len(series),
    },
}
Path(__file__).with_name("backtest.json").write_text(json.dumps(out, indent=1) + "\n")
print(f"wrote {len(series)} months, lift {out['summary']['lift']}")
