#!/usr/bin/env -S uv run --with h3 python
"""make_fixture.py: synthetic fixtures for the three frozen endpoints.

Writes, next to this script unless --out says otherwise:

  cells.fixture.json   GET /cells?month=2026-08   one row per H3 r9 cell in Lower Manhattan
  plan.fixture.json    GET /plan                  k=8 node placements snapped to (fake) tree pits
  queue.fixture.json   GET /queue                 3 detector events from node demo-01

Everything in here is made up. The numbers are shaped so the map tells the story the real
model should tell: score_b (P(active | inspected)) is high around a few "silent" hotspots in
the LES / Chinatown / East Village, score_a (predicted complaints per month) is inflated in the
wealthier community districts, so silence = pct_b - pct_a lights up the blocks that have rats
but no callers. Seed 42, so the file is byte-stable apart from generated_at.

Run:  ./city/make_fixture.py            (uv pulls h3 on first run)
      ./city/make_fixture.py --out public/city   to feed the renderer directly

Stdlib + h3 only. No pandas, no numpy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

import h3

MONTH = "2026-08"
RES = 9
SEED = 42
K_NODES = 8
DEMO_H3 = "892a100d2c3ffff"  # the cell the stage node reports into (DEMO_H3 in vision/pi/detect.py)
NODE_ID = "demo-01"
FW = "0.1.0"

# Lower Manhattan south of 14th St, (lat, lon), clockwise from 14th St & the Hudson.
LOWER_MANHATTAN = [
    (40.7400, -74.0115),  # 14th St & Hudson River
    (40.7345, -73.9715),  # 14th St & East River
    (40.7180, -73.9740),  # Houston St & East River
    (40.7100, -73.9775),  # Corlears Hook
    (40.7055, -73.9960),  # foot of the Brooklyn Bridge
    (40.6995, -74.0110),  # South Ferry
    (40.7020, -74.0185),  # the Battery, west side
    (40.7160, -74.0200),  # Battery Park City, north
    (40.7300, -74.0135),  # West Village on the Hudson
]

# Silent hotspots: (lat, lon, radius_m, bump on P(active)). Parks and old tenement blocks where
# proactive inspections keep finding rats but 311 stays quiet.
HOTSPOTS = [
    (40.7145, -73.9885, 380, 0.30),  # Seward Park / Grand St, LES
    (40.7265, -73.9820, 320, 0.26),  # Tompkins Square / Avenue B
    (40.7148, -73.9998, 260, 0.28),  # Columbus Park / Chinatown
    (40.7105, -73.9935, 260, 0.22),  # Two Bridges
    (40.7498, -73.9900, 220, 0.30),  # the demo cell (27th & 6th) so it reads as a find on stage
]

# Complaint propensity by community district: who calls 311. Rough, and deliberately unfair.
CD_COMPLAINT_MULT = {"101": 1.6, "102": 1.5, "103": 0.7, "104": 1.4, "105": 1.3, "106": 1.4}

# SHAP features. Sign says how the feature's contribution moves with the cell's "ratness".
FEATURE_PROFILE = {
    "restaurant_vermin_12mo": +0.90,
    "dob_nb_permits_6mo": +0.70,
    "litter_baskets_100m": +0.60,
    "park_adjacent": +0.60,
    "catch_basins_100m": +0.50,
    "pluto_bldg_age": +0.50,
    "tree_pits": +0.40,
    "lomod_pct": +0.30,
    "temp_mean": +0.20,
}

RMZ_NAME = "Chinatown/East Village/LES"
RMZ_CENTRE = (40.7170, -73.9880)
RMZ_CELLS = 12  # "a handful"
DEMO_QUIET = 0.45  # complaint suppression on the demo cell so it reads high-B / low-A on stage


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = p2 - p1
    dlmb = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def community_district(lat: float, lon: float) -> str:
    """Rough CD from lat/lon. Canal St ~40.718, Bowery ~-73.993, 14th St ~40.7345..40.740."""
    if lat < 40.7180:
        return "103" if (lon > -73.9990 and lat > 40.7080) else "101"  # Chinatown / Two Bridges are CD3
    if lat < 40.7400 - (lon + 74.0115) * 0.1375:  # the 14th St line, sloping down to the east
        return "103" if lon > -73.9930 else "102"
    if lon < -73.9960:
        return "104"
    if lon > -73.9800:
        return "106"
    return "105"


def percentile_rank(values: list[float]) -> list[float]:
    """0..100, average rank on ties, 100 = highest. Proper, not min-max scaling."""
    n = len(values)
    if n < 2:
        return [50.0 for _ in values]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return [round(100.0 * r / (n - 1), 1) for r in ranks]


def beta_ci(rng: random.Random, alpha: float, beta: float, draws: int = 4000) -> list[float]:
    """95% interval of Beta(alpha, beta) by Monte Carlo. Stdlib has no beta quantile."""
    xs = sorted(rng.betavariate(alpha, beta) for _ in range(draws))
    return [round(xs[int(0.025 * draws)], 3), round(xs[int(0.975 * draws)], 3)]


def binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(1 for _ in range(n) if rng.random() < p)


def build_cells(rng: random.Random) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    poly = h3.LatLngPoly(LOWER_MANHATTAN)
    cells = sorted(h3.h3shape_to_cells(poly, RES))
    if DEMO_H3 not in set(cells):
        cells.append(DEMO_H3)
        lat, lon = h3.cell_to_latlng(DEMO_H3)
        notes.append(
            f"demo cell {DEMO_H3} ({lat:.4f}, {lon:.4f}) is outside the Lower Manhattan polygon; "
            "appended anyway so the stage node has a cell to report into"
        )

    centres = {c: h3.cell_to_latlng(c) for c in cells}
    rmz_set = set(sorted(cells, key=lambda c: haversine_m(centres[c], RMZ_CENTRE))[:RMZ_CELLS])

    # 1. the truth: P(active | inspected) = a smooth baseline + the silent hotspots
    true_b: dict[str, float] = {}
    base_b: dict[str, float] = {}
    for c in cells:
        lat, lon = centres[c]
        noise = math.exp(rng.gauss(0, 0.22))
        base = (0.10 + 0.015 * ((lat - 40.700) / 0.04)) * noise  # slight northward drift, tenements over towers
        hot = 0.0
        for hlat, hlon, radius, bump in HOTSPOTS:
            d = haversine_m((lat, lon), (hlat, hlon))
            hot += bump * math.exp(-(d / radius) ** 2)
        base_b[c] = base
        true_b[c] = min(0.85, max(0.03, base + hot * noise))

    # 2. what the city sees: complaints follow the baseline rat rate, barely notice the hotspots
    #    (that is what makes them silent), then get scaled by who calls 311 in that CD.
    score_a: dict[str, float] = {}
    for c in cells:
        cd = community_district(*centres[c])
        seen = base_b[c] + 0.2 * (true_b[c] - base_b[c])
        a = (0.35 + 5.5 * seen) * CD_COMPLAINT_MULT[cd] * math.exp(rng.gauss(0, 0.35))
        if c == DEMO_H3:
            a *= DEMO_QUIET  # the stage cell is the story's silent block: rats, no callers
        score_a[c] = round(a, 3)

    b_vals = [true_b[c] for c in cells]
    mean_b = sum(b_vals) / len(b_vals)
    sd_b = math.sqrt(sum((v - mean_b) ** 2 for v in b_vals) / len(b_vals)) or 1.0
    pct_a = dict(zip(cells, percentile_rank([score_a[c] for c in cells])))
    pct_b = dict(zip(cells, percentile_rank(b_vals)))

    # 3. sensor events: the demo cell and two others
    others = [c for c in cells if c != DEMO_H3 and true_b[c] > mean_b + sd_b]
    event_cells = {DEMO_H3: 3}
    for c in rng.sample(others, k=min(2, len(others))):
        event_cells[c] = 1

    rows = []
    for c in cells:
        lat, lon = centres[c]
        cd = community_district(lat, lon)
        b = true_b[c]

        # Beta-Binomial posterior: model B's score is the prior (strength m), inspections and
        # node events are the evidence. This is what /event updates on the live server.
        m = 6.0
        n_insp = min(30, int(rng.expovariate(1 / 3.5)))
        if c in rmz_set:
            n_insp += rng.randint(6, 12)  # RMZ = proactive indexed inspections
        hits = binomial(rng, n_insp, b)
        n_events = event_cells.get(c, 0)
        alpha = round(b * m + hits + n_events, 3)
        beta = round((1 - b) * m + (n_insp - hits), 3)

        z = (b - mean_b) / sd_b
        shap = [(f, round(w * z * 0.09 + rng.gauss(0, 0.03), 3)) for f, w in FEATURE_PROFILE.items()]
        shap.sort(key=lambda t: -abs(t[1]))

        last_event_at = None
        if n_events:
            last_event_at = (
                dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
                + dt.timedelta(days=rng.randint(0, 30), hours=rng.randint(21, 23) % 24, minutes=rng.randint(0, 59))
            ).isoformat(timespec="seconds").replace("+00:00", "Z")

        rows.append(
            {
                "h3": c,
                "score_a": score_a[c],
                "score_b": round(b, 3),
                "pct_a": pct_a[c],
                "pct_b": pct_b[c],
                "silence": round(pct_b[c] - pct_a[c], 1),
                "ci_b": beta_ci(rng, alpha, beta),
                "posterior": {"alpha": alpha, "beta": beta, "n_events": n_events},
                "reasons": [{"feature": f, "shap": s} for f, s in shap[:3]],
                "cd": cd,
                "rmz": RMZ_NAME if c in rmz_set else None,
                "n_inspections": n_insp,
                "last_event_at": last_event_at,
            }
        )
    return rows, notes


def build_plan(rng: random.Random, rows: list[dict]) -> dict:
    """Greedy: highest expected gain first, 100 m exclusion, demo cell pinned to rank 1."""
    by_h3 = {r["h3"]: r for r in rows}

    def gain(r: dict) -> float:
        a, b = r["posterior"]["alpha"], r["posterior"]["beta"]
        var = a * b / ((a + b) ** 2 * (a + b + 1))  # posterior variance
        return var * r["score_b"] * (1 + max(0.0, r["silence"]) / 100)

    order = [DEMO_H3] + sorted((r["h3"] for r in rows if r["h3"] != DEMO_H3), key=lambda c: -gain(by_h3[c]))
    chosen: list[tuple[str, float, float]] = []
    for c in order:
        lat, lon = h3.cell_to_latlng(c)
        # snap to a "tree pit": jitter the centre by up to ~60 m
        lat += rng.uniform(-0.00055, 0.00055)
        lon += rng.uniform(-0.0007, 0.0007)
        if any(haversine_m((lat, lon), (plat, plon)) < 100 for _, plat, plon in chosen):
            continue
        chosen.append((c, lat, lon))
        if len(chosen) == K_NODES:
            break

    nodes = []
    for rank, (c, lat, lon) in enumerate(chosen, start=1):
        r = by_h3[c]
        lo, hi = r["ci_b"]
        top = r["reasons"][0]["feature"]
        nodes.append(
            {
                "rank": rank,
                "h3": c,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "tree_id": str(rng.randint(100000, 720000)),
                "expected_gain": round(gain(r) * 100, 4),
                "silence": r["silence"],
                "reason": f"P(active) {r['score_b']:.2f} [{lo:.2f}-{hi:.2f}], silence {r['silence']:+.0f}; top driver {top}",
            }
        )
    return {"month": MONTH, "k": K_NODES, "nodes": nodes}


def build_queue() -> dict:
    """Three events from the stage node. ts is when the Pi fired, received_at when the API got it."""
    base = dt.datetime(2026, 9, 26, 14, 2, 11, tzinfo=dt.timezone.utc)
    specs = [(0, 0.91, [212, 301, 138, 74]), (47, 0.87, [188, 288, 151, 80]), (131, 0.94, [240, 310, 129, 69])]
    events = []
    for offset_s, conf, bbox in specs:
        ts = base + dt.timedelta(seconds=offset_s)
        rx = ts + dt.timedelta(milliseconds=340)
        events.append(
            {
                "node_id": NODE_ID,
                "h3": DEMO_H3,
                "ts": ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "class": "rat",
                "conf": conf,
                "n_hits": 3,
                "bbox": bbox,  # [x, y, w, h] in the 640x480 detector frame
                "crop_b64": "",  # empty in the fixture; the live node sends a JPEG of the rat crop
                "fw": FW,
                "received_at": rx.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
        )
    return {"events": events}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent, help="output directory")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rows, notes = build_cells(rng)
    cells_doc = {"month": MONTH, "generated_at": iso_now(), "cells": rows}
    plan_doc = build_plan(rng, rows)
    queue_doc = build_queue()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, doc in (("cells.fixture.json", cells_doc), ("plan.fixture.json", plan_doc), ("queue.fixture.json", queue_doc)):
        path = args.out / name
        path.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"wrote {path} ({path.stat().st_size // 1024} KB)")

    silent = sorted(rows, key=lambda r: -r["silence"])[:5]
    print(f"{len(rows)} cells, {sum(1 for r in rows if r['rmz'])} in RMZ, month {MONTH}")
    print("top silence: " + ", ".join(f"{r['h3']} ({r['silence']:+.0f}, cd {r['cd']})" for r in silent))
    for n in notes:
        print("note:", n, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
