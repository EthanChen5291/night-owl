"""Stored chat threads (api/chat_store.py via /agent/chat and /agent/threads), with a scripted fake Grok."""

import json
import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent
from chat_store import ChatStore
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
    answer_id = next(e for e in first if e["type"] == "thread")["answer_id"]
    calls = next(e for e in first if e["type"] == "client_tools")["calls"]
    assert [c["name"] for c in calls] == ["set_map_mode"]
    bot = client.get(f"/agent/threads/{tid}", headers=ME).json()["turns"][-1]
    assert bot["steps"][0]["state"] == "start"  # waiting on the page

    chat(client, {"thread_id": tid, "answer_id": answer_id,
                  "client_results": [{"id": calls[0]["id"], "content": json.dumps({"ok": True})}]})
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


def test_imessage_space_keeps_one_thread_until_reset(client, grok, monkeypatch):
    monkeypatch.setenv("NIGHT_OWL_CHAT_BOT_TOKEN", "test-bot-token")
    bot = {"x-chat-bot-token": "test-bot-token"}
    body = {"channel": "imessage", "imessage_space": "space-1", "text": "is the pi online?"}
    a = next(e for e in chat(client, body, headers=bot) if e["type"] == "thread")["id"]
    b = next(e for e in chat(client, {**body, "text": "and now?"}, headers=bot) if e["type"] == "thread")["id"]
    assert a == b
    c = client.post("/agent/imessage/reset", json={"imessage_space": "space-1"}, headers=bot).json()["id"]
    assert c != a
    assert next(e for e in chat(client, {**body, "text": "new topic"}, headers=bot) if e["type"] == "thread")["id"] == c
    # Proxied traffic works with the token, while any caller without it is denied.
    with client.stream("POST", "/agent/chat", json=body, headers={"x-forwarded-for": "1.2.3.4"}) as r:
        assert r.status_code == 403
    # and they never show up in a browser's list
    assert client.get("/agent/threads", headers=ME).json()["threads"] == []


def test_stateless_protocol_still_works(client, grok):
    grok.script = ["plain"]
    events = chat(client, {"messages": [{"role": "user", "content": "hi"}]})
    assert not any(e["type"] == "thread" for e in events)
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "plain"


def test_interrupted_answer_keeps_question_and_partial_context(client, grok, monkeypatch):
    async def disconnected(_body):
        yield {"choices": [{"delta": {"content": "partial answer"}}]}
        yield {"__error__": "provider disconnected"}

    monkeypatch.setattr(agent, "_chunks", disconnected)
    tid = next(e for e in chat(client, {"thread_id": None, "text": "Remember me"}) if e["type"] == "thread")["id"]
    turns = client.get(f"/agent/threads/{tid}", headers=ME).json()["turns"]
    assert [(t["role"], t["text"]) for t in turns] == [("user", "Remember me"), ("bot", "partial answer")]
    assert turns[-1]["error"] == "provider disconnected"
    assert [m["content"] for m in client.app.state.chats.history(tid)] == ["Remember me", "partial answer"]

    monkeypatch.setattr(agent, "_chunks", grok)
    chat(client, {"thread_id": tid, "text": "What did I ask?"})
    assert [m["content"] for m in grok.bodies[-1]["messages"][1:]] == ["Remember me", "partial answer", "What did I ask?"]


def test_pending_browser_tool_is_closed_before_next_question(client, grok):
    grok.script = [("call", "set_map_mode", {"mode": "silence"}), "next answer"]
    tid = next(e for e in chat(client, {"thread_id": None, "text": "Switch the map"}) if e["type"] == "thread")["id"]
    chat(client, {"thread_id": tid, "text": "New question after reload"})
    sent = grok.bodies[-1]["messages"][1:]
    call = next(m for m in sent if m.get("tool_calls"))
    tool_id = call["tool_calls"][0]["id"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == tool_id and "interrupted" in m["content"] for m in sent)
    assert sent[-1] == {"role": "user", "content": "New question after reload"}
    first_answer = client.get(f"/agent/threads/{tid}", headers=ME).json()["turns"][1]
    assert first_answer["steps"][0]["state"] == "error"
    assert first_answer["error"] == "Answer interrupted"


def test_tool_continuation_checks_originating_answer(client, grok):
    grok.script = [("call", "set_map_mode", {"mode": "silence"}), "done"]
    first = chat(client, {"thread_id": None, "text": "Switch the map"})
    event = next(e for e in first if e["type"] == "thread")
    call = next(e for e in first if e["type"] == "client_tools")["calls"][0]
    continuation = {"thread_id": event["id"], "answer_id": event["answer_id"],
                    "client_results": [{"id": call["id"], "content": "{}"}]}
    assert client.post("/agent/chat", json={**continuation, "answer_id": event["answer_id"] + 1}, headers=ME).status_code == 409
    assert client.post("/agent/chat", json={k: v for k, v in continuation.items() if k != "answer_id"}, headers=ME).status_code == 400
    assert client.post("/agent/chat", json={**continuation, "client_results": [{"id": "wrong", "content": "{}"}]}, headers=ME).status_code == 409
    chat(client, continuation)
    assert len(client.get(f"/agent/threads/{event['id']}", headers=ME).json()["turns"]) == 2


