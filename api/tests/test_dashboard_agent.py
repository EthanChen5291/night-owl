"""The dashboard chat tool loop uses local data and mocked Responses, never a provider request."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import dashboard_agent
from main import create_app

REPO = Path(__file__).resolve().parents[2]
QUERY = {"dataset": "cells", "group_by": "borough", "metrics": ["score_b"], "aggregation": "mean"}
SPEC = {"title": "Borough risk", "description": "Current model month", "cards": [{
    "id": "risk", "title": "Mean active-sign risk", "kind": "bar", "query": QUERY,
    "x": "borough", "y": ["score_b"]}]}


def frames(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_chat_tool_loop_emits_dashboard_from_local_data(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    inputs = []
    responses = iter([
        {"output": [{"type": "function_call", "name": "query_data", "call_id": "q1",
                     "arguments": json.dumps({"query": QUERY})}]},
        {"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p1",
                     "arguments": json.dumps({"spec": SPEC})}]},
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "The Bronx has lower mean risk than Manhattan."}]}]},
    ])

    def provider(body):
        inputs.append(body)
        return next(responses)

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        response = client.post("/dashboards/chat", json={"message": "Compare borough risk", "history": []})
    assert response.status_code == 200
    events = frames(response)
    assert [e["type"] for e in events][-3:] == ["dashboard", "delta", "done"]
    artifact = next(e["dashboard"] for e in events if e["type"] == "dashboard")
    assert artifact["results"]["risk"]["total_rows"] == 5
    assert all(body["store"] is False for body in inputs)
    assert [tool["name"] for tool in inputs[0]["tools"]] == ["query_data", "publish_dashboard"]
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "q1" for item in inputs[1]["input"])
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "p1" for item in inputs[2]["input"])


def test_chat_rejects_bad_context_and_does_not_call_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    monkeypatch.setattr(dashboard_agent, "_provider", lambda _: (_ for _ in ()).throw(AssertionError("provider called")))
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        bad = [{"message": "", "history": []},
               {"message": "hello", "history": [{"role": "tool", "content": "x"}]},
               {"message": "hello", "unexpected": True},
               {"message": "hello", "dashboard": {"cards": [{"id": "risk", "x": "borough", "y": 3}]},
                "selection": {"card_id": "risk", "field": "borough", "value": "Bronx"}},
               {"message": "hello", "dashboard": SPEC, "selection": {"card_id": "risk", "field": "bad", "value": "Bronx"}}]
        for body in bad:
            assert client.post("/dashboards/chat", json=body).status_code == 400


def test_chat_reports_tool_error_then_can_publish(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    inputs = []
    responses = iter([
        {"output": [{"type": "function_call", "name": "query_data", "call_id": "q1",
                     "arguments": json.dumps({"query": {**QUERY, "metrics": ["made_up"]}})}]},
        {"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p1",
                     "arguments": json.dumps({"spec": SPEC})}]},
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done.", "annotations": []}]}]},
    ])

    def provider(body):
        inputs.append(body)
        return next(responses)

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        events = frames(client.post("/dashboards/chat", json={"message": "Build a chart"}))
    assert any(e["type"] == "dashboard" for e in events)
    q_result = next(item["output"] for item in inputs[1]["input"] if item.get("call_id") == "q1" and item.get("type") == "function_call_output")
    assert "error" in json.loads(q_result)


def test_clarification_is_not_an_error_and_last_round_publish_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        monkeypatch.setattr(dashboard_agent, "_provider", lambda _: {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Which borough?"}]}]})
        reply = frames(client.post("/dashboards/chat", json={"message": "Show my area"}))
        assert [event["type"] for event in reply][-2:] == ["delta", "done"]

        calls = iter([{"output": [{"type": "function_call", "name": "query_data", "call_id": f"q{i}",
                                    "arguments": json.dumps({"query": QUERY})}]} for i in range(4)] +
                     [{"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p5",
                                    "arguments": json.dumps({"spec": SPEC})}]}])
        monkeypatch.setattr(dashboard_agent, "_provider", lambda _: next(calls))
        published = frames(client.post("/dashboards/chat", json={"message": "Show borough risk"}))
        assert any(event["type"] == "dashboard" for event in published)
        assert published[-1]["type"] == "done"


def test_provider_redirect_is_rejected(monkeypatch):
    import urllib.error

    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    assert dashboard_agent._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example") is None
    class RedirectingOpener:
        def open(self, *_args, **_kwargs):
            raise urllib.error.HTTPError("https://other.example", 302, "redirect", {}, None)
    monkeypatch.setattr(dashboard_agent.urllib.request, "build_opener", lambda *_: RedirectingOpener())
    try:
        dashboard_agent._provider({"model": "mock", "input": []})
    except dashboard_agent.DashboardError as exc:
        assert str(exc) == "xAI request returned HTTP 302"
    else:
        raise AssertionError("redirect accepted")
