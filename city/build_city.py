#!/usr/bin/env -S uv run --with duckdb --with h3 --with shapely python
"""build_city.py: bake NYC open data into the JSON the three.js city renderer loads.

Inputs (nothing is downloaded here; pass paths to the CSV/Parquet you already have in
~/divMap/data/raw/open/ or data/parquet/):

  --buildings  NYC Building Footprints, dataset 5zhs-2jue on data.cityofnewyork.us.
               CSV/Parquet with a WKT geometry column (the_geom, MULTIPOLYGON in lon/lat), or a
               GeoJSON FeatureCollection. Needs an id (bin or doitt_id) and heightroof /
               groundelev (height_roof / ground_elevation in the GeoJSON), both in FEET.
  --trees      2015 Street Tree Census (uvpi-gqnh): tree_id, latitude, longitude, status.
               CSV/Parquet or the Socrata JSON export (a list of records).
  --land       Borough Boundaries (gthc-hcne) polygons: the land mass; everything else is water.
  --roads      Roadbed (i36f-5ih7) polygons.
  --parks      Parks Properties (y6ja-fw4f) polygons.
  --water      Hydrography (pjs3-c3z5) polygons: inland water inside the land mass.
  --bridges    optional: any CSV/Parquet with a WKT LINESTRING/MULTILINESTRING column.
  The polygon layers take GeoJSON or a WKT CSV/Parquet, like --buildings.

Outputs, in --out (default public/city/):

  buildings.json  [{id, h3, footprint: [[x, y], ...], height}]   height in metres, footprint = exterior ring (+elev with --elev)
  trees.json      [{id, x, y, h3}]
  land.json, roads.json, parks.json, water.json   [{id, ring: [[x, y], ...]}]   exterior rings clipped to the bbox
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

The full city look (what the web app draws when the files exist), from the raw GeoJSON downloads:

  R=~/divMap/data/raw
  ./city/build_city.py --buildings $R/buildings.geojson --trees $R/trees.json --land $R/boroughs.geojson \\
      --roads $R/roadbed.geojson --parks $R/parks.geojson --water $R/hydro.geojson \\
      --bbox -74.03,40.688,-73.94,40.76 --out web/public/city

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
BBL_COLS = ("base_bbl", "mappluto_bbl", "bbl")
TREE_ID_COLS = ("tree_id", "id", "objectid")
BRIDGE_ID_COLS = ("id", "objectid", "bridge_id", "name")
POLYGON_ID_COLS = ("objectid", "id", "source_id", "parknum", "borocode", "name", "park_name", "boroname")

# flat polygon layers: name -> (simplify metres, min part area m2)
POLYGON_LAYERS = {"land": (2.0, 200.0), "roads": (1.0, 20.0), "parks": (1.0, 40.0), "water": (2.0, 200.0)}


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


# ---------------------------------------------------------------- polygon sources

def is_geojson(path: Path) -> bool:
    return path.suffix.lower() in (".geojson",) or (path.suffix.lower() == ".json" and _json_is_featurecollection(path))


def _json_is_featurecollection(path: Path) -> bool:
    with path.open() as f:
        head = f.read(200)
    return "FeatureCollection" in head or '"Feature"' in head


def to_float(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def geojson_polygons(path: Path, bbox, pad: float):
    """Yield (properties with lowercase keys, shapely geometry) for every feature whose bounds touch the padded bbox."""
    from shapely.geometry import shape

    with path.open() as f:
        data = json.load(f)
    feats = data.get("features", []) if isinstance(data, dict) else data
    for feat in feats:
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:
            continue
        b = g.bounds
        if b[2] < bbox[0] - pad or b[0] > bbox[2] + pad or b[3] < bbox[1] - pad or b[1] > bbox[3] + pad:
            continue
        yield {k.lower(): v for k, v in (feat.get("properties") or {}).items()}, g


def wkt_polygons(con, path: Path, bbox, pad: float, id_cols, extra_cols, log):
    """Yield (props, shapely geometry) from a CSV/Parquet with a WKT column; props has 'id' plus extra_cols by role."""
    from shapely import wkt as shapely_wkt

    src = source_sql(path)
    cols = columns(con, src)
    geom = pick(cols, GEOM_COLS, "WKT geometry")
    rid = pick(cols, id_cols, "id", required=False)
    id_expr = f"CAST({q(rid)} AS VARCHAR)" if rid else "CAST(row_number() OVER () AS VARCHAR)"
    roles = {role: pick(cols, cands, role, required=False) for role, cands in extra_cols.items()}
    exprs = [f"TRY_CAST({q(c)} AS DOUBLE)" if c else "NULL" for c in roles.values()]
    sql = f"SELECT {id_expr}, {q(geom)}{''.join(', ' + e for e in exprs)} FROM {src} WHERE {q(geom)} IS NOT NULL AND {wkt_prefilter(geom, bbox, pad=pad)}"
    log(f"{path.name}: geom={geom} id={rid} {' '.join(f'{k}={v}' for k, v in roles.items())}")
    cur = con.execute(sql)
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for row in rows:
            try:
                g = shapely_wkt.loads(row[1])
            except Exception:
                continue
            props = {"id": row[0], **{role: row[2 + i] for i, role in enumerate(roles)}}
            yield props, g


def polygon_parts(g):
    from shapely.geometry import MultiPolygon, Polygon

    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    if hasattr(g, "geoms"):  # GeometryCollection from a clip
        return [p for p in g.geoms if isinstance(p, Polygon)]
    return []


def local_ring(proj: Projector, part, simplify_m: float, min_area_m2: float) -> list[list[float]] | None:
    """Project one polygon part to local metres, simplify, return its exterior ring (unclosed) or None."""
    from shapely.geometry import Polygon

    ring = proj.ring(part.exterior.coords)
    if len(ring) < 3:
        return None
    local = Polygon(ring)
    if local.area < min_area_m2:
        return None
    if simplify_m > 0:
        local = local.simplify(simplify_m, preserve_topology=True)
    out = [[round(x, 1), round(y, 1)] for x, y in local.exterior.coords]
    if out and out[0] == out[-1]:
        out.pop()
    return out if len(out) >= 3 else None


# ---------------------------------------------------------------- bakes

def load_addresses(con, pluto: Path, log) -> dict[str, str]:
    """bbl -> address from PLUTO (Parquet/CSV); keys are the integer BBL as a string."""
    src = source_sql(pluto)
    cols = columns(con, src)
    bbl = pick(cols, ("bbl",), "bbl")
    addr = pick(cols, ("address",), "address")
    rows = con.execute(f"SELECT CAST(CAST({q(bbl)} AS BIGINT) AS VARCHAR), {q(addr)} FROM {src} WHERE {q(addr)} IS NOT NULL").fetchall()
    out = {b: a.strip().title() for b, a in rows if b and a}
    log(f"addresses: {len(out)} lots from {pluto.name}")
    return out


def parse_disc(s: str) -> tuple[str, int]:
    cell, k = s.split(",")
    return cell.strip(), int(k)


def disc_cells(cell: str, k: int) -> set[str]:
    """Every r9 cell within k rings of `cell`: the hex-edged disc a district keeps."""
    import h3

    return set(h3.grid_disk(cell, k))


def bake_buildings(con, path: Path, bbox, proj: Projector, res: int, simplify_m: float,
                   min_area_m2: float, height_units: str, limit: int | None, keep_elev: bool, log,
                   addresses: dict[str, str] | None = None, disc: set[str] | None = None) -> list[dict]:
    import h3

    if is_geojson(path):
        log(f"buildings: {path.name} (GeoJSON)")
        rows = geojson_polygons(path, bbox, pad=0.004)
    else:
        rows = wkt_polygons(con, path, bbox, 0.004, BUILDING_ID_COLS, {"height": HEIGHT_COLS, "elev": ELEV_COLS, "bbl": BBL_COLS}, log)

    scale = FT_TO_M if height_units == "feet" else 1.0
    out: list[dict] = []
    n_in = n_bad = n_small = n_addr = n_disc = 0
    for props, g in rows:
        n_in += 1
        if limit and n_in > limit:
            break
        rid = next((str(props[c]) for c in ("id",) + BUILDING_ID_COLS if props.get(c) not in (None, "")), str(n_in))
        addr = None
        if addresses:
            bbl = next((props[c] for c in ("bbl",) + BBL_COLS if props.get(c) not in (None, "")), None)
            if bbl is not None:
                try:
                    addr = addresses.get(str(int(float(bbl))))
                except (TypeError, ValueError):
                    addr = None
        height = to_float(props.get("height")) if "height" in props else next((to_float(props[c]) for c in HEIGHT_COLS if c in props), None)
        elev = to_float(props.get("elev")) if "elev" in props else next((to_float(props[c]) for c in ELEV_COLS if c in props), None)
        parts = polygon_parts(g)
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
            cell = h3.latlng_to_cell(c.y, c.x, res)
            if disc is not None and cell not in disc:
                n_disc += 1
                continue
            footprint = local_ring(proj, part, simplify_m, min_area_m2)
            if footprint is None:
                n_small += 1
                continue
            rec = {
                "id": rid if len(parts) == 1 else f"{rid}.{i + 1}",
                "h3": cell,
                "footprint": footprint,
                "height": h_m,
            }
            if keep_elev and elev is not None:
                rec["elev"] = round(elev * scale, 1)  # opt-in: not in the renderer contract
            if addr:
                rec["addr"] = addr
                n_addr += 1
            out.append(rec)
    log(f"buildings: {n_in} candidates -> {len(out)} kept ({n_small} below {min_area_m2} m2 or degenerate, {n_bad} unparseable, "
        f"{n_disc} outside the disc, {n_addr} with a PLUTO address)")
    return out


def bake_polygons(con, name: str, path: Path, bbox, proj: Projector, log, disc: set[str] | None = None) -> list[dict]:
    """Flat layer: every polygon part clipped to the bbox, as {id, ring} in local metres."""
    import h3
    from shapely.geometry import box

    simplify_m, min_area_m2 = POLYGON_LAYERS[name]
    if is_geojson(path):
        log(f"{name}: {path.name} (GeoJSON)")
        rows = geojson_polygons(path, bbox, pad=0.0)
    else:
        rows = wkt_polygons(con, path, bbox, 0.03, POLYGON_ID_COLS, {}, log)
    clip = box(*bbox)
    out: list[dict] = []
    n_in = 0
    for props, g in rows:
        n_in += 1
        rid = next((str(props[c]) for c in ("id",) + POLYGON_ID_COLS if props.get(c) not in (None, "")), str(n_in))
        try:
            g = g.buffer(0).intersection(clip)
        except Exception:
            continue
        parts = [p for p in polygon_parts(g) if not p.is_empty]
        for i, part in enumerate(parts):
            if disc is not None:
                c = part.centroid
                if h3.latlng_to_cell(c.y, c.x, 9) not in disc:
                    continue
            ring = local_ring(proj, part, simplify_m, min_area_m2)
            if ring is not None:
                out.append({"id": rid if len(parts) == 1 else f"{rid}.{i + 1}", "ring": ring})
    log(f"{name}: {n_in} features -> {len(out)} parts")
    return out


def bake_trees(con, path: Path, bbox, proj: Projector, res: int, limit: int | None, log,
               disc: set[str] | None = None) -> list[dict]:
    import h3

    src = source_sql(path)
    cols = columns(con, src)
    tid = pick(cols, TREE_ID_COLS, "tree id")
    lat = pick(cols, ("latitude", "lat"), "latitude")
    lon = pick(cols, ("longitude", "lon", "lng"), "longitude")
    status = cols.get("status")
    addr = cols.get("address")
    where = (
        f"TRY_CAST({q(lon)} AS DOUBLE) BETWEEN {bbox[0]} AND {bbox[2]} AND "
        f"TRY_CAST({q(lat)} AS DOUBLE) BETWEEN {bbox[1]} AND {bbox[3]}"
    )
    if status:
        where += f" AND lower({q(status)}) = 'alive'"
    addr_expr = f"CAST({q(addr)} AS VARCHAR)" if addr else "NULL"
    sql = f"SELECT CAST({q(tid)} AS VARCHAR), TRY_CAST({q(lat)} AS DOUBLE), TRY_CAST({q(lon)} AS DOUBLE), {addr_expr} FROM {src} WHERE {where}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    log(f"trees: {path.name} id={tid} status_filter={'alive' if status else 'none'} address={'yes' if addr else 'no'}")
    out = []
    for rid, la, lo, a in con.execute(sql).fetchall():
        if la is None or lo is None:
            continue
        cell = h3.latlng_to_cell(la, lo, res)
        if disc is not None and cell not in disc:
            continue
        x, y = proj.xy(lo, la)
        rec = {"id": rid, "x": round(x, 1), "y": round(y, 1), "h3": cell}
        if a:
            rec["addr"] = a.strip().title()  # the street address the tree pit fronts, e.g. "100 Waverly Avenue"
        out.append(rec)
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
    ap.add_argument("--pluto", type=Path, help="PLUTO Parquet/CSV: adds 'addr' to each building by BBL")
    ap.add_argument("--disc", type=parse_disc, default=None,
                    help="H3,K: keep only buildings/roads/trees whose r9 cell is within K rings of cell H3 (a hex-edged disc)")
    for layer in POLYGON_LAYERS:
        ap.add_argument(f"--{layer}", type=Path, help=f"optional polygon file (GeoJSON or WKT) -> {layer}.json")
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

    layer_paths = {layer: getattr(args, layer) for layer in POLYGON_LAYERS}
    if not (args.buildings or args.trees or args.bridges or any(layer_paths.values())):
        ap.error("nothing to do: pass at least one of --buildings, --trees, --bridges, --land, --roads, --parks, --water")
    for p in (args.buildings, args.trees, args.bridges, args.pluto, *layer_paths.values()):
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
    disc = disc_cells(*args.disc) if args.disc else None
    if disc:
        log(f"disc: {len(disc)} r9 cells within {args.disc[1]} rings of {args.disc[0]}")
    if args.buildings:
        addresses = load_addresses(con, args.pluto, log) if args.pluto else None
        b = bake_buildings(con, args.buildings, bbox, proj, args.res, args.simplify, args.min_area, args.height_units, args.limit, args.elev, log,
                           addresses=addresses, disc=disc)
        dump("buildings.json", b)
        counts["buildings"] = len(b)
    if args.trees:
        t = bake_trees(con, args.trees, bbox, proj, args.res, args.limit, log, disc=disc)
        dump("trees.json", t)
        counts["trees"] = len(t)
    if args.bridges:
        br = bake_bridges(con, args.bridges, bbox, proj, args.simplify, log)
        dump("bridges.json", br)
        counts["bridges"] = len(br)
    for layer, path in layer_paths.items():
        if path:
            polys = bake_polygons(con, layer, path, bbox, proj, log, disc=disc)
            dump(f"{layer}.json", polys)
            counts[layer] = len(polys)

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
