#!/usr/bin/env -S uv run --with duckdb --with h3 --with shapely python
"""build_city.py: bake NYC open data into the JSON the three.js city renderer loads.

Inputs (nothing is downloaded here; pass paths to the CSV/Parquet you already have in
~/divMap/data/raw/open/ or data/parquet/):

  --buildings  NYC Building Footprints, dataset 5zhs-2jue on data.cityofnewyork.us.
               Needs a WKT geometry column (the_geom, MULTIPOLYGON in lon/lat), an id
               (bin or doitt_id) and heightroof / groundelev, both in FEET in the source.
  --trees      2015 Street Tree Census (uvpi-gqnh): tree_id, latitude, longitude, status.
  --bridges    optional: any CSV/Parquet with a WKT LINESTRING/MULTILINESTRING column.

Outputs, in --out (default public/city/):

  buildings.json  [{id, h3, footprint: [[x, y], ...], height}]   height in metres, footprint = exterior ring (+elev with --elev)
  trees.json      [{id, x, y, h3}]
  bridges.json    [{id, path: [[x, y], ...]}]                    only when --bridges is given
  meta.json       {centre, bbox, counts, h3_res, crs, generated_at}

Coordinates are local metres: an equirectangular projection around --centre (default the
bbox centre), x east, y north, rounded to 0.1 m. The renderer treats them as three.js x / -z.
The H3 cell is the r9 cell of the footprint centroid, which is how a building gets its tint
from the /cells row. Polygon holes (courtyards) are dropped; multipolygon parts become
separate entries with ids like 1001234.2.

Typical run (Lower Manhattan, the default bbox):

  ./city/build_city.py --buildings data/raw/open/building_footprints.csv \\
                       --trees data/raw/open/street_trees_2015.csv --out public/city

--limit N is for smoke tests. DuckDB does the bbox prefilter on the raw text so the 1.1M-row
footprints file never fully materialises; shapely does the exact clip, projection and simplify.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

# Lower Manhattan south of 14th St: min_lon, min_lat, max_lon, max_lat
DEFAULT_BBOX = (-74.0250, 40.6980, -73.9680, 40.7420)
M_PER_DEG = 111_320.0  # metres per degree of latitude
FT_TO_M = 0.3048

GEOM_COLS = ("the_geom", "geometry", "geom", "wkt", "multipolygon", "shape")
BUILDING_ID_COLS = ("bin", "doitt_id", "globalid", "objectid", "id")
HEIGHT_COLS = ("heightroof", "height_roof", "height")
ELEV_COLS = ("groundelev", "ground_elev", "elevation")
TREE_ID_COLS = ("tree_id", "id", "objectid")
BRIDGE_ID_COLS = ("id", "objectid", "bridge_id", "name")


# ---------------------------------------------------------------- geometry helpers

class Projector:
    """Equirectangular, metres, x east / y north, around a centre lat/lon."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = M_PER_DEG * math.cos(math.radians(lat0))
        self.ky = M_PER_DEG

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def ring(self, coords) -> list[list[float]]:
        out = []
        for lon, lat, *_ in coords:
            x, y = self.xy(lon, lat)
            out.append([round(x, 1), round(y, 1)])
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out


