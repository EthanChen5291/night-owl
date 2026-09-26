# api/ — Barn Owl demo hub

FastAPI server that sits between the Pi node, the model output and the web app. It serves the frozen JSON
contract (`plan/master-plan.md` §6), takes `POST /event` from `vision/pi/detect.py`, keeps one
Beta-Binomial posterior per H3 cell (plan §4) and overlays it on `/cells` so the map moves when the prop
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

## Endpoints (contract §6)

| Method | Path | Notes |
|---|---|---|
| GET | `/cells?month=YYYY-MM` | `model/out/cells_<month>.json` → `model/out/cells.json` → `city/cells.fixture.json`, with the live posterior overlay |
| GET | `/plan?month&k` | `model/out/plan_<month>.json` → `model/out/plan.json` → `city/plan.fixture.json`, truncated to `k` |
| GET | `/queue?limit=50` | live events, newest first, `received_at` added. Starts empty (the queue fixture is for the frontend only) |
| POST | `/event` | the 9-key body; 422 on bad shape (bbox must be 0–1, class `rat`/`person`, conf 0–1), 400 on bad JSON |
| GET | `/backtest` | `model/out/backtest.json` → `api/fixtures/backtest.json` (synthetic, flagged `"synthetic": true`) |
| GET | `/stream` | Server-Sent Events: `hello` on connect, `event` per POST, `reset` on DELETE; keepalive every 15 s |
| GET | `/health` | `{"ok":true,"events":n,"cells_source":path}` |
| DELETE | `/events` | needs header `X-Demo-Reset: yes`; clears memory and `events.jsonl` |

`/cells` overlay: for every cell that has received an accepted event, `posterior` is replaced,
`score_b` becomes the posterior mean, `last_event_at` is the event `ts`, then `pct_b` and
`silence = pct_b − pct_a` are recomputed over the whole set (same percentile-rank rule as
`city/make_fixture.py`).

## Posterior (plan §4)

Prior per cell `alpha0 = score_b·n0`, `beta0 = (1−score_b)·n0`, `n0 = 10`, `score_b` read from the cells
file the first time the cell gets an event (unknown h3 → prior 0.2, logged). Each accepted event adds
`alpha += conf`, `n_events += 1`; `score_b_updated = alpha/(alpha+beta)`. Events with `conf < 0.5` or
`n_hits < 3` are queued and logged but do not move the posterior (env `BARN_OWL_MIN_CONF`,
`BARN_OWL_MIN_HITS` to change). The demo cell starts at `n_events = 0` on the server regardless of what
the cells file says, so the stage line "0 → 1" holds.

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
