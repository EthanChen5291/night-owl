"""SQLite-backed chat threads for the NightOwl assistant (api/agent.py).

Main tables:
  threads  one conversation: who owns it, where it happens (web / imessage), its title, and `history`, the
           OpenAI-style messages the model sees next time (pictures stripped, as the browser used to keep them)
  turns    what the person sees: their questions, and each answer with its tool steps, pictures and any error

The server is the source of truth: the browser and the iMessage bot send only the new question (or the page's tool
results) plus a thread id, and the server loads and saves the rest. Owners are opaque strings: "web:<browser id>"
for the map chat (an anonymous id the page keeps, not a login), "imessage:<Spectrum space id>" for texts.

Stdlib only. One connection per call, WAL mode, and short SQLite transactions. A fenced lease on each thread
rejects overlapping runs across workers without holding a write transaction while the model or tools run.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

MAX_THREADS_LISTED = 50
MAX_TURN_IMAGES = 4
MAX_IMAGE_CHARS = 700_000   # one stored picture as a data URL; bigger ones (full map screenshots) are dropped
TITLE_CHARS = 60
RUN_LEASE_SECONDS = 20
MAX_IMPORT_ITEMS = 100

SCHEMA = """
create table if not exists threads (
  id          text primary key,
  owner       text not null,
  channel     text not null default 'web',
  title       text not null default 'New chat',
  created_at  real not null,
  updated_at  real not null,
  history     text not null default '[]',
  run_id      text,
  lease_until real
);
create index if not exists threads_owner on threads (owner, updated_at desc);
create table if not exists turns (
  id          integer primary key autoincrement,
  thread_id   text not null references threads(id) on delete cascade,
  role        text not null check (role in ('user', 'bot')),
  text        text not null default '',
  steps       text not null default '[]',
  images      text not null default '[]',
  error       text,
  created_at  real not null
);
create index if not exists turns_thread on turns (thread_id, id);
create table if not exists chat_imports (
  owner text not null,
  migration_key text not null,
  thread_id text not null references threads(id) on delete cascade,
  primary key (owner, migration_key)
);
create table if not exists imessage_current (
  owner text primary key,
  thread_id text not null references threads(id) on delete cascade
);
"""


def default_path() -> Path:
    """NIGHT_OWL_CHAT_DB, else next to the events log (the droplet keeps that in writable /var/lib/poc), else api/."""
    explicit = os.environ.get("NIGHT_OWL_CHAT_DB")
    if explicit:
        return Path(explicit)
    events = os.environ.get("NIGHT_OWL_EVENTS_FILE") or os.environ.get("BARN_OWL_EVENTS_FILE")
    return (Path(events).parent if events else Path(__file__).resolve().parent) / "chat.db"


class ChatStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            c.execute("begin immediate")
            columns = {r["name"] for r in c.execute("pragma table_info(threads)")}
            if "run_id" not in columns:
                c.execute("alter table threads add column run_id text")
            if "lease_until" not in columns:
                c.execute("alter table threads add column lease_until real")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("pragma journal_mode=wal")
        c.execute("pragma foreign_keys=on")
        try:
            with self._lock, c:
                yield c
        finally:
            c.close()

    # ------------------------------------------------------------------ threads

    def create(self, owner: str, channel: str = "web", title: str | None = None) -> dict:
        now = time.time()
        tid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute("insert into threads (id, owner, channel, title, created_at, updated_at) values (?, ?, ?, ?, ?, ?)",
                      (tid, owner, channel, (title or "New chat")[:TITLE_CHARS], now, now))
        return {"id": tid, "owner": owner, "channel": channel, "title": title or "New chat", "created_at": now, "updated_at": now}

    def get(self, tid: str, owner: str) -> dict | None:
        """The thread if this owner has it (a wrong owner looks exactly like a missing thread)."""
        with self._conn() as c:
            r = c.execute("select * from threads where id = ? and owner = ?", (tid, owner)).fetchone()
        return dict(r) if r else None

    def current_imessage(self, owner: str, reset: bool = False) -> dict:
        """Durable active pointer; an old stream finishing after reset cannot become current again."""
        with self._conn() as c:
            c.execute("begin immediate")
            current = None if reset else c.execute("select thread_id from imessage_current where owner = ?", (owner,)).fetchone()
            if current:
                row = c.execute("select * from threads where id = ? and owner = ?", (current["thread_id"], owner)).fetchone()
                if row:
                    return dict(row)
            row = None if reset else c.execute("select * from threads where owner = ? and channel = 'imessage' order by updated_at desc limit 1",
                                               (owner,)).fetchone()
            if row:
                tid = row["id"]
            else:
                now, tid = time.time(), uuid.uuid4().hex
                c.execute("insert into threads (id, owner, channel, created_at, updated_at) values (?, ?, 'imessage', ?, ?)",
                          (tid, owner, now, now))
            c.execute("insert into imessage_current (owner, thread_id) values (?, ?) "
                      "on conflict(owner) do update set thread_id = excluded.thread_id", (owner, tid))
            return dict(c.execute("select * from threads where id = ?", (tid,)).fetchone())

    def list(self, owner: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """select t.id, t.channel, t.title, t.created_at, t.updated_at,
                          (select count(*) from turns u where u.thread_id = t.id and u.role = 'user') as questions
                   from threads t where owner = ? order by updated_at desc limit ?""", (owner, MAX_THREADS_LISTED)).fetchall()
        return [dict(r) for r in rows]

    def rename(self, tid: str, owner: str, title: str) -> bool:
        with self._conn() as c:
            n = c.execute("update threads set title = ? where id = ? and owner = ?", (title.strip()[:TITLE_CHARS] or "New chat", tid, owner)).rowcount
        return n > 0

    def delete(self, tid: str, owner: str) -> bool:
        with self._conn() as c:
            n = c.execute("delete from threads where id = ? and owner = ?", (tid, owner)).rowcount
        return n > 0

    def history(self, tid: str) -> list[dict]:
        with self._conn() as c:
            r = c.execute("select history from threads where id = ?", (tid,)).fetchone()
        return json.loads(r["history"]) if r else []

    def begin_question(self, tid: str, owner: str, question: str) -> tuple[str, int, list[dict], dict] | None:
        """Claim one run and persist its question before any network request. None means a live run owns the thread."""
        now, run_id = time.time(), uuid.uuid4().hex
        with self._conn() as c:
            c.execute("begin immediate")
            prior_run = c.execute("select run_id from threads where id = ? and owner = ?", (tid, owner)).fetchone()
            had_expired_run = bool(prior_run and prior_run["run_id"])
            claimed = c.execute(
                "update threads set run_id = ?, lease_until = ? where id = ? and owner = ? "
                "and (run_id is null or lease_until < ?)",
                (run_id, now + RUN_LEASE_SECONDS, tid, owner, now),
            ).rowcount
            if not claimed:
                return None
            row = c.execute("select * from threads where id = ?", (tid,)).fetchone()
            messages = json.loads(row["history"])
            previous = c.execute("select * from turns where thread_id = ? and role = 'bot' order by id desc limit 1", (tid,)).fetchone()
            if previous:
                pending_tools = _pending_tool_ids(messages)
                was_interrupted = had_expired_run or bool(pending_tools) or bool(
                    messages and messages[-1].get("role") == "user" and previous["error"] is None)
                messages = _close_pending_tools(messages)
                # A crashed or abandoned answer still belongs in future context.
                if messages and messages[-1].get("role") == "user" and previous["text"]:
                    messages.append({"role": "assistant", "content": previous["text"]})
                steps = json.loads(previous["steps"])
                if was_interrupted or any(s.get("state") == "start" for s in steps):
                    for step in steps:
                        if step.get("state") == "start":
                            step["state"] = "error"
                    c.execute("update turns set steps = ?, error = coalesce(error, ?) where id = ?",
                              (json.dumps(steps), "Answer interrupted", previous["id"]))
            messages.append({"role": "user", "content": question})
            c.execute("insert into turns (thread_id, role, text, created_at) values (?, 'user', ?, ?)", (tid, question, now))
            cur = c.execute("insert into turns (thread_id, role, created_at) values (?, 'bot', ?)", (tid, now))
            c.execute("update threads set history = ?, updated_at = ?, title = case when title = 'New chat' then ? else title end where id = ?",
                      (json.dumps(messages), now, _title(question), tid))
            return run_id, int(cur.lastrowid), messages, dict(c.execute("select * from threads where id = ?", (tid,)).fetchone())

    def begin_continuation(self, tid: str, owner: str, answer_id: int,
                           result_ids: list[str]) -> tuple[str, int, list[dict], dict] | None:
        now, run_id = time.time(), uuid.uuid4().hex
        with self._conn() as c:
            c.execute("begin immediate")
            claimed = c.execute(
                "update threads set run_id = ?, lease_until = ? where id = ? and owner = ? "
                "and (run_id is null or lease_until < ?)",
                (run_id, now + RUN_LEASE_SECONDS, tid, owner, now),
            ).rowcount
            if not claimed:
                return None
            row = c.execute("select * from threads where id = ?", (tid,)).fetchone()
            last = c.execute("select * from turns where thread_id = ? and role = 'bot' order by id desc limit 1", (tid,)).fetchone()
            messages = json.loads(row["history"])
            pending = _pending_tool_ids(messages)
            if not last or answer_id != last["id"] or not pending or sorted(result_ids) != sorted(pending):
                c.execute("update threads set run_id = null, lease_until = null where id = ? and run_id = ?", (tid, run_id))
                raise ValueError("no pending answer for this continuation")
            return run_id, last["id"], messages, _turn(last)

    def heartbeat(self, tid: str, run_id: str) -> bool:
        with self._conn() as c:
            return bool(c.execute("update threads set lease_until = ? where id = ? and run_id = ?",
                                  (time.time() + RUN_LEASE_SECONDS, tid, run_id)).rowcount)

    def checkpoint(self, tid: str, run_id: str, turn_id: int, text: str, steps: list[dict], images: list[dict],
                   error: str | None, messages: list[dict] | None = None, release: bool = False) -> bool:
        """Fence every write with the active run. Save visible answer and context in one short transaction."""
        kept = [i for i in images if len(i.get("src", "")) <= MAX_IMAGE_CHARS][:MAX_TURN_IMAGES]
        with self._conn() as c:
            c.execute("begin immediate")
            row = c.execute("select history from threads where id = ? and run_id = ?", (tid, run_id)).fetchone()
            if not row:
                return False
            if messages is None:
                messages = json.loads(row["history"])
                if error or release:
                    if messages and messages[-1].get("role") == "user" and text:
                        messages.append({"role": "assistant", "content": text})
            c.execute("update turns set text = ?, steps = ?, images = ?, error = ? where id = ? and thread_id = ?",
                      (text, json.dumps(steps), json.dumps(kept), error, turn_id, tid))
            c.execute("update threads set history = ?, updated_at = ?, run_id = ?, lease_until = ? where id = ? and run_id = ?",
                      (json.dumps(messages), time.time(), None if release else run_id,
                       None if release else time.time() + RUN_LEASE_SECONDS, tid, run_id))
            return True

    def import_legacy(self, owner: str, migration_key: str, items: list[dict], history: list[dict]) -> tuple[dict, list[dict]]:
        """One import per owner/key, including retries after an uncertain response."""
        now = time.time()
        with self._conn() as c:
            c.execute("begin immediate")
            prior = c.execute("select thread_id from chat_imports where owner = ? and migration_key = ?",
                              (owner, migration_key)).fetchone()
            if prior:
                tid = prior["thread_id"]
            else:
                tid = uuid.uuid4().hex
                title = next((_title(i["text"]) for i in items if i["kind"] == "user"), "New chat")
                c.execute("insert into threads (id, owner, channel, title, created_at, updated_at, history) values (?, ?, 'web', ?, ?, ?, ?)",
                          (tid, owner, title, now, now, json.dumps(history)))
                for i in items:
                    c.execute("insert into turns (thread_id, role, text, steps, images, error, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                              (tid, "user" if i["kind"] == "user" else "bot", i["text"], json.dumps(i.get("steps", [])),
                               json.dumps(i.get("images", [])), i.get("error"), now))
                c.execute("insert into chat_imports (owner, migration_key, thread_id) values (?, ?, ?)", (owner, migration_key, tid))
            thread = dict(c.execute("select * from threads where id = ?", (tid,)).fetchone())
            turns = [_turn(r) for r in c.execute("select * from turns where thread_id = ? order by id", (tid,))]
            return thread, turns

    # ------------------------------------------------------------------ turns

    def turns(self, tid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("select * from turns where thread_id = ? order by id", (tid,)).fetchall()
        return [_turn(r) for r in rows]


def _title(text: str) -> str:
    t = " ".join(text.split())
    return t if len(t) <= TITLE_CHARS else t[: TITLE_CHARS - 1].rstrip() + "…"


def _pending_tool_ids(messages: list[dict]) -> list[str]:
    """IDs in the last assistant call group that do not yet have tool replies."""
    for index in range(len(messages) - 1, -1, -1):
        m = messages[index]
        if m.get("role") == "assistant":
            calls = m.get("tool_calls") or []
            replied = {x.get("tool_call_id") for x in messages[index + 1:] if x.get("role") == "tool"}
            return [str(x.get("id")) for x in calls if str(x.get("id")) not in replied]
        if m.get("role") == "user":
            return []
    return []


def _close_pending_tools(messages: list[dict]) -> list[dict]:
    for tool_id in _pending_tool_ids(messages):
        messages.append({"role": "tool", "tool_call_id": tool_id,
                         "content": json.dumps({"error": "Browser tool interrupted before returning a result"})})
    return messages


def _turn(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "role": r["role"], "text": r["text"], "steps": json.loads(r["steps"]),
            "images": json.loads(r["images"]), "error": r["error"], "created_at": r["created_at"]}
