# web - Barn Owl map (deliverable 1 + backtest chart + live feed)

Vite + React + TypeScript + three.js. One page: a citywide H3 map with optional 3D city tiles, the
city-sees / actually-there / silence toggle, a popup with the contract fields, a selectable 5/10/20-site
node plan as pins, a live event feed, and the backtest chart.

## Run

```
cd web
pnpm install
pnpm dev             # http://localhost:5173
pnpm build           # tsc -b && vite build -> dist/
pnpm lint
```

## API and the dev proxy

All requests go to `/api/...`. `vite.config.ts` proxies `/api` to `http://localhost:8000` and
strips the prefix, so the server keeps the contract's bare paths:

| frontend | server |
|---|---|
| `GET /api/cells?month=2026-09` | `GET /cells?month=2026-09` |
| `GET /api/plan?month=2026-09&k=20` | `GET /plan?month=2026-09&k=20` |
| `GET /api/queue?limit=20` (polled every 2 s) | `GET /queue?limit=20` |
| `GET /api/stream` (optional SSE, one event JSON per message) | `GET /stream` |
| `GET /api/backtest` | `GET /backtest` |
| `GET /api/placements?h3=…` | `GET /placements?h3=…` (spot options inside a ranked hexagon; 503 without `model/out/placements.json`) |

Change the target in `vite.config.ts` if the model server runs elsewhere.

`/backtest` shape: `{"window":[from,to],"k":50,"series":[{"month","precision_silent","precision_311","n_positives"}],"summary":{...},"synthetic":bool}`.
`summary.lift` (or `mean_lift` / `precision_lift`) is shown in the panel header; `synthetic: true` shows a SYNTHETIC badge.

## Fixture fallback

If a request fails or times out (8 s) the app imports the repo fixtures directly from
`../city/*.fixture.json` (single source, nothing is copied): `cells.fixture.json`, `plan.fixture.json`,
`queue.fixture.json`. The header marks model, fixture, or stale data and shows the served month if it differs from the requested month. The H3 map, planned sites, and cell popup work without generated city tiles. There is no backtest fixture;
without the API the panel says "backtest not available". Polling keeps trying `/api/queue` every 2 s,
so starting the server later flips the feed to live without a reload.

## The city (optional bake)

The scene renders the ground, the hex prisms, the plan pins and the owls without any city bake.
Everything else comes from `web/public/city/` (gitignored), three bakes in `city/`:

To install the existing 220-tile bake, run `python3 web/scripts/install_city_bake.py` from the
repository root with GitHub CLI access to this repo. The script pins the `city-bake-v1` release
asset by SHA-256, checks its paths and manifests, and leaves any existing bake untouched.

| File | From | Drawn as |
|---|---|---|
| `land.json`, `parks.json`, `water.json` `[{id, ring}]` | `build_city.py` (citywide, once) | the citywide map under the colour field; hidden inside an area |
| `areas/<id>/{land,parks,water}.json` | `make_areas.py` | the active borough's own ground, the only land drawn while you are in it |
| `areas.json` `{centre, areas: [{id, name, lat, lon, outline}]}` | `make_tiles.py` + `make_areas.py` | the boroughs: clickable fills and coastlines in the citywide view, name tags everywhere; the camera flies to `lat/lon`; the outline says which cells and buildings are theirs |
| `tiles.json` `{res: 7, tiles: {<r7>: {b, r, t, a}}}` | `make_tiles.py` (+ `a` from `make_areas.py`) | counts per tile for the streaming budget, and the borough each tile belongs to |
| `tiles/<r7>.json` `{buildings, roads, trees}` | `make_tiles.py` | one merged building mesh (procedural facade, lit windows at night, colour = height band blended with the cell colour), one road mesh, one instanced canopy per tile |
| `meta.json` | either | its `centre` is the projection origin; every bake shares `city/areas.json`'s centre |

