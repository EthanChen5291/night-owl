"""The dashboard chat tool loop uses local data and mocked Responses, never a provider request."""
import asyncio
import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

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

    def provider(body, emit=None):
        inputs.append(body)
        return next(responses)

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        response = client.post("/dashboards/chat", json={"message": "Compare borough risk", "history": []})
    assert response.status_code == 200
    events = frames(response)
    types = [e["type"] for e in events]
    assert types[-2:] == ["delta", "done"] and types.index("dashboard") < types.index("delta")
    assert [e["text"] for e in events if e["type"] == "step"] == ["Queried modelled NYC cells", "Built dashboard"]
    artifact = next(e["dashboard"] for e in events if e["type"] == "dashboard")
    assert artifact["results"]["risk"]["total_rows"] == 5
    assert all(body["store"] is False for body in inputs)
    assert [tool["name"] for tool in inputs[0]["tools"]] == ["query_data", "publish_dashboard"]
    query_schema = inputs[0]["tools"][0]["parameters"]["properties"]["query"]["properties"]
    assert {"filters", "split_by"} <= set(query_schema) and "borough_months" in query_schema["dataset"]["enum"]
    assert '"periods"' in inputs[0]["input"][0]["content"]
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "q1" for item in inputs[1]["input"])
    assert any(item.get("type") == "function_call_output" and item.get("call_id") == "p1" for item in inputs[2]["input"])


def test_chat_streams_thinking_and_text_as_they_arrive(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    rounds = iter([
        (["Checking borough data."], [], {"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p1",
                                                        "arguments": json.dumps({"spec": SPEC})}]}),
        ([], ["Brooklyn ", "leads."], {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Brooklyn leads."}]}]}),
    ])

    def provider(body, emit):
        thinking, deltas, response = next(rounds)
        for text in thinking:
            emit("thinking", text)
        for text in deltas:
            emit("delta", text)
        return response

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        events = frames(client.post("/dashboards/chat", json={"message": "Compare borough risk"}))
    assert [e["text"] for e in events if e["type"] == "thinking"] == ["Checking borough data."]
    assert [e["text"] for e in events if e["type"] == "delta"] == ["Brooklyn ", "leads."], "streamed text is not repeated"
    types = [e["type"] for e in events]
    assert types.index("dashboard") < types.index("delta") and types[-1] == "done"


def test_chat_rejects_bad_context_and_does_not_call_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    monkeypatch.setattr(dashboard_agent, "_provider", lambda *_: (_ for _ in ()).throw(AssertionError("provider called")))
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

    def provider(body, emit=None):
        inputs.append(body)
        return next(responses)

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        events = frames(client.post("/dashboards/chat", json={"message": "Build a chart"}))
    assert any(e["type"] == "dashboard" for e in events)
    q_result = next(item["output"] for item in inputs[1]["input"] if item.get("call_id") == "q1" and item.get("type") == "function_call_output")
    assert "error" in json.loads(q_result)


def test_malformed_query_argument_recovers_and_publishes(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    inputs = []
    responses = iter([
        {"output": [{"type": "function_call", "name": "query_data", "call_id": "q1",
                     "arguments": json.dumps({"query": ["bad shape"]})}]},
        {"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p1",
                     "arguments": json.dumps({"spec": SPEC})}]},
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]},
    ])

    def provider(body, _emit):
        inputs.append(body)
        return next(responses)

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        events = frames(client.post("/dashboards/chat", json={"message": "Build a chart"}))
    assert any(event["type"] == "dashboard" for event in events)
    assert events[-1]["type"] == "done"
    q_result = next(item["output"] for item in inputs[1]["input"]
                    if item.get("type") == "function_call_output" and item.get("call_id") == "q1")
    assert "error" in json.loads(q_result)
    assert any(event["type"] == "step" and event.get("error") for event in events)


def test_clarification_is_not_an_error_and_last_round_publish_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        monkeypatch.setattr(dashboard_agent, "_provider", lambda *_: {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Which borough?"}]}]})
        reply = frames(client.post("/dashboards/chat", json={"message": "Show my area"}))
        assert [event["type"] for event in reply][-2:] == ["delta", "done"]

        calls = iter([{"output": [{"type": "function_call", "name": "query_data", "call_id": f"q{i}",
                                    "arguments": json.dumps({"query": QUERY})}]} for i in range(4)] +
                     [{"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p5",
                                    "arguments": json.dumps({"spec": SPEC})}]}])
        monkeypatch.setattr(dashboard_agent, "_provider", lambda *_: next(calls))
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


