# NightOwl API

This FastAPI server connects the Pi detector, Sanjavan's city-model exports, and the web app. It accepts
the event contract in [the master plan](../plan/master-plan.md), keeps a separate probability estimate
for each H3 cell and month, and serves the updated cells and site plan to the map. The detector targets
the team's plush prop in room light; an event is sensor evidence, not a retrained city model.

## Run

```
./api/run.sh                                   # 0.0.0.0:8000, the Pi posts to http://192.168.7.1:8000
# or
uv run --project api uvicorn main:app --app-dir api --host 0.0.0.0 --port 8000
```

Tests: `uv run --project api pytest -q api/tests`

To rehearse the map without the Pi, use this canned event against an isolated API:

```
./api/fake_event.sh                  # POST fixtures/event.demo.json to localhost:8000 with ts = now
API=http://192.168.7.1:8000 ./api/fake_event.sh
```

Reset between rehearsals: `curl -X DELETE -H 'X-Demo-Reset: yes' localhost:8000/events`

The scripts below also post staged sightings with fresh timestamps. Both change the persisted queue and
cell probabilities. Reset afterward. Their events are demo fixtures, not Pi detections or evaluation evidence.

```
./api/fake_sightings.py        # 15 sightings: grayscale crops of the rat prop from the team's own footage
./api/real_sightings.py        # 17 staged sightings with wild rat and mouse photo crops
```

`fake_sightings.py` uses plush-prop crops from team footage. `real_sightings.py` uses openly licensed
Wikimedia Commons photos, cut to the node's crop format. Its node IDs, H3 cells, and times are invented;
some photos show mice although the event schema calls the class `rat`. It is an illustration, not a
sample from the detector. The original photos can be fetched with `--fetch` into the gitignored
`api/fixtures/rodents/`. The baked crops are in `fixtures/events.real.json`, with authors, licenses,
and source links in `fixtures/rodents.credits.json`. Attribute CC BY and CC BY-SA images on slides.

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
| POST | `/agent/chat` | Optional assistant. Web requests send `month` and `plan_k`; its cell and site tools read the same live Store as the map. Requires `XAI_API_KEY`. |

`/cells` and `/plan` report the actual file `month`, `source` (`model` or `fixture`), and `synthetic`
(`true` for the fixture). A request also echoes `requested_month`, which may differ from the file month
if no exact source exists. September events cannot alter the August fixture. For each accepted detection
in the served month, `/cells` replaces `posterior` and `score_b`, computes an approximate current
`ci_b`, and keeps the exported ensemble interval as `model_ci_b`. It recomputes `pct_b` and
`silence = pct_b − pct_a` over the served cells.

`/plan` keeps its generated pins when no candidate has new evidence. For an affected candidate, it
re-ranks the original nodes plus tree-pit options in same-month `model/out/placements.json`, scales
expected gain by the posterior risk change and remaining uncertainty, and enforces 100 m spacing.
It never creates a new location. A detection in a cell outside the planner's candidate pool can update
that cell without moving a plan pin. The optional assistant uses the same selected month and site budget
as the web app and reports the actual source month when the requested export is unavailable.

## Posterior (plan §4)

Prior per cell uses a valid exported `posterior` when it is centred on `score_b` and has zero events.
Otherwise `alpha0 = score_b·n0`, `beta0 = (1−score_b)·n0`, `n0 = 10`; unknown H3 uses prior 0.2.
Each accepted rat event adds
`alpha += conf`, `n_events += 1`; `score_b_updated = alpha/(alpha+beta)`. Events with `conf < 0.5` or
`n_hits < 3` and person events are queued without an update. Exact duplicate deliveries are ignored and do not move
the posterior (env `NIGHT_OWL_MIN_CONF`, `NIGHT_OWL_MIN_HITS` to change). The August fixture has an
inconsistent old `posterior`, so the server uses the `score_b` fallback for that cell.

## State

In-memory ring buffer (2000 events) mirrored to `api/events.jsonl` (append-only, gitignored) and replayed
on start, so a server restart mid-rehearsal keeps the feed. One stdout line per event:

```
EVENT node=demo-01 h3=892a100d2c3ffff class=rat conf=0.91 n_hits=3 -> posterior mean 0.464 (a=5.10 b=5.81 n=1) [ok]
```

## Env

`NIGHT_OWL_*` settings take precedence. The matching legacy `BARN_OWL_*` names
remain supported as fallbacks, including data paths, posterior gates, ring size,
and the agent dashboard URL. Existing services do not need their configuration renamed.

| Var | Default | |
|---|---|---|
| `NIGHT_OWL_DATA_DIR` | repo root | where `model/out/` and `city/` are looked up |
| `NIGHT_OWL_EVENTS_FILE` | `api/events.jsonl` | persistence file |
| `NIGHT_OWL_MIN_CONF` / `NIGHT_OWL_MIN_HITS` | 0.5 / 3 | posterior gate |
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