**Streaming** (`src/city/tiles.ts`): the scene reports where the camera looks; the app keeps the r7 tile under
the target, its ring of 6, and ring 2 while the total stays under 90k buildings, fetches what is missing
(40-tile cache) and drops the rest. Only the active area's tiles (`a` in `tiles.json`) ever load, and a
tile on a river is built for the active bank only (each building, road piece and tree is checked against
the borough outline by its r9 cell), so the other boroughs cost nothing. Past a 12 km orbit distance
nothing streams. Shadows follow the camera target. Nothing is ever cut off at a box edge: fly anywhere
with WASD (arrows work too), J/K climb and dive, drag to orbit.

**Two views of the cells.** Citywide there are no prisms: the cells are one flat vertex-coloured mesh over
the whole city, each hex corner averaged with its neighbours so it reads as a smooth gradient, muted
towards the look's neutral. Inside an area the r9 prisms of that area stand up (height and colour from
the mode). Both use the ramps in `src/colours.ts`.

**Addresses**: buildings carry their PLUTO address, trees the street address their pit fronts.
`src/city/addresses.ts` grids the loaded tiles so hovering shows the building you are over or `near <the
nearest tree pit>`, and a placed owl snaps to the nearest tree pit (they hang on tree guards).

Lighting presets (`day` is the default, `night` is the stage look): sky dome, fog, sun with shadows and
the facade/window mix all live in `LOOKS` in `src/city/scene.ts`; the UI theme tokens follow the preset
through `data-theme` on `<html>` (`src/index.css`).

## Owls

Owls are the placed sensor nodes (`src/owls.ts`, kept in `localStorage` until the contract grows a
placements endpoint). Place one with the pin tool (top left) and a click, or click a suggested site pin, or
a suggested row in the panel. The first owl takes `node_id = demo-01`, so the stage node's events land on
it; an event from an unknown `node_id` spawns an owl at that cell. Each owl: `Owl n`, address, tree id,
the sightings from `/queue` whose `node_id` matches, and an activity ring around a node icon (green to red, thicker and more opaque with sightings in the last
15 minutes, red at 6). Click an owl to select it (camera glides there), the trash icon or Delete removes
it, Esc clears. The log button opens every sighting with its crop, address and time. An owl is never inside a
building: a click on a footprint moves to the nearest tree pit within 150 m, else to the sidewalk at the footprint's
edge (owls saved earlier, or spawned by an event at a cell centre, are moved the same way once the tiles load).
Inside a borough only its owls exist, on the map and in the list; citywide all of them show.

On the map an owl is, from afar, a flat red badge with a pink rim that grows gently with distance and draws
through the buildings (never lost behind one) but under the prism glass (it reads at ground level); within a
few hundred metres it crossfades into a deep-red 3D pin (base, post, head) standing on the pavement, a real
object in the street: depth-tested, so buildings in front of it hide it (a faint red ghost shows through where it is
hidden, so it stays locatable), lit, with its own cast shadow and a contact shadow under the base. A click flies in
looking down steeply and swings round to an angle from which no loaded building blocks the pin (rays from candidate
camera spots against the building meshes; 30-degree steps, then steeper). Markers draw after the prism glass and the flat ones are unlit, unfogged and untone-mapped, so their red is
never tinted by the cell colour, the sun or the haze. Around it: a semi-transparent white disc for its ~110 m coverage, two slow white pulse
rings, and a red ripple along the edge when selected. Hovering swells the marker and sweeps the rim yellow
clockwise from 12 o'clock; clicking makes it hop and flies the camera all the way in to the pin. The click
target is wider than the badge.

## Suggested hexagons and the spots inside them

`/plan` ranks hexagons (k=20 citywide; the panel shows the ones in the borough you are in, amber numbered
discs on the map). Click a row or its pin and the camera glides there and the row opens its **spot options**
from `GET /placements?h3=` (`model/09_placements.py`: up to three ~50 m spots inside the hexagon, each with a
street tree to mount on, a score and reasons). They show as small red pulsing glass discs A, B, C on their trees,
in the same family as the owl badge; the plan hexagons themselves are amber discs with their rank. Click an option
to fly to it, its pin icon (or the green pin on the map) to place an owl there: the owl takes the spot's tree
and mount address.