def in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = [float(v) for v in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox is min_lon,min_lat,max_lon,max_lat")
    return parts[0], parts[1], parts[2], parts[3]


def parse_centre(s: str) -> tuple[float, float]:
    lat, lon = (float(v) for v in s.split(","))
    return lat, lon


# ---------------------------------------------------------------- duckdb helpers

def source_sql(path: Path) -> str:
    p = str(path).replace("'", "''")
    suf = path.suffix.lower()
    if suf == ".parquet":
        return f"read_parquet('{p}')"
    if suf in (".json", ".jsonl", ".ndjson"):
        return f"read_json_auto('{p}')"
    return f"read_csv_auto('{p}', header=true, sample_size=-1)"


def columns(con, src: str) -> dict[str, str]:
    """lowercase name -> real name"""
    rows = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
    return {r[0].lower(): r[0] for r in rows}


def pick(cols: dict[str, str], candidates, what: str, required: bool = True) -> str | None:
    for c in candidates:
        if c in cols:
            return cols[c]
    if required:
        raise SystemExit(f"could not find a {what} column; have: {', '.join(cols.values())}")
    return None


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


FIRST_LON = r"TRY_CAST(regexp_extract({g}, '(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)', 1) AS DOUBLE)"
FIRST_LAT = r"TRY_CAST(regexp_extract({g}, '(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)', 2) AS DOUBLE)"


def wkt_prefilter(geom_col: str, bbox, pad: float) -> str:
    """Cheap SQL clip on the first vertex of the WKT, padded so edge cases survive to shapely."""
    g = q(geom_col)
    return (
        f"{FIRST_LON.format(g=g)} BETWEEN {bbox[0] - pad} AND {bbox[2] + pad} AND "
        f"{FIRST_LAT.format(g=g)} BETWEEN {bbox[1] - pad} AND {bbox[3] + pad}"
    )


# ---------------------------------------------------------------- bakes

def bake_buildings(con, path: Path, bbox, proj: Projector, res: int, simplify_m: float,
                   min_area_m2: float, height_units: str, limit: int | None, keep_elev: bool, log) -> list[dict]:
    import h3
    from shapely import wkt as shapely_wkt
    from shapely.geometry import MultiPolygon, Polygon

    src = source_sql(path)
    cols = columns(con, src)
    geom = pick(cols, GEOM_COLS, "WKT geometry")
    bid = pick(cols, BUILDING_ID_COLS, "building id")
    hcol = pick(cols, HEIGHT_COLS, "heightroof", required=False)
    ecol = pick(cols, ELEV_COLS, "groundelev", required=False)
    h_expr = f"TRY_CAST({q(hcol)} AS DOUBLE)" if hcol else "NULL"
    e_expr = f"TRY_CAST({q(ecol)} AS DOUBLE)" if ecol else "NULL"
    sql = (
        f"SELECT CAST({q(bid)} AS VARCHAR), {q(geom)}, {h_expr}, {e_expr} FROM {src} "
        f"WHERE {q(geom)} IS NOT NULL AND {wkt_prefilter(geom, bbox, pad=0.004)}"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    log(f"buildings: {path.name} geom={geom} id={bid} height={hcol} elev={ecol}")

    scale = FT_TO_M if height_units == "feet" else 1.0
    out: list[dict] = []
    n_in = n_bad = n_small = 0
    cur = con.execute(sql)
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, wkt, height, elev in rows:
            n_in += 1
            try:
                g = shapely_wkt.loads(wkt)
            except Exception:
                n_bad += 1
                continue
            parts = list(g.geoms) if isinstance(g, MultiPolygon) else [g] if isinstance(g, Polygon) else []
            if not parts:
                n_bad += 1
                continue
            h_m = round((height or 0.0) * scale, 1)
            if h_m <= 0:
                h_m = 3.0  # source has nulls/zeros; give it one storey rather than a hole
            for i, part in enumerate(parts):
                c = part.centroid
                if not in_bbox(c.x, c.y, bbox):
                    continue
                ring = proj.ring(part.exterior.coords)
                if len(ring) < 3:
                    n_bad += 1
                    continue
                local = Polygon(ring)
                if local.area < min_area_m2:
                    n_small += 1
                    continue
                if simplify_m > 0:
                    local = local.simplify(simplify_m, preserve_topology=True)
                footprint = [[round(x, 1), round(y, 1)] for x, y in local.exterior.coords]
                if footprint[0] == footprint[-1]:
                    footprint.pop()
                if len(footprint) < 3:
                    n_bad += 1
                    continue
                rec = {
                    "id": rid if len(parts) == 1 else f"{rid}.{i + 1}",
                    "h3": h3.latlng_to_cell(c.y, c.x, res),
                    "footprint": footprint,
                    "height": h_m,
                }
                if keep_elev and elev is not None:
                    rec["elev"] = round(elev * scale, 1)  # opt-in: not in the renderer contract
                out.append(rec)
    log(f"buildings: {n_in} candidates -> {len(out)} kept ({n_small} below {min_area_m2} m2, {n_bad} unparseable)")
    return out


def bake_trees(con, path: Path, bbox, proj: Projector, res: int, limit: int | None, log) -> list[dict]:
    import h3

    src = source_sql(path)
    cols = columns(con, src)
    tid = pick(cols, TREE_ID_COLS, "tree id")
    lat = pick(cols, ("latitude", "lat"), "latitude")
    lon = pick(cols, ("longitude", "lon", "lng"), "longitude")
    status = cols.get("status")
    where = (
        f"TRY_CAST({q(lon)} AS DOUBLE) BETWEEN {bbox[0]} AND {bbox[2]} AND "
        f"TRY_CAST({q(lat)} AS DOUBLE) BETWEEN {bbox[1]} AND {bbox[3]}"
    )
    if status:
        where += f" AND lower({q(status)}) = 'alive'"
    sql = f"SELECT CAST({q(tid)} AS VARCHAR), TRY_CAST({q(lat)} AS DOUBLE), TRY_CAST({q(lon)} AS DOUBLE) FROM {src} WHERE {where}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    log(f"trees: {path.name} id={tid} status_filter={'alive' if status else 'none'}")
    out = []
    for rid, la, lo in con.execute(sql).fetchall():
        if la is None or lo is None:
            continue
        x, y = proj.xy(lo, la)
        out.append({"id": rid, "x": round(x, 1), "y": round(y, 1), "h3": h3.latlng_to_cell(la, lo, res)})
    log(f"trees: {len(out)} kept")
    return out


def bake_bridges(con, path: Path, bbox, proj: Projector, simplify_m: float, log) -> list[dict]:
    from shapely import wkt as shapely_wkt
    from shapely.geometry import LineString, MultiLineString, box

    src = source_sql(path)
    cols = columns(con, src)
    geom = pick(cols, GEOM_COLS, "WKT geometry")
    bid = pick(cols, BRIDGE_ID_COLS, "bridge id", required=False)
    id_expr = f"CAST({q(bid)} AS VARCHAR)" if bid else "CAST(row_number() OVER () AS VARCHAR)"
    sql = f"SELECT {id_expr}, {q(geom)} FROM {src} WHERE {q(geom)} IS NOT NULL AND {wkt_prefilter(geom, bbox, pad=0.03)}"
    clip = box(*bbox)
    out = []
    for rid, wkt in con.execute(sql).fetchall():
        try:
            g = shapely_wkt.loads(wkt).intersection(clip)
        except Exception:
            continue
        lines = list(g.geoms) if isinstance(g, MultiLineString) else [g] if isinstance(g, LineString) else []
        for i, line in enumerate(lines):
            if line.is_empty:
                continue
            path_xy = proj.ring(line.coords) if simplify_m <= 0 else proj.ring(line.simplify(simplify_m / M_PER_DEG).coords)
            if len(path_xy) >= 2:
                out.append({"id": rid if len(lines) == 1 else f"{rid}.{i + 1}", "path": path_xy})
    log(f"bridges: {len(out)} segments")
    return out


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--buildings", type=Path, help="Building Footprints CSV/Parquet (5zhs-2jue)")
    ap.add_argument("--trees", type=Path, help="2015 Street Tree Census CSV/Parquet (uvpi-gqnh)")
    ap.add_argument("--bridges", type=Path, help="optional WKT line file for bridges")
    ap.add_argument("--out", type=Path, default=Path("public/city"), help="output directory (default public/city)")
    ap.add_argument("--bbox", type=parse_bbox, default=DEFAULT_BBOX,
                    help="min_lon,min_lat,max_lon,max_lat (default Lower Manhattan south of 14th St)")
    ap.add_argument("--centre", type=parse_centre, default=None, help="lat,lon origin of the local metre frame (default bbox centre)")
    ap.add_argument("--res", type=int, default=9, help="H3 resolution for the cell key (default 9)")
    ap.add_argument("--simplify", type=float, default=0.5, help="Douglas-Peucker tolerance in metres, 0 to disable (default 0.5)")
    ap.add_argument("--min-area", type=float, default=8.0, help="drop footprint parts smaller than this many m2 (default 8)")
    ap.add_argument("--height-units", choices=("feet", "metres"), default="feet", help="units of heightroof/groundelev in the source (default feet)")
    ap.add_argument("--elev", action="store_true", help="also write groundelev (metres) as 'elev' on each building; off by default, the renderer sits everything at z=0")
    ap.add_argument("--limit", type=int, default=None, help="cap rows per source, for smoke tests")
    ap.add_argument("--indent", type=int, default=None, help="pretty-print JSON (default compact)")
    args = ap.parse_args(argv)

    if not (args.buildings or args.trees or args.bridges):
        ap.error("nothing to do: pass at least one of --buildings, --trees, --bridges")
    for p in (args.buildings, args.trees, args.bridges):
        if p and not p.exists():
            ap.error(f"{p} does not exist (this script never downloads; see data/bake_open_data.py)")

    import duckdb

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    bbox = args.bbox
    centre = args.centre or ((bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2)
    proj = Projector(*centre)
    con = duckdb.connect()
    args.out.mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj) -> Path:
        path = args.out / name
        with path.open("w") as f:
            json.dump(obj, f, separators=(",", ":") if args.indent is None else None, indent=args.indent)
        log(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
        return path

    counts: dict[str, int] = {}
    if args.buildings:
        b = bake_buildings(con, args.buildings, bbox, proj, args.res, args.simplify, args.min_area, args.height_units, args.limit, args.elev, log)
        dump("buildings.json", b)
        counts["buildings"] = len(b)
    if args.trees:
        t = bake_trees(con, args.trees, bbox, proj, args.res, args.limit, log)
        dump("trees.json", t)
        counts["trees"] = len(t)
    if args.bridges:
        br = bake_bridges(con, args.bridges, bbox, proj, args.simplify, log)
        dump("bridges.json", br)
        counts["bridges"] = len(br)

    meta_path = args.out / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update(
        {
            "centre": {"lat": centre[0], "lon": centre[1]},
            "bbox": {"min_lon": bbox[0], "min_lat": bbox[1], "max_lon": bbox[2], "max_lat": bbox[3]},
            "crs": "local equirectangular, metres, x east, y north, origin at centre",
            "h3_res": args.res,
            "height_units": "m",
            "counts": {**meta.get("counts", {}), **counts},
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
    )
    dump("meta.json", meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
