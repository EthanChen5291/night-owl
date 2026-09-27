"""Stored chat threads (api/chat_store.py via /agent/chat and /agent/threads), with a scripted fake Grok."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent
from main import create_app

REPO = Path(__file__).resolve().parents[2]
ME = {"x-chat-client": "browser-aaaaaaaaaaaaaaaa"}
OTHER = {"x-chat-client": "browser-bbbbbbbbbbbbbbbb"}


class FakeGrok:
    """Stands in for agent._chunks: each call to the model plays the next script entry.
    An entry is either answer text, or ("call", tool_name, args) for one tool call."""

    def __init__(self):
        self.script: list = []
        self.bodies: list[dict] = []

    async def __call__(self, body):
        self.bodies.append(json.loads(json.dumps(body)))
        step = self.script.pop(0) if self.script else "ok"
        if isinstance(step, tuple):
            _, name, args = step
            yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"call-{name}", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}
        else:
            for part in (step[: len(step) // 2], step[len(step) // 2:]):
                yield {"choices": [{"delta": {"content": part}}]}


@pytest.fixture
def grok(monkeypatch):
    fake = FakeGrok()
    monkeypatch.setattr(agent, "_chunks", fake)
    monkeypatch.setenv("XAI_API_KEY", "test")
    agent._hits.clear()
    return fake


@pytest.fixture
def client(tmp_path, grok):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as c:
        yield c


def chat(client, body, headers=ME):
    with client.stream("POST", "/agent/chat", json=body, headers=headers) as r:
        assert r.status_code == 200, r.read()
        return [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]


def test_thread_is_created_saved_and_continued(client, grok):
    grok.script = ["Hello from Grok."]
    events = chat(client, {"thread_id": None, "text": "Where are the silent blocks?"})
    tid = next(e for e in events if e["type"] == "thread")["id"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello from Grok."

    t = client.get(f"/agent/threads/{tid}", headers=ME).json()
    assert t["thread"]["title"] == "Where are the silent blocks?"
    assert [(x["role"], x["text"]) for x in t["turns"]] == [("user", "Where are the silent blocks?"), ("bot", "Hello from Grok.")]

    # the second question sends only the new text; the server supplies the earlier turn to the model
    grok.script = ["Second answer."]
    chat(client, {"thread_id": tid, "text": "And in Brooklyn?"})
    sent = [m["content"] for m in grok.bodies[-1]["messages"] if m["role"] != "system"]
    assert sent == ["Where are the silent blocks?", "Hello from Grok.", "And in Brooklyn?"]
    listed = client.get("/agent/threads", headers=ME).json()["threads"]
    assert [(x["id"], x["questions"]) for x in listed] == [(tid, 2)]


def test_threads_belong_to_their_browser(client, grok):
    events = chat(client, {"thread_id": None, "text": "hi"})
    tid = next(e for e in events if e["type"] == "thread")["id"]
    assert client.get(f"/agent/threads/{tid}", headers=OTHER).status_code == 404
    assert client.get("/agent/threads", headers=OTHER).json()["threads"] == []
    assert client.delete(f"/agent/threads/{tid}", headers=OTHER).status_code == 404
    with client.stream("POST", "/agent/chat", json={"thread_id": tid, "text": "x"}, headers=OTHER) as r:
        assert r.status_code == 404
    assert client.get("/agent/threads", headers={}).status_code == 400  # no browser id at all


def test_browser_tool_round_is_stored_as_one_answer(client, grok):
    grok.script = [("call", "set_map_mode", {"mode": "silence"}), "Switched to silence."]
    first = chat(client, {"thread_id": None, "text": "show silence"})
    tid = next(e for e in first if e["type"] == "thread")["id"]
    calls = next(e for e in first if e["type"] == "client_tools")["calls"]
    assert [c["name"] for c in calls] == ["set_map_mode"]
    bot = client.get(f"/agent/threads/{tid}", headers=ME).json()["turns"][-1]
    assert bot["steps"][0]["state"] == "start"  # waiting on the page

    chat(client, {"thread_id": tid, "client_results": [{"id": calls[0]["id"], "content": json.dumps({"ok": True})}]})
    turns = client.get(f"/agent/threads/{tid}", headers=ME).json()["turns"]
    assert [x["role"] for x in turns] == ["user", "bot"]
    assert turns[-1]["steps"][0]["state"] == "done"
    assert turns[-1]["text"].endswith("Switched to silence.")


def test_rename_and_delete(client, grok):
    tid = client.post("/agent/threads", headers=ME).json()["id"]
    assert client.patch(f"/agent/threads/{tid}", json={"title": "Bronx owls"}, headers=ME).json()["ok"]
    assert client.get("/agent/threads", headers=ME).json()["threads"][0]["title"] == "Bronx owls"
    assert client.delete(f"/agent/threads/{tid}", headers=ME).json()["ok"]
    assert client.get(f"/agent/threads/{tid}", headers=ME).status_code == 404


def test_imessage_space_keeps_one_thread_until_reset(client, grok):
    body = {"channel": "imessage", "imessage_space": "space-1", "text": "is the pi online?"}
    a = next(e for e in chat(client, body, headers={}) if e["type"] == "thread")["id"]
    b = next(e for e in chat(client, {**body, "text": "and now?"}, headers={}) if e["type"] == "thread")["id"]
    assert a == b
    c = next(e for e in chat(client, {**body, "new_thread": True}, headers={}) if e["type"] == "thread")["id"]
    assert c != a
    # iMessage threads are only for the bot on the server itself, never through the proxy
    with client.stream("POST", "/agent/chat", json=body, headers={"x-forwarded-for": "1.2.3.4"}) as r:
        assert r.status_code == 403
    # and they never show up in a browser's list
    assert client.get("/agent/threads", headers=ME).json()["threads"] == []


def test_stateless_protocol_still_works(client, grok):
    grok.script = ["plain"]
    events = chat(client, {"messages": [{"role": "user", "content": "hi"}]})
    assert not any(e["type"] == "thread" for e in events)
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "plain"
