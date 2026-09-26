#!/usr/bin/env -S uv run --with duckdb --with h3 --with shapely --with ijson python
"""make_tiles.py: bake the whole city into H3 r7 tiles the web app streams around the camera.

Inputs (citywide exports, see the curl lines in city/README.md):
  $RAW/city/buildings_citywide.geojson   5zhs-2jue, 1.08M footprints (streamed with ijson, never fully in memory)
  $RAW/city/roadbed_citywide.geojson     i36f-5ih7
  $RAW/city/trees_citywide.json          uvpi-gqnh (tree_id, latitude, longitude, address, status)
  $RAW/boroughs.geojson                  gthc-hcne, for the area outlines
  $PLUTO                                 pluto.parquet, for building addresses

Outputs, in web/public/city/:
  tiles/<r7>.json    {"buildings": [...], "roads": [...], "trees": [...]}  same record shapes as build_city.py
  tiles.json         {"res": 7, "tiles": {"<r7>": {"b": n, "r": n, "t": n}}}   counts, so the app can budget what it loads
  areas.json         {"centre", "areas": [{"id", "name", "lat", "lon", "outline": [[x, y], ...]}]}

Everything shares the projection centre in city/areas.json, the same one the citywide land/parks/water bake used.
About 5 minutes and ~250 MB of tiles for the whole city.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = Path(os.environ.get("RAW", "~/divMap/data/raw")).expanduser()
PLUTO = Path(os.environ.get("PLUTO", "~/divMap/data/parquet/pluto.parquet")).expanduser()
OUT = ROOT / "web" / "public" / "city"
TILE_RES = 7
COMPACT = {"separators": (",", ":")}

sys.path.insert(0, str(HERE))
import build_city  # noqa: E402


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def stream_features(path: Path):
    """Yield (properties, geometry-dict) from a FeatureCollection without loading the file."""
    import ijson

    with path.open("rb") as f:
        for feat in ijson.items(f, "features.item", use_float=True):
            geom = feat.get("geometry")
            if geom:
                yield {k.lower(): v for k, v in (feat.get("properties") or {}).items()}, geom


def bake_buildings(tiles: dict, proj: build_city.Projector, addresses: dict[str, str]) -> int:
    import h3
    from shapely.geometry import shape

    n = 0
    n_addr = 0
    for props, geom in stream_features(RAW / "city" / "buildings_citywide.geojson"):
        try:
            g = shape(geom)
        except Exception:
            continue
        rid = next((str(props[c]) for c in build_city.BUILDING_ID_COLS if props.get(c) not in (None, "")), None) or str(n)
        height = next((build_city.to_float(props[c]) for c in build_city.HEIGHT_COLS if c in props), None)
        h_m = round((height or 0.0) * build_city.FT_TO_M, 1)
        if h_m <= 0:
            h_m = 3.0
        addr = None
        bbl = next((props[c] for c in build_city.BBL_COLS if props.get(c) not in (None, "")), None)
        if bbl is not None:
            try:
                addr = addresses.get(str(int(float(bbl))))
            except (TypeError, ValueError):
                addr = None
        parts = build_city.polygon_parts(g)
        for i, part in enumerate(parts):
            c = part.centroid
            footprint = build_city.local_ring(proj, part, 0.5, 8.0)
            if footprint is None:
                continue
            cell = h3.latlng_to_cell(c.y, c.x, 9)
            rec = {"id": rid if len(parts) == 1 else f"{rid}.{i + 1}", "h3": cell, "footprint": footprint, "height": h_m}
            if addr:
                rec["addr"] = addr
                n_addr += 1
            tiles[h3.cell_to_parent(cell, TILE_RES)]["b"].append(json.dumps(rec, **COMPACT))
            n += 1
        if n % 100_000 < len(parts):
            log(f"  buildings {n:,}")
    log(f"buildings: {n:,} parts, {n_addr:,} with an address")
    return n


def bake_roads(tiles: dict, proj: build_city.Projector) -> int:
    import h3
    from shapely.geometry import shape

    n = 0
    for props, geom in stream_features(RAW / "city" / "roadbed_citywide.geojson"):
        try:
            g = shape(geom)
        except Exception:
            continue
        rid = str(props.get("source_id") or props.get("objectid") or n)
        parts = build_city.polygon_parts(g)
        for i, part in enumerate(parts):
            ring = build_city.local_ring(proj, part, 1.0, 20.0)
            if ring is None:
                continue
            c = part.centroid
            tile = h3.latlng_to_cell(c.y, c.x, TILE_RES)
            tiles[tile]["r"].append(json.dumps({"id": rid if len(parts) == 1 else f"{rid}.{i + 1}", "ring": ring}, **COMPACT))
            n += 1
    log(f"roads: {n:,} parts")
    return n


def bake_trees(tiles: dict, proj: build_city.Projector) -> int:
    import h3

    with (RAW / "city" / "trees_citywide.json").open() as f:
        rows = json.load(f)
    n = 0
    for t in rows:
        try:
            la = float(t["latitude"])
            lo = float(t["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if str(t.get("status", "Alive")).lower() != "alive":
            continue
        x, y = proj.xy(lo, la)
        rec = {"id": str(t.get("tree_id", n)), "x": round(x, 1), "y": round(y, 1), "h3": h3.latlng_to_cell(la, lo, 9)}
        a = t.get("address")
        if a:
            rec["addr"] = str(a).strip().title()
        tiles[h3.latlng_to_cell(la, lo, TILE_RES)]["t"].append(json.dumps(rec, **COMPACT))
        n += 1
    log(f"trees: {n:,}")
    return n


def area_outlines(proj: build_city.Projector) -> dict[str, list[list[float]]]:
    """borocode -> the largest part of the borough polygon, simplified, in local metres."""
    from shapely.geometry import shape

    out = {}
    with (RAW / "boroughs.geojson").open() as f:
        for feat in json.load(f)["features"]:
            props = {k.lower(): v for k, v in feat["properties"].items()}
            g = shape(feat["geometry"])
            parts = build_city.polygon_parts(g)
            if not parts:
                continue
            biggest = max(parts, key=lambda p: p.area)
            ring = build_city.local_ring(proj, biggest, 25.0, 0.0)
            if ring:
                out[str(props.get("borocode"))] = ring
    return out


def main() -> int:
    import duckdb

    manifest = json.loads((HERE / "areas.json").read_text())
    centre = (manifest["centre"]["lat"], manifest["centre"]["lon"])
    proj = build_city.Projector(*centre)
    for name in ("city/buildings_citywide.geojson", "city/roadbed_citywide.geojson", "city/trees_citywide.json", "boroughs.geojson"):
        if not (RAW / name).is_file():
            log(f"missing {RAW / name}")
            return 1
    con = duckdb.connect()
    addresses = build_city.load_addresses(con, PLUTO, log) if PLUTO.is_file() else {}

    tiles: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"b": [], "r": [], "t": []})
    bake_buildings(tiles, proj, addresses)
    bake_roads(tiles, proj)
    bake_trees(tiles, proj)

    tile_dir = OUT / "tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)
    for old in tile_dir.glob("*.json"):
        old.unlink()
    counts = {}
    total = 0
    for tile, parts in tiles.items():
        body = '{"buildings":[' + ",".join(parts["b"]) + '],"roads":[' + ",".join(parts["r"]) + '],"trees":[' + ",".join(parts["t"]) + "]}"
        (tile_dir / f"{tile}.json").write_text(body)
        counts[tile] = {"b": len(parts["b"]), "r": len(parts["r"]), "t": len(parts["t"])}
        total += len(body)
    (OUT / "tiles.json").write_text(json.dumps({"res": TILE_RES, "centre": manifest["centre"], "tiles": counts}, **COMPACT))
    log(f"wrote {len(counts)} tiles, {total / 1e6:.0f} MB")

    outlines = area_outlines(proj)
    areas = []
    for a in manifest["areas"]:
        areas.append({"id": a["id"], "name": a["name"], "lat": a["lat"], "lon": a["lon"], "outline": outlines.get(str(a["borocode"]), [])})
    (OUT / "areas.json").write_text(json.dumps({"centre": manifest["centre"], "areas": areas}, **COMPACT))
    log(f"wrote {OUT / 'areas.json'} ({len(areas)} areas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
