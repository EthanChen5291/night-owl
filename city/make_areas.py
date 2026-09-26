#!/usr/bin/env -S uv run --with h3 --with shapely python
"""make_areas.py: per-borough ground layers and the tile -> borough assignment, on top of make_tiles.py.

Reads $RAW/boroughs.geojson, $RAW/city/parks_citywide.geojson, $RAW/city/hydro_citywide.geojson and the
existing web/public/city/tiles.json. Writes, in web/public/city/:

  areas/<id>/land.json, parks.json, water.json   [{id, ring}]  the borough's own ground (only this is drawn inside an area)
  areas.json                                       {centre, areas: [{id, name, lat, lon, outline}]}
  tiles.json                                       adds "a": <area id> to every tile (by its centre; water-only tiles get null)

Fast: under a minute. Run after make_tiles.py, or alone after editing city/areas.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = Path(os.environ.get("RAW", "~/divMap/data/raw")).expanduser()
OUT = ROOT / "web" / "public" / "city"
COMPACT = {"separators": (",", ":")}

sys.path.insert(0, str(HERE))
import build_city  # noqa: E402


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_features(path: Path):
    from shapely.geometry import shape

    with path.open() as f:
        for feat in json.load(f)["features"]:
            geom = feat.get("geometry")
            if geom:
                yield {k.lower(): v for k, v in (feat.get("properties") or {}).items()}, shape(geom)


def rings_within(path: Path, prepared, proj: build_city.Projector, simplify_m: float, min_area: float) -> list[dict]:
    out = []
    n = 0
    for props, g in load_features(path):
        n += 1
        rid = str(props.get("source_id") or props.get("objectid") or props.get("parknum") or props.get("name") or n)
        parts = build_city.polygon_parts(g)
        for i, part in enumerate(parts):
            if not prepared.contains(part.centroid):
                continue
            ring = build_city.local_ring(proj, part, simplify_m, min_area)
            if ring:
                out.append({"id": rid if len(parts) == 1 else f"{rid}.{i + 1}", "ring": ring})
    return out


def main() -> int:
    import h3
    from shapely.geometry import Point
    from shapely.prepared import prep

    manifest = json.loads((HERE / "areas.json").read_text())
    proj = build_city.Projector(manifest["centre"]["lat"], manifest["centre"]["lon"])
    boroughs = {}
    for props, g in load_features(RAW / "boroughs.geojson"):
        boroughs[str(props.get("borocode"))] = g
    parks_path = RAW / "city" / "parks_citywide.geojson"
    hydro_path = RAW / "city" / "hydro_citywide.geojson"

    areas = []
    prepared_by_id = {}
    for a in manifest["areas"]:
        g = boroughs.get(str(a["borocode"]))
        if g is None:
            log(f"{a['id']}: no borough {a['borocode']} in boroughs.geojson")
            continue
        prepared = prep(g)
        prepared_by_id[a["id"]] = (g, prepared)
        out_dir = OUT / "areas" / a["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        parts = build_city.polygon_parts(g)
        land = []
        for i, part in enumerate(parts):
            ring = build_city.local_ring(proj, part, 2.0, 200.0)
            if ring:
                land.append({"id": f"{a['id']}.{i + 1}", "ring": ring})
        parks = rings_within(parks_path, prepared, proj, 1.0, 40.0) if parks_path.is_file() else []
        water = rings_within(hydro_path, prepared, proj, 2.0, 200.0) if hydro_path.is_file() else []
        for name, data in (("land", land), ("parks", parks), ("water", water)):
            (out_dir / f"{name}.json").write_text(json.dumps(data, **COMPACT))
        biggest = max(parts, key=lambda p: p.area)
        areas.append({"id": a["id"], "name": a["name"], "lat": a["lat"], "lon": a["lon"], "outline": build_city.local_ring(proj, biggest, 25.0, 0.0) or []})
        log(f"{a['id']}: land {len(land)} parts, parks {len(parks)}, water {len(water)}")

    (OUT / "areas.json").write_text(json.dumps({"centre": manifest["centre"], "areas": areas}, **COMPACT))
    log(f"wrote {OUT / 'areas.json'} ({len(areas)} areas)")

    tiles_path = OUT / "tiles.json"
    if tiles_path.is_file():
        tiles = json.loads(tiles_path.read_text())
        assigned = 0
        for tile, counts in tiles["tiles"].items():
            lat, lon = h3.cell_to_latlng(tile)
            p = Point(lon, lat)
            area_id = next((aid for aid, (_, pr) in prepared_by_id.items() if pr.contains(p)), None)
            if area_id is None:
                # a tile centred on water still belongs to whichever borough is nearest, within 1.5 km
                best = min(((g.distance(p), aid) for aid, (g, _) in prepared_by_id.items()), default=(1e9, None))
                area_id = best[1] if best[0] * 111_000 < 1500 else None
            counts["a"] = area_id
            assigned += area_id is not None
        tiles_path.write_text(json.dumps(tiles, **COMPACT))
        log(f"tiles.json: {assigned}/{len(tiles['tiles'])} tiles assigned to an area")
    return 0


if __name__ == "__main__":
    sys.exit(main())
