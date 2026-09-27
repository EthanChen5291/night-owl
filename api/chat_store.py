"""SQLite-backed chat threads for the NightOwl assistant (api/agent.py).

Two tables:
  threads  one conversation: who owns it, where it happens (web / imessage), its title, and `history`, the
           OpenAI-style messages the model sees next time (pictures stripped, as the browser used to keep them)
  turns    what the person sees: their questions, and each answer with its tool steps, pictures and any error

The server is the source of truth: the browser and the iMessage bot send only the new question (or the page's tool
results) plus a thread id, and the server loads and saves the rest. Owners are opaque strings: "web:<browser id>"
for the map chat (an anonymous id the page keeps, not a login), "imessage:<Spectrum space id>" for texts.

Stdlib only. One connection per call, WAL mode, a process-wide lock around writes (FastAPI runs tools in threads).
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

SCHEMA = """
create table if not exists threads (
  id          text primary key,
  owner       text not null,
  channel     text not null default 'web',
  title       text not null default 'New chat',
  created_at  real not null,
  updated_at  real not null,
  history     text not null default '[]'
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

    def latest(self, owner: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("select * from threads where owner = ? order by updated_at desc limit 1", (owner,)).fetchone()
        return dict(r) if r else None

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

    def save_history(self, tid: str, messages: list[dict]) -> None:
        with self._conn() as c:
            c.execute("update threads set history = ?, updated_at = ? where id = ?", (json.dumps(messages), time.time(), tid))

    # ------------------------------------------------------------------ turns

    def add_question(self, tid: str, text: str) -> int:
        """Stores the question and an empty answer to fill in; titles an untitled thread after its first question.
        Returns the answer's turn id."""
        now = time.time()
        with self._conn() as c:
            c.execute("insert into turns (thread_id, role, text, created_at) values (?, 'user', ?, ?)", (tid, text, now))
            cur = c.execute("insert into turns (thread_id, role, created_at) values (?, 'bot', ?)", (tid, now))
            c.execute("update threads set updated_at = ?, title = case when title = 'New chat' then ? else title end where id = ?",
                      (now, _title(text), tid))
            return int(cur.lastrowid)

    def last_answer(self, tid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("select * from turns where thread_id = ? and role = 'bot' order by id desc limit 1", (tid,)).fetchone()
        return _turn(r) if r else None

    def save_answer(self, turn_id: int, text: str, steps: list[dict], images: list[dict], error: str | None) -> None:
        kept = [i for i in images if len(i.get("src", "")) <= MAX_IMAGE_CHARS][:MAX_TURN_IMAGES]
        with self._conn() as c:
            c.execute("update turns set text = ?, steps = ?, images = ?, error = ? where id = ?",
                      (text, json.dumps(steps), json.dumps(kept), error, turn_id))

    def turns(self, tid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("select * from turns where thread_id = ? order by id", (tid,)).fetchall()
        return [_turn(r) for r in rows]


def _title(text: str) -> str:
    t = " ".join(text.split())
    return t if len(t) <= TITLE_CHARS else t[: TITLE_CHARS - 1].rstrip() + "…"


def _turn(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "role": r["role"], "text": r["text"], "steps": json.loads(r["steps"]),
            "images": json.loads(r["images"]), "error": r["error"], "created_at": r["created_at"]}