## Behaviour

The interface is icons first; every control names itself on hover.

- Citywide on load: a near top-down map with the colour field, the boroughs as glass-tagged shapes and a
  `Fly to` card (top left). Click either and the camera flies in (an arc, ~2 s); the back button (top left)
  flies out. Inside an area the other boroughs' name tags stay on their boroughs; click one to hop
  straight across: the old borough's ground and buildings go, the new one's load. Tags keep a constant
  size on screen, larger citywide. The area and the view mode live
  in the URL hash (`#mode=silence&a=manhattan`) and in `localStorage`.
- Mode bar (top centre): home = `What the city sees` (pct_a), signal = `What's there` (pct_b), muted bell =
  `Silence` (pct_b − pct_a, orange = silent blocks); the active one is named in the chip underneath.
  Sun / moon switch day and night.
- Toolbar (top left, inside an area): back, place an owl, suggested hexagons (the `/plan` pins and their
  spot options), sightings log.
- Hover: a chip above the cursor with the address (`near …` for street pits), the cell's value in the
  current mode and its sightings; over an owl or a suggested pin it says what a click does.
- Click a hex (from more than ~1 km out; closer in the prisms are glass over the street, neither hoverable nor
  clickable, and the pointer reads the building or tree pit instead): a pinned card (top left) with the three views as bars, P(active) with its interval, the
  sightings, the top-3 reasons. Click again or Esc to close.
- Owls panel (right): one card per owl with its gauge, address, last sighting; suggested sites under it.
  The arrow on its left border slides it away; the backtest strip has the same arrow on its top border.
- A new event flashes its cell, then refetches `/cells` and `/plan`; the API owns the posterior and ranking.
  Events arrive over SSE (`event:` messages) with the 2 s poll as the fallback.
- Backtest strip (bottom): KPI tiles (lift, mean precision of both rankings, months ahead) and the two
  precision lines with the COVID months shaded; direct labels at the line ends, a glass tooltip.

## Component map

```
src/
  App.tsx                 state: mode, area, cells, plan, events, owls, tiles, hover; fetching, polling, streaming
  api.ts                  fetch helpers with fixture fallback, /api base, public/city loader
  owls.ts                 owl records (localStorage), the stage node id, the activity rate
  colours.ts              sequential (viridis-like) and diverging (blue-neutral-orange) ramps; legend + mesh share them
  types.ts                the frozen JSON contract, the bake shapes, owls, hover and view info
  city/projection.ts      equirectangular lat/lon <-> local metres (same as build_city.py)
  city/tiles.ts           which r7 tiles to keep for a view (budgeted), and the tile cache
  city/addresses.ts       grid over the loaded tiles: building at a point, nearest tree pit
  city/facade.ts          the procedural window texture (albedo + lit mask)
  city/scene.ts           three.js: sky, citywide + per-area ground, tiles (filtered to the area), the flat colour
                          field, hex prisms, borough tags, owls, plan pins, camera flights, WASD/JK, raycast hover
                          and click. No React inside. In dev it is on window.__barnowl for the screenshot scripts.
  components/Scene.tsx    the canvas + the effects that feed CityScene
  components/Icons.tsx    the icon set
  components/ModeBar.tsx  view icons + day/night
  components/Toolbar.tsx  back, place, suggestions, log
  components/AreaPicker.tsx
  components/HoverTip.tsx
  components/CellPopup.tsx  pinned cell card
  components/NodesPanel.tsx + Gauge.tsx   owls with activity rings, suggested sites
  components/LogsDrawer.tsx sightings with crops
  components/BacktestChart.tsx (Recharts)
  components/Legend.tsx, Header.tsx
```