def test_legacy_import_is_idempotent_scoped_and_bounded(client):
    payload = {"migration_key": "nightowl.chat.v1", "items": [
        {"kind": "user", "text": "Old question"},
        {"kind": "bot", "text": "Old answer", "steps": [], "images": [], "busy": False}], "history": []}
    first = client.post("/agent/threads/import", json=payload, headers=ME)
    assert first.status_code == 200
    same = client.post("/agent/threads/import", json=payload, headers=ME)
    assert same.json()["thread"]["id"] == first.json()["thread"]["id"]
    assert len(same.json()["turns"]) == 2
    assert [m["content"] for m in client.app.state.chats.history(same.json()["thread"]["id"])] == ["Old question", "Old answer"]
    other = client.post("/agent/threads/import", json=payload, headers=OTHER)
    assert other.json()["thread"]["id"] != first.json()["thread"]["id"]
    assert client.post("/agent/threads/import", json={**payload, "items": payload["items"] * 51}, headers=ME).status_code == 400
    assert client.post("/agent/threads/import", json={**payload, "items": [{"kind": "bot", "text": 1}]}, headers=ME).status_code == 400
    bad_image = {"kind": "bot", "text": "image", "images": [{"src": "data:image/png;base64,AA", "caption": {"bad": True}}]}
    assert client.post("/agent/threads/import", json={**payload, "items": [bad_image]}, headers=ME).status_code == 400


def test_imessage_requires_shared_token(client, grok, monkeypatch):
    body = {"imessage_space": "private", "text": "hi"}
    monkeypatch.delenv("NIGHT_OWL_CHAT_BOT_TOKEN", raising=False)
    assert client.post("/agent/chat", json=body).status_code == 503
    assert client.post("/agent/imessage/reset", json={"imessage_space": "private"}).status_code == 503
    monkeypatch.setenv("NIGHT_OWL_CHAT_BOT_TOKEN", "secret")
    assert client.post("/agent/chat", json=body).status_code == 403
    assert client.post("/agent/imessage/reset", json={"imessage_space": "private"}, headers={"x-chat-bot-token": "wrong"}).status_code == 403
    assert client.post("/agent/imessage/reset", json={"imessage_space": "private"}, headers={"x-chat-bot-token": "secret"}).status_code == 200
    assert len(client.app.state.chats.list("imessage:private")) == 1


def test_two_workers_reject_overlap_and_preserve_history(tmp_path, grok, monkeypatch):
    async def scenario():
        path = tmp_path / "chat.db"
        first_store, second_store = ChatStore(path), ChatStore(path)
        first_app, second_app = FastAPI(), FastAPI()
        source = SimpleNamespace(events_file=tmp_path / "events.jsonl")
        agent.mount_agent(first_app, source, first_store)
        agent.mount_agent(second_app, source, second_store)
        started, release = asyncio.Event(), asyncio.Event()
        seen = []

        async def fake_run(_data, messages, emit, _channel):
            question = messages[-1]["content"]
            seen.append([m["content"] for m in messages])
            if question == "A":
                started.set()
                await release.wait()
            await emit({"type": "delta", "text": "answer " + question})
            await emit({"type": "messages", "messages": messages + [{"role": "assistant", "content": "answer " + question}]})

        monkeypatch.setattr(agent, "run_agent", fake_run)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=first_app), base_url="http://test", headers=ME) as one, \
                   httpx.AsyncClient(transport=httpx.ASGITransport(app=second_app), base_url="http://test", headers=ME) as two:
            tid = (await one.post("/agent/threads")).json()["id"]
            running = asyncio.create_task(one.post("/agent/chat", json={"thread_id": tid, "text": "A"}))
            await asyncio.wait_for(started.wait(), 2)
            blocked = await two.post("/agent/chat", json={"thread_id": tid, "text": "B"})
            assert blocked.status_code == 409
            assert [t["text"] for t in second_store.turns(tid)] == ["A", ""]
            release.set()
            assert (await running).status_code == 200
            assert (await two.post("/agent/chat", json={"thread_id": tid, "text": "B"})).status_code == 200
            assert seen == [["A"], ["A", "answer A", "B"]]
            assert [m["content"] for m in ChatStore(path).history(tid)] == ["A", "answer A", "B", "answer B"]

    asyncio.run(scenario())


