import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import create_app

DEMO_H3 = "892a100d2c3ffff"
REPO = Path(__file__).resolve().parents[2]


def event(conf=0.91, h3=DEMO_H3, ts="2026-09-26T14:02:11.000Z", **over):
    body = {"node_id": "demo-01", "h3": h3, "ts": ts, "class": "rat", "conf": conf, "n_hits": 3,
            "bbox": [0.331, 0.627, 0.216, 0.154], "crop_b64": "", "fw": "0.1.0"}
    body.update(over)
    return body


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["events"] == 0
    assert j["cells_source"].endswith("cells.fixture.json") or "model/out" in j["cells_source"]


def test_three_events_queue_order_and_posterior(client):
    base = client.get(f"/cells?month=2026-08").json()
    cell0 = next(c for c in base["cells"] if c["h3"] == DEMO_H3)
    prior_alpha, prior_beta = cell0["score_b"] * 10, (1 - cell0["score_b"]) * 10

    confs = [0.91, 0.80, 0.70]
    means = []
    for i, cf in enumerate(confs):
        r = client.post("/event", json=event(conf=cf, ts=f"2026-09-26T14:0{i}:00.000Z"))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True and j["h3"] == DEMO_H3
        assert j["posterior"]["n_events"] == i + 1
        expected_alpha = prior_alpha + sum(confs[: i + 1])
        assert j["posterior"]["alpha"] == pytest.approx(expected_alpha, abs=1e-3)
        assert j["posterior"]["beta"] == pytest.approx(prior_beta, abs=1e-3)
        assert j["score_b_updated"] == pytest.approx(expected_alpha / (expected_alpha + prior_beta), abs=1e-3)
        means.append(j["score_b_updated"])
    assert means == sorted(means)  # each rat sighting raises P(active)

    q = client.get("/queue?limit=10").json()["events"]
    assert [e["ts"] for e in q] == ["2026-09-26T14:02:00.000Z", "2026-09-26T14:01:00.000Z", "2026-09-26T14:00:00.000Z"]
    assert all("received_at" in e for e in q)
    assert q[0]["conf"] == 0.70 and q[0]["class"] == "rat"
    assert len(client.get("/queue?limit=2").json()["events"]) == 2

    cells = client.get("/cells?month=2026-08").json()
    assert cells["month"] == "2026-08" and "generated_at" in cells
    cell = next(c for c in cells["cells"] if c["h3"] == DEMO_H3)
    assert cell["last_event_at"] == "2026-09-26T14:02:00.000Z"
    assert cell["score_b"] == pytest.approx(means[-1], abs=1e-3)
    assert cell["posterior"]["n_events"] == 3
    assert cell["silence"] == pytest.approx(cell["pct_b"] - cell["pct_a"], abs=0.11)
    assert 0 <= cell["pct_b"] <= 100
    # contract keys intact
    for k in ["h3", "score_a", "score_b", "pct_a", "pct_b", "silence", "ci_b", "posterior", "reasons", "cd", "rmz",
              "n_inspections", "last_event_at"]:
        assert k in cell
    assert client.get("/health").json()["events"] == 3


def test_low_conf_is_queued_but_does_not_move_posterior(client):
    r = client.post("/event", json=event(conf=0.3))
    assert r.status_code == 200 and r.json()["posterior"]["n_events"] == 0
    assert len(client.get("/queue").json()["events"]) == 1


def test_unknown_h3_accepted_with_prior(client):
    r = client.post("/event", json=event(h3="892a1008003ffff"))
    assert r.status_code == 200
    j = r.json()
    assert j["posterior"]["alpha"] == pytest.approx(0.2 * 10 + 0.91, abs=1e-3)
    assert j["posterior"]["beta"] == pytest.approx(8.0, abs=1e-3)


@pytest.mark.parametrize("bad", [
    {"bbox": [212, 301, 138, 74]},        # pixels, not normalised
    {"bbox": [0.1, 0.2, 0.3]},            # 3 values
    {"conf": 1.5},
    {"class": "dog"},
    {"h3": "not-an-h3"},
    {"extra": 1},
])
def test_malformed_event_422(client, bad):
    r = client.post("/event", json=event(**bad))
    assert r.status_code == 422, r.text


def test_bad_json_400(client):
    r = client.post("/event", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code in (400, 422)


def test_reset_guarded_and_works(client):
    client.post("/event", json=event())
    assert client.delete("/events").status_code == 403
    r = client.delete("/events", headers={"X-Demo-Reset": "yes"})
    assert r.status_code == 200 and r.json()["cleared"] == 1
    assert client.get("/queue").json()["events"] == []
    cell = next(c for c in client.get("/cells").json()["cells"] if c["h3"] == DEMO_H3)
    assert cell["last_event_at"] != "2026-09-26T14:02:11.000Z"


def test_persistence_survives_restart(tmp_path):
    f = tmp_path / "events.jsonl"
    with TestClient(create_app(data_dir=REPO, events_file=f)) as c:
        c.post("/event", json=event())
        c.post("/event", json=event(conf=0.8))
    assert len(f.read_text().splitlines()) == 2
    with TestClient(create_app(data_dir=REPO, events_file=f)) as c:
        assert c.get("/health").json()["events"] == 2
        cell = next(x for x in c.get("/cells").json()["cells"] if x["h3"] == DEMO_H3)
        assert cell["posterior"]["n_events"] == 2


def test_plan_truncates(client):
    j = client.get("/plan?month=2026-08&k=3").json()
    assert j["month"] == "2026-08" and j["k"] == 3 and len(j["nodes"]) == 3
    assert j["nodes"][0]["rank"] == 1 and j["nodes"][0]["h3"] == DEMO_H3
    for k in ["rank", "h3", "lat", "lon", "tree_id", "expected_gain", "silence", "reason"]:
        assert k in j["nodes"][0]


def test_bad_month_422(client):
    assert client.get("/cells?month=2026-13").status_code == 422
    assert client.get("/cells?month=Aug").status_code == 422


def test_backtest_fixture_loads(client):
    j = client.get("/backtest").json()
    assert j["window"][0] == "2016-01" and j["k"] == 50
    assert len(j["series"]) >= 120
    s0 = j["series"][0]
    assert set(s0) == {"month", "precision_silent", "precision_311", "n_positives"}
    assert j["summary"]["lift"] > 1.0
    assert j["summary"]["mean_precision_silent"] > j["summary"]["mean_precision_311"]
    if "model/out" not in j["source"]:
        assert j["synthetic"] is True


def test_stream_hello(client):
    # TestClient buffers the whole body, so only the bounded form is testable here; the live push is
    # covered by the end-to-end curl in the README (curl -N 'localhost:8000/stream?limit=1' + fake_event.sh).
    r = client.get("/stream?limit=0")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text.startswith("event: hello\ndata: ")
    assert json.loads(r.text.split("data: ", 1)[1].split("\n")[0])["events"] == 0


def test_cors_header(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")
