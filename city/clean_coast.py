#!/usr/bin/env -S uv run --with shapely python
"""
Tidy the citywide coastline: web/public/city/land.json -> a clean outline for the map view.

The baked land layer is the borough boundaries at survey detail: every pier, slip, bulkhead
notch and the seams between boroughs. From 36 km up that reads as a torn paper edge. This pass

  1. dissolves the boroughs into one landmass (no internal seams),
  2. shaves every pier and spit thinner than 2*OPEN_RADIUS (a morphological opening), then fills
     every slip and inlet narrower than 2*CLOSE_RADIUS (a closing), both with round joins; the
     opening goes first so clustered finger piers are removed rather than fused into a block, and
     its radius is the larger one because the rivers (Harlem, Newtown Creek) are narrower than the
     widest piers are long,
  3. drops islets smaller than MIN_AREA,
  4. simplifies to TOLERANCE and rounds the remaining corners (two rounds of Chaikin).

The per-borough land under web/public/city/areas/<id>/ keeps its full detail: that is what you see
when you are inside an area, close enough for piers to matter. Only the citywide layer is smoothed.

    ./city/clean_coast.py                         # in place
    ./city/clean_coast.py --src a.json --out b.json --open 80 --close 55
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
DEFAULT = HERE.parent / "web" / "public" / "city" / "land.json"

OPEN_RADIUS = 80.0  # m: land thinner than twice this vanishes (piers, spits, marsh slivers)
CLOSE_RADIUS = 55.0  # m: water narrower than twice this is filled (slips, basins); the Harlem River (~120 m) stays open
MIN_AREA = 30_000.0  # m2: islets below this are dropped (Roosevelt, Rikers and Governors are 20x this)
TOLERANCE = 10.0  # m: Douglas-Peucker after the morphology
CHAIKIN = 2  # corner-cutting passes after simplification


def chaikin(ring: list[tuple[float, float]], passes: int) -> list[tuple[float, float]]:
    """Closed-ring Chaikin corner cutting: each edge keeps its 1/4 and 3/4 points."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring[:]
    for _ in range(passes):
        out: list[tuple[float, float]] = []
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = out
    return pts


def clean(polys: list[dict], open_r: float, close_r: float, min_area: float, tolerance: float, passes: int) -> list[dict]:
    shapes = [Polygon(p["ring"]).buffer(0) for p in polys if len(p["ring"]) >= 3]
    land = unary_union(shapes)
    # open: shave piers and spits; close: fill slips and basins
    land = land.buffer(-open_r, join_style="round").buffer(open_r, join_style="round")
    land = land.buffer(close_r, join_style="round").buffer(-close_r, join_style="round")
    parts = list(land.geoms) if land.geom_type == "MultiPolygon" else [land]
    parts = [g for g in parts if g.area >= min_area]
    parts.sort(key=lambda g: -g.area)
    out: list[dict] = []
    for i, g in enumerate(parts):
        g = g.simplify(tolerance, preserve_topology=True)
        ring = chaikin(list(g.exterior.coords), passes)
        out.append({"id": f"c.{i + 1}", "ring": [[round(x, 1), round(y, 1)] for x, y in ring]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT, help=f"baked land layer (default {DEFAULT})")
    ap.add_argument("--out", type=Path, default=None, help="output path (default: overwrite --src)")
    ap.add_argument("--open", type=float, default=OPEN_RADIUS, help=f"opening radius in metres, shaves land (default {OPEN_RADIUS})")
    ap.add_argument("--close", type=float, default=CLOSE_RADIUS, help=f"closing radius in metres, fills water (default {CLOSE_RADIUS})")
    ap.add_argument("--min-area", type=float, default=MIN_AREA, help=f"drop parts under this many m2 (default {MIN_AREA})")
    ap.add_argument("--tolerance", type=float, default=TOLERANCE, help=f"simplify tolerance in metres (default {TOLERANCE})")
    ap.add_argument("--chaikin", type=int, default=CHAIKIN, help=f"corner-cutting passes (default {CHAIKIN})")
    args = ap.parse_args(argv)

    polys = json.loads(args.src.read_text())
    before = sum(len(p["ring"]) for p in polys)
    out = clean(polys, args.open, args.close, args.min_area, args.tolerance, args.chaikin)
    after = sum(len(p["ring"]) for p in out)
    dest = args.out or args.src
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{args.src.name}: {len(polys)} parts / {before} vertices -> {len(out)} parts / {after} vertices -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
