# web - Barn Owl map (deliverable 1 + backtest chart + live feed)

Vite + React + TypeScript + three.js. One page: a 3D H3 map of lower Manhattan with the
city-sees / actually-there / silence toggle, a hover popup with the contract fields, the k=8
node plan as pins, a live event feed, and the backtest chart.

## Run

```
cd web
npm install
npm run dev          # http://localhost:5173
npm run build        # tsc -b && vite build -> dist/
npx tsc --noEmit -p tsconfig.app.json
```

## API and the dev proxy

All requests go to `/api/...`. `vite.config.ts` proxies `/api` to `http://localhost:8000` and
strips the prefix, so the server keeps the contract's bare paths:

| frontend | server |
|---|---|
| `GET /api/cells?month=2026-08` | `GET /cells?month=2026-08` |
| `GET /api/plan?k=8` | `GET /plan?k=8` |
| `GET /api/queue?limit=20` (polled every 2 s) | `GET /queue?limit=20` |
| `GET /api/stream` (optional SSE, one event JSON per message) | `GET /stream` |
| `GET /api/backtest` | `GET /backtest` |

Change the target in `vite.config.ts` if the model server runs elsewhere.

`/backtest` shape: `{"window":[from,to],"k":50,"series":[{"month","precision_silent","precision_311","n_positives"}],"summary":{...},"synthetic":bool}`.
`summary.lift` (or `mean_lift` / `precision_lift`) is shown in the panel header; `synthetic: true` shows a SYNTHETIC badge.

## Fixture fallback

If a request fails or times out (3 s) the app imports the repo fixtures directly from
`../city/*.fixture.json` (single source, nothing is copied): `cells.fixture.json`, `plan.fixture.json`,
`queue.fixture.json`. The header pill says `API: live` or `API: fixture`. There is no backtest fixture;
without the API the panel says "backtest not available". Polling keeps trying `/api/queue` every 2 s,
so starting the server later flips the feed to live without a reload.

## Buildings (optional)

The scene renders the ground, the hex prisms, the plan pins and the events without any city bake.
If `web/public/city/buildings.json` exists (shape `[{id, h3, footprint: [[x, y], ...], height}]`, local
metres) the buildings are drawn as one merged extruded mesh tinted by their cell's colour. It is produced by
`city/build_city.py` from the open-data footprints:

```
./city/build_city.py --buildings data/raw/open/building_footprints.csv \
                     --trees data/raw/open/street_trees_2015.csv --out web/public/city
```

`meta.json` from the same bake (its `centre`) is used as the projection origin so the buildings line up
with the cells; without it the centroid of the served cells is the origin. The file is not in git.

## Behaviour

- Toggle (top-left): `What the city sees` (pct_a), `What's there` (pct_b), `Silence` (silence,
  diverging, orange = silent blocks). The mode is kept in the URL hash (`#mode=silence`).
  Lighting: `night` (warm key light, fog) or `flat`.
- Hover a hex: CellPopup with h3, cd, rmz, score_a, score_b, pct_a/pct_b, silence, ci_b, posterior
  (alpha, beta, n_events), top-3 reasons as SHAP bars, n_inspections, last_event_at.
- Legend (bottom-left) follows the mode and has the plan-markers checkbox.
- EventFeed (right): newest first; a new event flashes its cell for ~1.5 s, bumps that cell's
  posterior alpha and n_events locally, then refetches /cells after 1 s. Click a row to fly to the cell.
- BacktestChart (bottom, collapsible): precision_silent vs precision_311 per month.

## Component map

```
src/
  App.tsx                 state: mode, month, cells, plan, events, hover, flash; fetching and polling
  api.ts                  fetch helpers with fixture fallback, /api base, public/city loader
  colours.ts              sequential (viridis-like) and diverging (blue-neutral-orange) ramps; legend + mesh share them
  types.ts                the frozen JSON contract as TypeScript
  city/projection.ts      equirectangular lat/lon -> local metres (same as build_city.py)
  city/scene.ts           three.js: ground, hex prisms (h3-js cellToBoundary + ExtrudeGeometry), buildings,
                          plan pins, presets, raycast hover, flash pulse. No React inside.
  components/Scene.tsx    the canvas + the one useEffect that owns CityScene
  components/Toggle.tsx   mode buttons + lighting preset
  components/Legend.tsx   ramp bar for the mode, plan toggle
  components/CellPopup.tsx
  components/EventFeed.tsx
  components/BacktestChart.tsx  (Recharts)
  components/Header.tsx   Barn Owl, month, cell count, API pill
```
