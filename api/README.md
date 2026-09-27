# api/ — Barn Owl demo hub

FastAPI server that sits between the Pi node, the model output and the web app. It serves the frozen JSON
contract (`plan/master-plan.md` §6), takes `POST /event` from `vision/pi/detect.py`, keeps one
Beta-Binomial posterior per H3 cell and month (plan §4) and overlays it on `/cells` so the map moves when the prop
is waved on stage (plan §9).

## Run

```
./api/run.sh                                   # 0.0.0.0:8000, the Pi posts to http://192.168.7.1:8000
# or
uv run --project api uvicorn main:app --app-dir api --host 0.0.0.0 --port 8000
```

Tests: `uv run --project api pytest -q api/tests`

Stage fallback when the node or the network is dead (plan §9 step 2):

```
./api/fake_event.sh                  # POST fixtures/event.demo.json to localhost:8000 with ts = now
API=http://192.168.7.1:8000 ./api/fake_event.sh
```

Reset between rehearsals: `curl -X DELETE -H 'X-Demo-Reset: yes' localhost:8000/events`

The scripts below post staged sightings with fresh timestamps. Both change the API's persisted queue and
posterior. Use them only against an isolated rehearsal API, reset afterward, and never treat their
events as Pi detections or evaluation evidence.

```
./api/fake_sightings.py        # 15 sightings: grayscale crops of the rat prop from the team's own footage
./api/real_sightings.py        # 17 sightings: real wild rats and house mice in daylight, dusk, flash, torchlight and unlit subway track
```

`fake_sightings.py` uses rat-prop crops from team footage. `real_sightings.py` cuts openly licensed
Wikimedia Commons photos to the node's crop format (grayscale by default,
`--colour` to keep colour). The photos themselves are re-downloaded with `--fetch` into `api/fixtures/rodents/`
(gitignored); the crops are baked into `fixtures/events.real.json`, and `fixtures/rodents.credits.json` has the
author and licence of every photo. Attribute CC BY and CC BY-SA images if a crop appears on a slide.

## Endpoints (contract §6)

| Method | Path | Notes |
|---|---|---|
| GET | `/cells?month=YYYY-MM` | Exact-month model file or fixture first; otherwise current model output with its actual month. Live posterior overlay applies only to matching-month events. |
| GET | `/plan?month&k` | Same month selection; accepted detections re-rank existing tree locations when their H3 is a candidate. `replanned` reports whether the plan changed. |
| GET | `/queue?limit=50` | live events, newest first, `received_at` added. Starts empty (the queue fixture is for the frontend only) |
| POST | `/event` | The 9-key body; 400 on malformed shape or JSON. Response `accepted` is true only when this delivery updates the posterior. |
| GET | `/backtest` | `model/out/backtest.json` → `api/fixtures/backtest.json` (synthetic, flagged `"synthetic": true`) |
| GET | `/stream` | Server-Sent Events: `hello` on connect, `event` per POST, `reset` on DELETE; keepalive every 15 s |
| GET | `/health` | `{"ok":true,"events":n,"cells_source":path}` |
| DELETE | `/events` | needs header `X-Demo-Reset: yes`; clears memory and `events.jsonl` |

`/cells` and `/plan` report the actual file `month`, `source` (`model` or `fixture`), and `synthetic`
(`true` for the fixture). A request also echoes `requested_month`, which may differ from the file month
if no exact source exists. September events cannot alter the August fixture. For each accepted detection
in the served month, `/cells` replaces `posterior` and `score_b`, computes an approximate current
`ci_b`, and keeps the exported ensemble interval as `model_ci_b`. It recomputes `pct_b` and
`silence = pct_b − pct_a` over the served cells.

`/plan` keeps its generated pins when no candidate has new evidence. For an affected candidate, it
re-ranks the original nodes plus tree-pit options in same-month `model/out/placements.json`, scales
expected gain by the posterior risk change and remaining uncertainty, and enforces 100 m spacing.
It never creates a new location. The September demo H3 is in the model cells but outside its planner
candidate pool, so a demo event updates the map without moving a September plan pin. For a pin-movement
rehearsal, configure the node with the H3 of a current plan candidate.

## Posterior (plan §4)

Prior per cell uses a valid exported `posterior` when it is centred on `score_b` and has zero events.
Otherwise `alpha0 = score_b·n0`, `beta0 = (1−score_b)·n0`, `n0 = 10`; unknown H3 uses prior 0.2.
Each accepted rat event adds
`alpha += conf`, `n_events += 1`; `score_b_updated = alpha/(alpha+beta)`. Events with `conf < 0.5` or
`n_hits < 3` and person events are queued without an update. Exact duplicate deliveries are ignored and do not move
the posterior (env `BARN_OWL_MIN_CONF`, `BARN_OWL_MIN_HITS` to change). The August fixture has an
inconsistent old `posterior`, so the server uses the `score_b` fallback for that cell.

## State

In-memory ring buffer (2000 events) mirrored to `api/events.jsonl` (append-only, gitignored) and replayed
on start, so a server restart mid-rehearsal keeps the feed. One stdout line per event:

```
EVENT node=demo-01 h3=892a100d2c3ffff class=rat conf=0.91 n_hits=3 -> posterior mean 0.464 (a=5.10 b=5.81 n=1) [ok]
```

## Env

| Var | Default | |
|---|---|---|
| `BARN_OWL_DATA_DIR` | repo root | where `model/out/` and `city/` are looked up |
| `BARN_OWL_EVENTS_FILE` | `api/events.jsonl` | persistence file |
| `BARN_OWL_MIN_CONF` / `BARN_OWL_MIN_HITS` | 0.5 / 3 | posterior gate |
| `HOST` / `PORT` | 0.0.0.0 / 8000 | `run.sh` |

## Files

```
main.py              app + routes + pydantic Event model
store.py             state, file fallback chain, overlay, JSONL persistence, SSE fan-out
posterior.py         Beta-Binomial + percentile rank
fixtures/event.demo.json     the canned stage event (fake_event.sh)
fixtures/backtest.json       synthetic backtest (make_backtest.py regenerates it)
tests/test_api.py    pytest + httpx TestClient
```
