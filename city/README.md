# City renderer (frontend workstream)

The map is deliverable (1) of the three that must ship: Lower Manhattan in 3D with an H3 r9 overlay,
a city-sees / actually-there toggle, and a live cell that lights up when the node on stage posts an
event. This directory holds the docs, the data bake and the fixtures; the app itself lives in
`~/divMap` (`src/`, `public/city/`) and is described below so Utsav can rebuild or extend it without
the original chat context.

## What exists

`~/divMap` is a Vite + React + three.js app: `npm install && npm run dev`, then http://localhost:5173.

- Lower Manhattan south of 14th St from open data: 43.6k building footprints extruded to `heightroof`,
  2015 street trees as points, bridges as lines. All from `public/city/{buildings,trees,bridges,meta}.json`,
  baked by `build_city.py` (below). Coordinates are local metres, x east / y north; the scene maps them
  to three.js x / -z.
- Three lighting presets (day, dusk, night-IR). Night is the one for the pitch: the node's cyan band
  reads well and the cells glow.
- H3 overlay: one flat hex mesh per `/cells` row, coloured by percentile rank. Building tint follows the
  colour of the cell the building's centroid falls in (`buildings.json[i].h3` is precomputed for this,
  so the lookup is a dictionary, not a point-in-polygon).
- Hover popup with the contract fields: `h3`, `score_a`, `score_b`, `pct_a`, `pct_b`, `silence`, `ci_b`,
  posterior α/β/`n_events`, top-3 `reasons`, `cd`, `rmz`, `n_inspections`, `last_event_at`.
- Data comes from `public/city/cells.fixture.json`, which is **synthetic**. Nothing in the map is a real
  model output yet.

## The toggle

Three colour modes, one control, the same geometry:

| Mode | Colour field | Palette | Reads as |
|---|---|---|---|
| **city sees** | `pct_a` (percentile of predicted complaints) | sequential | the 311 map: who calls |
| **actually there** | `pct_b` (percentile of P(active \| inspected)) | sequential, same ramp | what proactive inspections find |
| **silence** | `silence = pct_b - pct_a`, range -100..100 | diverging, centred on 0 | high B / low A = the silent blocks |

Flipping between the first two is the whole pitch in one gesture: the LES and Chinatown go from dim
to bright, the Village and FiDi go the other way. Silence mode is the answer key. Legend follows the
mode. Keep the camera still when the mode changes so the eye sees only the colour move.

## Going live

`loadCity()` in `src/city/scene.ts` currently fetches `/city/cells.fixture.json`. To go live:

