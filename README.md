# Night Owl

Night Owl is a DivHacks prototype for finding NYC blocks where rat risk may be higher than 311 complaints suggest. The map compares two monthly H3 cell rankings: Model A predicts complaints, and Model B estimates active rat signs conditional on inspection. Their percentile difference is the "silence" score. It is a planning signal, not a count of rats.

The web app shows those cells, suggested sensor sites, an inspection backtest, and a sightings feed. A Raspberry Pi camera node can send a detection to the local API, which updates the affected cell's posterior. The API owns that update; the browser refetches the result.

## Run the local map

Use two terminals from the repository root:

```sh
./api/run.sh
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
```

Open `http://localhost:5173`. The Vite server forwards `/api` requests to the API on port 8000. If the API is unavailable, the map shows labeled fixture data; the backtest panel reports that it is unavailable. The map and plan pins work without the optional city tiles. To install the pinned city bake, see [web/README.md](web/README.md).

Run the software checks with:

```sh
uv run --project api pytest -q api/tests
pnpm --dir web build
pnpm --dir web lint
```

## What is verified

The map, API, and detector have separate evidence. One reviewed plush detection from the live Pi camera reached an isolated local API and appeared on the map. That verifies one end-to-end event, not field accuracy or reliable detection across repeated appearances. See [the live trial](vision/V5_LIVE_RESULTS.md).

The V5 detector remains a demo candidate. Its fresh box test scored 0.6158 rat AP50 as run, with documented reference-label problems and no corrected score. A separate fixed-rule event test found 18 of 19 plush appearances but produced 17 false alerts during 190.409 seconds of no-plush footage. It failed the event gate. V6 also failed its fixed guards and was not promoted. Neither result supports a 90% real-world accuracy claim. Read the [fresh box test](vision/V5_FRESH_RESULTS.md), [formal event test](vision/V5_FORMAL_EVENT_RESULTS.md), and [artifact index](vision/artifacts/README.md) before using the model or its numbers in a demo.

## Repository guide

| Path | Contents |
|---|---|
| [web/](web/README.md) | React and three.js map, plan, backtest, sightings feed, and assistant UI |
| [api/](api/README.md) | FastAPI endpoints, event persistence, posterior updates, and source labels |
| [model/](model/README.md) | Monthly cell features, model outputs, planning, and backtest |
| [vision/](vision/RUNBOOK.md) | Plush detector training, evaluation, and Pi runtime |
| [city/](city/README.md) | H3 fixtures and optional 3D city bake |
| [plan/](plan/master-plan.md) | Team plan and data contract |
| [docs/utsav-technical-handoff.md](docs/utsav-technical-handoff.md) | Detailed technical handoff and evidence limits |

Fixture events and the scripts under `api/` are for an isolated rehearsal. They are not Pi observations or detector evaluation data. The historical Barn Owl name remains in file paths, environment variables, storage keys, and the `barn-owl.tech` domain.
