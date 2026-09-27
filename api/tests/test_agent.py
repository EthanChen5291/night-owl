"""Assistant tools must describe the same month and live ranking as the map."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import Data, t_city_overview, t_get_cell, t_node_sites, t_search_cells
from main import create_app

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as c:
        yield c


def _event(h3: str) -> dict:
    return {"node_id": "agent-test", "h3": h3, "ts": "2026-09-27T01:15:00.000Z", "class": "rat",
            "conf": 0.95, "n_hits": 3, "bbox": [0.2, 0.2, 0.3, 0.3], "crop_b64": "", "fw": "test"}


def test_agent_sites_follow_live_plan_and_reset(client):
    store = client.app.state.store
    data = Data(store, "2026-09", 20)
    before = client.get("/plan?month=2026-09&k=20").json()
    sites, _ = t_node_sites(data, {"limit": 20})
    assert sites["month"] == before["month"]
    assert [(n["h3"], n["rank"]) for n in sites["sites"]] == [
        (n["h3"], n["rank"]) for n in before["nodes"]]

    target = before["nodes"][-1]["h3"]
    assert client.post("/event", json=_event(target)).json()["accepted"] is True
    after = client.get("/plan?month=2026-09&k=20").json()
    live_sites, _ = t_node_sites(data, {"limit": 20})
    assert live_sites["replanned"] is True
    assert [(n["h3"], n["rank"]) for n in live_sites["sites"]] == [
        (n["h3"], n["rank"]) for n in after["nodes"]]
    assert next(n["rank"] for n in live_sites["sites"] if n["h3"] == target) < 20

    assert client.delete("/events", headers={"X-Demo-Reset": "yes"}).status_code == 200
    reset_sites, _ = t_node_sites(data, {"limit": 20})
    assert [(n["h3"], n["rank"]) for n in reset_sites["sites"]] == [
        (n["h3"], n["rank"]) for n in before["nodes"]]


def test_agent_tools_follow_requested_and_actual_source_month(client):
    store = client.app.state.store
    august = Data(store, "2026-08", 3)
    august_cells = client.get("/cells?month=2026-08").json()
    august_plan = client.get("/plan?month=2026-08&k=3").json()
    assert august.cells()[0] == august_cells["month"] == "2026-08"
    sites, _ = t_node_sites(august, {"limit": 20})
    assert sites["month"] == august_plan["month"]
    assert sites["source"] == august_plan["source"] == "fixture"
    assert len(sites["sites"]) == 3
    overview, _ = t_city_overview(august, {})
    search, _ = t_search_cells(august, {"limit": 1})
    cell, _ = t_get_cell(august, {"h3": august_cells["cells"][0]["h3"]})
    assert overview["month"] == search["month"] == cell["month"] == "2026-08"

    missing = Data(store, "2025-01", 3)
    fallback_cells = client.get("/cells?month=2025-01").json()
    fallback_plan = client.get("/plan?month=2025-01&k=3").json()
    assert missing.cells()[0] == fallback_cells["month"] != "2025-01"
    sites, _ = t_node_sites(missing, {"limit": 20})
    assert sites["month"] == fallback_plan["month"]
    assert sites["requested_month"] == "2025-01"


def test_agent_chat_rejects_bad_month_and_plan_k(client, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "local-test-only")
    for body in ({"month": "2026-13"}, {"month": "yesterday"}, {"plan_k": -1}, {"plan_k": True}):
        assert client.post("/agent/chat", json={"messages": [], **body}).status_code == 400


def test_agent_chat_passes_selected_context_to_tools(client, monkeypatch):
    import agent

    monkeypatch.setenv("XAI_API_KEY", "local-test-only")

    async def local_agent(data, messages, emit, channel):
        sites, _ = t_node_sites(data, {"limit": 20})
        await emit({"type": "delta", "text": f"{sites['month']}:{len(sites['sites'])}"})

    monkeypatch.setattr(agent, "run_agent", local_agent)
    response = client.post("/agent/chat", json={"messages": [{"role": "user", "content": "sites"}],
                                                 "month": "2026-08", "plan_k": 3})
    assert response.status_code == 200
    assert '"text": "2026-08:3"' in response.text
