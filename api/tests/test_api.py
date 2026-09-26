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
    base = client.get(f"/cells?month=2026-09").json()
    cell0 = next(c for c in base["cells"] if c["h3"] == DEMO_H3)
    prior_alpha, prior_beta = cell0["posterior"]["alpha"], cell0["posterior"]["beta"]

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

    cells = client.get("/cells?month=2026-09").json()
    assert cells["month"] == "2026-09" and "generated_at" in cells
    cell = next(c for c in cells["cells"] if c["h3"] == DEMO_H3)
    assert cell["last_event_at"] == "2026-09-26T14:02:00.000Z"
    assert cell["score_b"] == pytest.approx(means[-1], abs=1e-3)
    assert cell["posterior"]["n_events"] == 3
    assert cell["ci_b"] != cell["model_ci_b"]
    assert cell["ci_b"][0] <= cell["score_b"] <= cell["ci_b"][1]
    assert cell["ci_b_basis"] == "sensor_posterior_wilson_approx"
    assert cell["silence"] == pytest.approx(cell["pct_b"] - cell["pct_a"], abs=0.11)
    assert 0 <= cell["pct_b"] <= 100
    # contract keys intact
    for k in ["h3", "score_a", "score_b", "pct_a", "pct_b", "silence", "ci_b", "posterior", "reasons", "cd", "rmz",
              "n_inspections", "last_event_at"]:
        assert k in cell
    assert client.get("/health").json()["events"] == 3


def test_low_conf_is_queued_but_does_not_move_posterior(client):
    before = client.get("/cells?month=2026-09").json()
    r = client.post("/event", json=event(conf=0.3))
    assert r.status_code == 200 and r.json()["posterior"]["n_events"] == 0
    assert len(client.get("/queue").json()["events"]) == 1
    after = client.get("/cells?month=2026-09").json()
    assert next(c for c in after["cells"] if c["h3"] == DEMO_H3) == next(c for c in before["cells"] if c["h3"] == DEMO_H3)


def test_person_event_is_queued_without_update(client):
    before = client.get("/plan?month=2026-09&k=10").json()["nodes"]
    assert client.post("/event", json=event(**{"class": "person"})).json()["posterior"]["n_events"] == 0
    assert len(client.get("/queue").json()["events"]) == 1
    assert client.get("/plan?month=2026-09&k=10").json()["nodes"] == before


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
    {"h3": "fffffffffffffff"},
    {"extra": 1},
])
def test_malformed_event_400(client, bad):
    r = client.post("/event", json=event(**bad))
    assert r.status_code == 400, r.text


def test_bad_json_400(client):
    r = client.post("/event", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400


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


def test_duplicate_delivery_and_restart_are_idempotent(tmp_path):
    f = tmp_path / "events.jsonl"
    body = event()
    with TestClient(create_app(data_dir=REPO, events_file=f)) as c:
        first = c.post("/event", json=body).json()
        second = c.post("/event", json=body).json()
        assert second["posterior"] == first["posterior"]
        assert len(c.get("/queue").json()["events"]) == 1
    assert len(f.read_text().splitlines()) == 1
    with TestClient(create_app(data_dir=REPO, events_file=f)) as c:
        assert c.post("/event", json=body).json()["posterior"] == first["posterior"]
        assert len(c.get("/queue").json()["events"]) == 1


def test_timestamp_normalization_deduplicates_equivalent_utc_forms(client):
    first = client.post("/event", json=event(ts="2026-09-26T14:02:11Z"))
    second = client.post("/event", json=event(ts="2026-09-26T14:02:11.000+00:00"))
    assert first.status_code == second.status_code == 200
    assert first.json()["posterior"] == second.json()["posterior"]
    assert client.get("/queue").json()["events"][0]["ts"] == "2026-09-26T14:02:11.000Z"
    assert len(client.get("/queue").json()["events"]) == 1


def test_month_sources_and_historical_overlay(client):
    august = client.get("/cells?month=2026-08").json()
    assert august["month"] == august["requested_month"] == "2026-08"
    assert august["source"] == "fixture" and august["synthetic"] is True
    assert client.get("/plan?month=2026-08").json()["source"] == "fixture"
    assert client.get("/cells?month=2025-01").json()["month"] == "2026-09"
    assert client.get("/cells?month=2025-01").json()["requested_month"] == "2025-01"
    assert client.post("/event", json=event()).status_code == 200
    assert client.get("/cells?month=2026-08").json()["cells"] == august["cells"]
    assert client.get("/plan?month=2026-08").json()["nodes"] == json.loads((REPO / "city/plan.fixture.json").read_text())["nodes"]


def test_event_outside_candidate_pool_does_not_move_pins(client):
    before = client.get("/plan?month=2026-09&k=10").json()
    assert before["replanned"] is False
    assert client.post("/event", json=event()).status_code == 200
    after = client.get("/plan?month=2026-09&k=10").json()
    assert after["nodes"] == before["nodes"]
    assert after["replanned"] is False


def test_sensor_event_reranks_existing_tree_sites_and_reset_restores(client):
    before = client.get("/plan?month=2026-09&k=20").json()["nodes"]
    target = before[-1]
    old_sites = {(n["h3"], n["tree_id"]): (n["lat"], n["lon"]) for n in before}
    assert client.post("/event", json=event(h3=target["h3"])).status_code == 200
    changed = client.get("/plan?month=2026-09&k=20").json()["nodes"]
    assert changed != before
    assert next(n for n in changed if n["h3"] == target["h3"])["rank"] < target["rank"]
    assert all((n["lat"], n["lon"]) == old_sites[(n["h3"], n["tree_id"])]
               for n in changed if (n["h3"], n["tree_id"]) in old_sites)
    assert client.delete("/events", headers={"X-Demo-Reset": "yes"}).status_code == 200
    assert client.get("/plan?month=2026-09&k=20").json()["nodes"] == before


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
    assert len(j["series"]) >= 119
    s0 = j["series"][0]
    assert {"month", "precision_silent", "precision_311", "n_positives"} <= set(s0)
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