def test_first_stream_fragment_is_durable_before_answer_finishes(tmp_path, grok, monkeypatch):
    async def scenario():
        path = tmp_path / "chat.db"
        chats = ChatStore(path)
        app = FastAPI()
        agent.mount_agent(app, SimpleNamespace(events_file=tmp_path / "events.jsonl"), chats)
        sent, release = asyncio.Event(), asyncio.Event()

        async def paused_run(_data, messages, emit, _channel):
            await emit({"type": "delta", "text": "first fragment"})
            sent.set()
            await release.wait()
            await emit({"type": "messages", "messages": messages + [{"role": "assistant", "content": "first fragment"}]})

        monkeypatch.setattr(agent, "run_agent", paused_run)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=ME) as client:
            tid = (await client.post("/agent/threads")).json()["id"]
            running = asyncio.create_task(client.post("/agent/chat", json={"thread_id": tid, "text": "question"}))
            await asyncio.wait_for(sent.wait(), 2)
            assert [m["content"] for m in ChatStore(path).history(tid)] == ["question"]
            assert [t["text"] for t in ChatStore(path).turns(tid)] == ["question", "first fragment"]
            release.set()
            assert (await running).status_code == 200

    asyncio.run(scenario())


def test_expired_run_is_recovered_and_stale_writer_is_fenced(tmp_path):
    path = tmp_path / "chat.db"
    first, second = ChatStore(path), ChatStore(path)
    tid = first.create("web:browser-aaaaaaaaaaaaaaaa")["id"]
    old_run, old_answer, _, _ = first.begin_question(tid, "web:browser-aaaaaaaaaaaaaaaa", "first")
    assert first.checkpoint(tid, old_run, old_answer, "partial", [], [], None)
    with sqlite3.connect(path) as c:
        c.execute("update threads set lease_until = 0 where id = ?", (tid,))
    new_run, new_answer, messages, _ = second.begin_question(tid, "web:browser-aaaaaaaaaaaaaaaa", "second")
    assert [m["content"] for m in messages] == ["first", "partial", "second"]
    assert second.turns(tid)[1]["error"] == "Answer interrupted"
    assert not first.checkpoint(tid, old_run, old_answer, "stale", [], [], None, release=True)
    assert second.checkpoint(tid, new_run, new_answer, "fresh", [], [], None, release=True)
    assert [t["text"] for t in ChatStore(path).turns(tid)] == ["first", "partial", "second", "fresh"]


def test_imessage_reset_stays_current_when_old_answer_finishes(tmp_path):
    path = tmp_path / "chat.db"
    first, second = ChatStore(path), ChatStore(path)
    owner = "imessage:space-1"
    old = first.current_imessage(owner)
    old_run, old_answer, _, _ = first.begin_question(old["id"], owner, "old question")
    new = second.current_imessage(owner, reset=True)
    assert new["id"] != old["id"]
    assert first.checkpoint(old["id"], old_run, old_answer, "late reply", [], [], None, release=True)
    assert first.current_imessage(owner)["id"] == new["id"]
    assert second.current_imessage(owner)["id"] == new["id"]


def test_imessage_first_requests_converge_on_one_thread(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "chat.db"
    one, two = ChatStore(path), ChatStore(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(one.current_imessage, "imessage:space-1")
        b = pool.submit(two.current_imessage, "imessage:space-1")
        assert a.result()["id"] == b.result()["id"]


def test_legacy_schema_migrates_with_concurrent_workers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "old-chat.db"
    with sqlite3.connect(path) as c:
        c.execute("create table threads (id text primary key, owner text not null, channel text not null default 'web', "
                  "title text not null default 'New chat', created_at real not null, updated_at real not null, "
                  "history text not null default '[]')")
        c.execute("insert into threads (id, owner, created_at, updated_at) values ('old', 'web:browser-aaaaaaaaaaaaaaaa', 1, 1)")
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(ChatStore, path)
        b = pool.submit(ChatStore, path)
        assert a.result().get("old", "web:browser-aaaaaaaaaaaaaaaa")["history"] == "[]"
        assert b.result().get("old", "web:browser-aaaaaaaaaaaaaaaa")["run_id"] is None


def test_cancelled_request_releases_lease_and_keeps_partial_answer(tmp_path, grok, monkeypatch):
    async def scenario():
        path = tmp_path / "chat.db"
        chats = ChatStore(path)
        app = FastAPI()
        agent.mount_agent(app, SimpleNamespace(events_file=tmp_path / "events.jsonl"), chats)
        sent = asyncio.Event()

        async def paused_run(_data, _messages, emit, _channel):
            await emit({"type": "delta", "text": "partial"})
            sent.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(agent, "run_agent", paused_run)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=ME) as client:
            tid = (await client.post("/agent/threads")).json()["id"]
            running = asyncio.create_task(client.post("/agent/chat", json={"thread_id": tid, "text": "question"}))
            await asyncio.wait_for(sent.wait(), 2)
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
            for _ in range(50):
                if chats.get(tid, "web:browser-aaaaaaaaaaaaaaaa")["run_id"] is None:
                    break
                await asyncio.sleep(0.02)
            else:
                pytest.fail("cancelled answer kept its lease")
            assert [m["content"] for m in chats.history(tid)] == ["question", "partial"]
            assert chats.turns(tid)[1]["error"] == "Answer interrupted"

    asyncio.run(scenario())