def test_provider_parses_sse_and_only_streams_summary(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    lines = [
        b": keepalive\n", b"\n",
        b'data: {"type":"response.reasoning_text.delta","delta":"hidden"}\n', b"\n",
        b'data: {"type":"response.reasoning_summary_text.delta","delta":"Checking"}\n', b"\n",
        b'data: {"type":"response.output_text.delta","delta":"Ready"}\n', b"\n",
        b'data: {"type":"response.completed",\n', b'data: "response":{"output":[]}}\n', b"\n",
        b"data: [DONE]\n", b"\n",
    ]

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def __iter__(self):
            return iter(lines)

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(dashboard_agent.urllib.request, "build_opener", lambda *_: Opener())
    emitted = []
    result = dashboard_agent._provider({"model": "mock", "input": []}, lambda kind, text: emitted.append((kind, text)))
    assert result == {"output": []}
    assert emitted == [("thinking", "Checking"), ("delta", "Ready")]


@pytest.mark.parametrize("lines,expected", [
    ([b'data: {"type":"response.failed","secret":"do-not-show"}\n', b"\n"],
     "xAI response did not complete"),
    ([b"data: invalid-json\n", b"\n"], "xAI returned an invalid stream"),
    ([b'data: {"type":"response.output_text.delta","delta":"partial"}\n', b"\n", b"data: [DONE]\n"],
     "xAI returned an invalid response"),
])
def test_provider_rejects_failed_malformed_or_incomplete_sse(monkeypatch, lines, expected):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def __iter__(self):
            return iter(lines)

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(dashboard_agent.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(dashboard_agent.DashboardError, match=expected) as error:
        dashboard_agent._provider({"model": "mock", "input": []})
    assert "do-not-show" not in str(error.value)


def test_round_cancellation_stops_producer_without_later_round(monkeypatch):
    stopped = threading.Event()
    calls = []

    def provider(body, emit):
        calls.append(body)
        try:
            while True:
                emit("delta", "x")
        except dashboard_agent._RoundStopped:
            stopped.set()
            return {"output": []}

    monkeypatch.setattr(dashboard_agent, "_provider", provider)

    async def cancel_after_first_delta():
        stream = dashboard_agent._round({"model": "mock"})
        assert await asyncio.wait_for(anext(stream), 2) == ("delta", "x")
        await stream.aclose()

    asyncio.run(cancel_after_first_delta())
    assert stopped.wait(2)
    assert len(calls) == 1


def test_unstreamed_final_text_after_tool_round_is_not_lost(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    rounds = iter([
        ({"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p1",
                      "arguments": json.dumps({"spec": SPEC})}]}, "Working."),
        ({"output": [{"type": "message", "content": [{"type": "output_text", "text": "Final result."}]}]}, ""),
    ])

    def provider(_body, emit):
        result, delta = next(rounds)
        if delta:
            emit("delta", delta)
        return result

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        events = frames(client.post("/dashboards/chat", json={"message": "Build a chart"}))
    assert any(event["type"] == "dashboard" for event in events)
    assert "Final result." in "".join(event["text"] for event in events if event["type"] == "delta")


def test_query_budget_skips_extra_queries_but_still_publishes(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "mock-only")
    dashboard_agent._hits.clear()
    inputs = []
    too_many = [{"type": "function_call", "name": "query_data", "call_id": f"q{i}", "arguments": json.dumps({"query": QUERY})}
                for i in range(dashboard_agent.MAX_QUERIES + 2)]
    responses = iter([
        {"output": too_many},
        {"output": [{"type": "function_call", "name": "publish_dashboard", "call_id": "p1", "arguments": json.dumps({"spec": SPEC})}]},
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]},
    ])

    def provider(body, emit=None):
        inputs.append(body)
        return next(responses)

    monkeypatch.setattr(dashboard_agent, "_provider", provider)
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        response = client.post("/dashboards/chat", json={"message": "Everything at once", "history": []})
    events = frames(response)
    steps = [e for e in events if e["type"] == "step"]
    assert sum(1 for s in steps if s["text"] == "Queried modelled NYC cells") == dashboard_agent.MAX_QUERIES
    assert sum(1 for s in steps if s["text"] == "Query skipped") == 2
    assert any(e["type"] == "dashboard" for e in events) and not any(e["type"] == "error" for e in events)
    # The provider sees one shared input list, so filter to the query outputs of the first round.
    outputs = [item for item in inputs[1]["input"] if item.get("type") == "function_call_output" and item["call_id"].startswith("q")]
    assert len(outputs) == dashboard_agent.MAX_QUERIES + 2 and "budget" in outputs[-1]["output"] and "rows" in outputs[0]["output"]