1. Point it at `/cells?month=2026-08` (same JSON shape, nothing else in the scene changes).
2. Add a Vite dev proxy in `vite.config.ts` so `/cells`, `/plan`, `/queue` and `/event` forward to the
   model server (whatever port Ethan's API runs on; one line per route).
3. Poll `GET /queue` every 2 s (or open an EventSource if the API offers one). A new event with
   `h3 = 892a100d2c3ffff` flashes that cell, appends to the EventFeed, and bumps the cell's posterior in
   place (`alpha += 1`) until the next `/cells` refresh brings the server's number.
4. `GET /plan` draws the k=8 proposed node sites as markers at `lat/lon` (project them with the same
   centre as `meta.json`).

The month selector should call `/cells?month=YYYY-MM`; the fixture only has `2026-08`.

## Fixtures

Made by `make_fixture.py` (stdlib + `h3`, seed 42): `./city/make_fixture.py`, or
`./city/make_fixture.py --out ~/divMap/public/city` to drop them where the app reads them.

| File | Endpoint | What is in it |
|---|---|---|
| `cells.fixture.json` | `GET /cells?month=2026-08` | 126 H3 r9 cells covering Lower Manhattan south of 14th St, plus the demo cell |
| `plan.fixture.json` | `GET /plan` | 8 node placements, greedy by expected gain with a 100 m exclusion, demo cell pinned at rank 1 |
| `queue.fixture.json` | `GET /queue` | 3 events from `demo-01`, `crop_b64` left empty to keep the file small |

The numbers are shaped, not random: `score_b` peaks around a few "silent" hotspots (Seward Park,
Tompkins Square, Columbus Park, Two Bridges), `score_a` follows the baseline rat rate and is then
scaled by a per-CD complaint propensity (FiDi and the Village call more, the LES calls less). So
silence is strongly positive across CD 103 and negative in 101/102, which is the story the real model
should tell. Percentiles are proper average-rank percentiles, not min-max. `ci_b` is the 95% interval
of the Beta posterior (prior = `score_b` with strength 6, evidence = inspections + node events).
Twelve cells near Grand St carry `rmz = "Chinatown/East Village/LES"`; everything else is `null`.

The demo cell `892a100d2c3ffff` (`DEMO_H3` in `vision/pi/detect.py`) is at 27th St & 6th Ave, north of
14th, so it is outside the polygon; the script appends it anyway and says so on stderr. It is forced to
read as a silent block (`pct_b` 100, `pct_a` ~59) with `n_events = 3`, so the stage demo has somewhere
to land. If the renderer's bbox stays at 14th St the cell will sit just off the top edge of the
buildings; either widen `--bbox` in `build_city.py` to `-74.025,40.698,-73.968,40.756` or move the demo
cell to one inside the polygon (change `DEMO_H3` in both `make_fixture.py` and `detect.py`).

## The JSON contract (frozen at hour 0)

```
GET /cells?month=YYYY-MM
{"month": "2026-08", "generated_at": ISO,
 "cells": [{
   "h3": "892a100d2c3ffff",
   "score_a": float,            predicted complaints per month (Model A, all features)
   "score_b": float,            P(active | inspected) (Model B, physical features, IPW)
   "pct_a": 0..100, "pct_b": 0..100,
   "silence": pct_b - pct_a,
   "ci_b": [lo, hi],
   "posterior": {"alpha": float, "beta": float, "n_events": int},
   "reasons": [{"feature": str, "shap": float} x3],
   "cd": "101", "rmz": str | null,
   "n_inspections": int, "last_event_at": ISO | null }]}

GET /plan
{"month", "k": 8, "nodes": [{"rank", "h3", "lat", "lon", "tree_id": str,
                             "expected_gain": float, "silence": float, "reason": str}]}

GET /queue
{"events": [{"node_id": "demo-01", "h3", "ts": ISO, "class": "rat", "conf": float,
             "n_hits": int, "bbox": [x, y, w, h], "crop_b64": str, "fw": "0.1.0", "received_at": ISO}]}

POST /event   (what the Pi sends; the queue echoes it with received_at added)
{"node_id", "h3", "ts", "class", "conf", "n_hits", "bbox", "crop_b64", "fw"}
```

`bbox` is in the 640x480 detector frame. Feature names in `reasons` come from the feature table:
`restaurant_vermin_12mo`, `dob_nb_permits_6mo`, `litter_baskets_100m`, `catch_basins_100m`, `tree_pits`,
`pluto_bldg_age`, `lomod_pct`, `park_adjacent`, `temp_mean`. Render them as-is with underscores
replaced; do not maintain a display-name map on the frontend.

The backtest chart's endpoint is not in the frozen set. Suggested: `GET /backtest` ->
`{"months": [...], "series": {"model_b": [...], "complaints_only": [...], "random": [...]}, "metric": str}`.
Confirm against `plan/master-plan.md` §6 before building `BacktestChart` around it.

## The data bake: `build_city.py`

`#!/usr/bin/env -S uv run --with duckdb --with h3 --with shapely python`, so `./city/build_city.py --help`
just works. It never downloads: pass paths to the raw CSVs (or the Parquet from
`data/bake_open_data.py`).

```
./city/build_city.py --buildings data/raw/open/building_footprints.csv \
                     --trees data/raw/open/street_trees_2015.csv \
                     [--bridges bridges.csv] --out ~/divMap/public/city
```

Inputs can also be GeoJSON FeatureCollections (the raw downloads in `~/divMap/data/raw/*.geojson`) and
the Socrata JSON export for trees. Four optional flat layers, each a polygon file in the same formats,
write `<layer>.json` as `[{id, ring: [[x, y], ...]}]` clipped to the bbox: `--land` (borough boundaries,
the land mass), `--roads` (roadbed), `--parks` (parks properties), `--water` (hydrography). The full
city look is:

```
R=~/divMap/data/raw
./city/build_city.py --buildings $R/buildings.geojson --trees $R/trees.json --land $R/boroughs.geojson \
    --roads $R/roadbed.geojson --parks $R/parks.geojson --water $R/hydro.geojson \
    --bbox=-74.03,40.688,-73.94,40.76 --out web/public/city
```

(`--bbox=` with the equals sign: a value starting with `-` is otherwise read as a flag.) That bbox reaches
27th St so the demo cell sits inside the city. Ten seconds on a laptop.

Citywide base under the model's 5k cells, buildings still local: two runs into the same `--out` with the
same `--centre` (the second run keeps the first run's files and merges the counts in `meta.json`):

```
C=40.724,-73.985
./city/build_city.py --land $R/boroughs.geojson --parks $R/city/parks_citywide.geojson \
    --water $R/city/hydro_citywide.geojson --bbox=-74.27,40.49,-73.69,40.92 --centre $C --out web/public/city
./city/build_city.py --buildings $R/buildings.geojson --trees $R/trees.json --roads $R/roadbed.geojson \
    --bbox=-74.03,40.688,-73.94,40.76 --centre $C --out web/public/city
```

`parks_citywide.geojson` and `hydro_citywide.geojson` are the full GeoJSON exports of y6ja-fw4f and
pjs3-c3z5 (about 45 MB each); the bbox-limited copies in `raw/` stop at the Lower Manhattan box.

## Tiles: `make_tiles.py` (the whole city, streamed)

The second run above is superseded by tiles. `make_tiles.py` streams the citywide exports once (ijson, so
the 856 MB footprints file never sits in memory), joins PLUTO addresses by BBL, and writes one file per H3
r7 tile plus a manifest and the borough areas; the web app streams tiles around the camera (see
`web/README.md`). Inputs, ~1.5 GB, from the API export endpoints:

```
C=~/divMap/data/raw/city
curl -L -o $C/buildings_citywide.geojson 'https://data.cityofnewyork.us/api/geospatial/5zhs-2jue?method=export&format=GeoJSON'
curl -L -o $C/roadbed_citywide.geojson   'https://data.cityofnewyork.us/api/geospatial/i36f-5ih7?method=export&format=GeoJSON'
curl -L -G -o $C/trees_citywide.json 'https://data.cityofnewyork.us/resource/uvpi-gqnh.json' \
    --data-urlencode '$select=tree_id,latitude,longitude,address,status' --data-urlencode '$limit=1000000'
./city/make_tiles.py          # ~3 min -> web/public/city/tiles/*.json, tiles.json, areas.json
./city/make_areas.py          # <1 min -> web/public/city/areas/<id>/{land,parks,water}.json, tiles.json gets "a"
```

`city/areas.json` is the source of the boroughs' names and landing centres and of the shared projection
centre; `make_tiles.py` adds each borough's outline from `boroughs.geojson`.

`make_areas.py` runs after it (or alone, after editing `city/areas.json`): it cuts each borough's own
land, parks and water out of `boroughs.geojson`, `parks_citywide.geojson` and `hydro_citywide.geojson`
(the web app draws only the active borough's ground, so the rest of the city costs nothing while you are
in one), and stamps every entry in `tiles.json` with `"a": <area id>`, the borough its centre falls in
(a tile centred on water goes to the nearest borough within 1.5 km, otherwise `null`). The app streams
only the active area's tiles.

Flags: `--bbox min_lon,min_lat,max_lon,max_lat` (default Lower Manhattan south of 14th St),
`--centre lat,lon` (origin of the metre frame, default bbox centre), `--res 9`, `--simplify 0.5`
(metres, Douglas-Peucker), `--min-area 8` (m², drops sheds and slivers), `--height-units feet|metres`
(the source is feet), `--elev` (adds `groundelev` as `elev`), `--limit N` for smoke tests, `--indent`.

Outputs: `buildings.json` `[{id, h3, footprint: [[x, y], ...], height}]`, `trees.json` `[{id, x, y, h3}]`,
`bridges.json` `[{id, path: [[x, y], ...]}]`, `meta.json` (centre, bbox, counts, crs, h3_res). DuckDB
does a bbox prefilter on the first WKT vertex with a regex so the 1.1M-row footprints file never fully
loads; shapely does the exact clip on the centroid, the projection, and the simplify. Holes are dropped,
multipolygon parts become `BIN.1`, `BIN.2`. Null or zero `heightroof` becomes 3 m. Dead trees and stumps
are dropped when the source has a `status` column.

## Hour-0 decision: three.js or deck.gl + MapLibre

| | three.js (exists) | deck.gl + MapLibre (plan) |
|---|---|---|
| State | built, 43.6k buildings, overlay, popup, presets | nothing built |
| Basemap | none: our own buildings, trees, bridges | real streets, labels, satellite |
| H3 layer | own hex mesh | `H3HexagonLayer` out of the box |
| Look | stylised, night mode, the node glow | a map |
| Risk | ours to fix; no street labels for orientation | 3-4 h to get to parity, plus a tile source |

**Recommendation: keep three.js.** It exists, it renders the contract, and the pitch is about the
sensor turning a ranking into evidence, not about a basemap. Swap to deck.gl only if the judges need to
read street names off the map, and then do it as a second view (a 2D "where am I" panel with
`H3HexagonLayer` over MapLibre) rather than a rewrite. Whoever decides at hour 0 writes the answer in
the top-level README §5.

## Component layout (for the scaffold)

```
src/
  App.tsx            state: month, mode ('a' | 'b' | 'silence'), cells (Map<h3, Cell>), plan, events,
                     hovered h3. Fetches /cells, /plan on mount and month change; polls /queue.
  city/
    scene.ts         three.js: loadCity() (buildings/trees/bridges/meta), buildHexes(cells), setMode(),
                     setPreset(), raycast -> onHover(h3). No React inside.
    colours.ts       sequential ramp for pct, diverging for silence; the same functions drive the Legend.
  components/
    Scene.tsx        a <canvas> plus a useEffect that owns the three.js scene; props: cells, mode, plan,
                     flash (h3 of the latest event), onHover.
    Toggle.tsx       the three-way mode control plus the month select and lighting preset.
    Legend.tsx       ramp + labels for the current mode (0..100, or -100..100 centred on 0).
    CellPopup.tsx    the hovered cell's contract fields; posterior as "α/β, n inspections, n events".
    BacktestChart.tsx  the one chart (deliverable 2): recall@k or precision vs month, Model B vs
                     complaints-only vs random. Recharts or plain SVG; no map coupling.
    EventFeed.tsx    the /queue list, newest first: node_id, class, conf, n_hits, ts, and the crop when
                     crop_b64 is non-empty. Clicking an event flies the camera to its cell.
```

Data flow: `App` holds the contract objects and passes them down; `Scene` is the only component that
touches three.js; `Toggle` and `Legend` share `colours.ts` so the swatches match the mesh. Hover goes
scene -> App -> CellPopup. New event goes `/queue` -> App -> (Scene flash, EventFeed row, cells[h3].posterior.alpha += 1).

Gate from the plan: hexes rendering from the fixtures by hour 6, live `/cells` after.
