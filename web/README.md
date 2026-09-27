# Night Owl map

The Vite, React, TypeScript, and three.js app shows monthly H3 cells, a 5/10/20-site plan, sightings, and the inspection backtest. The colour modes show predicted 311 complaints, estimated rat signs conditional on inspection, and the difference between their percentile ranks.

## Run

```sh
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
pnpm --dir web build
pnpm --dir web lint
pnpm dlx --allow-build esbuild tsx@4.23.15 --test web/tests/*.test.mjs
```

Open `http://localhost:5173`. Run `./api/run.sh` separately for server data. `web/vite.config.ts` proxies `/api` to `http://localhost:8000` and removes the prefix. Change that target if the API runs elsewhere.

| Browser request | API endpoint |
|---|---|
| `/api/cells?month=2026-09` | `/cells?month=2026-09` |
| `/api/plan?month=2026-09&k=20` | `/plan?month=2026-09&k=20` |
| `/api/queue?limit=20` | `/queue?limit=20` |
| `/api/stream` | `/stream` |
| `/api/backtest` | `/backtest` |
| `/api/placements?h3=…` | `/placements?h3=…` |
| `/api/agent/chat` | `/agent/chat` |

The assistant sends the selected month and plan budget with each chat request. Its server tools use those values when answering map questions. It needs the backend's configured model provider; the map itself does not.

## Data labels and fallback

`/cells` and `/plan` report the source month and whether the data came from a model file or a synthetic fixture. The header shows the month actually served if it differs from the selected month. The map labels model, fixture, and stale responses. A server response marked `synthetic` is shown as a fixture.

If an API request fails or takes more than eight seconds, `web/src/api.ts` loads `city/cells.fixture.json`, `city/plan.fixture.json`, or `city/queue.fixture.json`. These are demonstration data. The app has no local backtest fixture, so the chart says it is unavailable when `/api/backtest` cannot be reached. A server-provided synthetic backtest carries a synthetic badge. The chart draws only the series present in the response and uses its reported `k`; it does not generate other plan sizes.

The app polls the queue every two seconds and listens for Server-Sent Events. It reconnects a closed stream and refreshes cells and plans after new live events or a reset. Fixture queue rows never become persisted owls. Only accepted server events change the posterior; the browser fetches the server's updated cells and plan instead of computing its own update.

## City tiles and controls

The H3 map, plan pins, cell popup, and camera focus work without a city bake. For the 220-tile bake, run `python3 web/scripts/install_city_bake.py` from the repository root with GitHub CLI access. The installer checks the pinned `city-bake-v1` release asset and its SHA-256 before extracting it under `web/public/city/`. The bake is optional and gitignored.

The city bake supplies ground polygons, borough outlines, buildings, roads, and trees. With it, the map streams nearby H3 resolution-7 tiles under a building budget. The camera follows an area when you select a borough. Without it, the map stays citywide and the cells and plan remain selectable. See [city/README.md](../city/README.md) for the bake format.

- Use the month picker and site-budget control to choose the model view.
- Search for an address, neighborhood, or H3 cell, or use **Demo cell** to focus the example cell.
- Switch between complaint, rat-sign, and silence modes. Click a cell for scores, inspection count, interval, posterior, and top reasons.
- Open a suggested site to see tree-pit options when `/placements` is available. Place an owl on the map or at a suggested site.
- Use the sightings drawer for queue events and their crops. The source badge distinguishes server events from fallback fixtures.
- Drag to orbit. WASD or arrow keys move the camera; J and K change height. The day and night buttons change the scene lighting.

Placed owls are kept in browser `localStorage`. The first placed owl uses `node_id=demo-01` for the stage fixture. A live event from an unknown node creates a map owl at its H3 cell. A fixture event does not. An accepted event can change a cell without moving a plan pin if that cell is outside the planner's candidate pool.

The optional assistant can inspect the current map, take a screenshot, and drive map controls. Its answers may also use model files and queued events. Check the map's source labels and the underlying evidence before treating an answer as a measurement.

## Main files

| Path | Role |
|---|---|
| `src/App.tsx` | Map state, API refresh, queue, SSE, and controls |
| `src/api.ts` | API requests and fixture fallback |
| `src/agent.ts`, `src/components/AgentChat.tsx` | Assistant stream and chat UI |
| `src/owls.ts` | Placed-node storage and activity |
| `src/city/scene.ts`, `src/components/Scene.tsx` | three.js scene and React bridge |
| `src/city/tiles.ts`, `src/city/addresses.ts` | Tile selection and address lookup |
| `src/components/BacktestChart.tsx` | Backtest chart from the returned series |
| `scripts/install_city_bake.py` | Pinned city-bake installer |
