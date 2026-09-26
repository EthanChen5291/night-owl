"""In-memory state for the demo hub, mirrored to an append-only JSONL so a restart keeps the events.

Data files resolve relative to the repo root (parent of api/), overridable with BARN_OWL_DATA_DIR:
  cells:    model/out/cells_<month>.json -> model/out/cells.json -> city/cells.fixture.json
  plan:     model/out/plan_<month>.json  -> model/out/plan.json  -> city/plan.fixture.json
  backtest: model/out/backtest.json      -> api/fixtures/backtest.json
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from posterior import PRIOR_SCORE_B, Posterior, accepts, percentile_rank

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parent
RING_SIZE = int(os.environ.get("BARN_OWL_RING", "2000"))


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, data_dir: Path | None = None, events_file: Path | None = None):
        self.data_dir = Path(data_dir or os.environ.get("BARN_OWL_DATA_DIR") or REPO_ROOT).resolve()
        self.events_file = Path(events_file or os.environ.get("BARN_OWL_EVENTS_FILE") or (API_DIR / "events.jsonl"))
        self.events: deque[dict] = deque(maxlen=RING_SIZE)  # oldest -> newest
        self.posteriors: dict[str, Posterior] = {}
        self.last_event_at: dict[str, str] = {}
        self.unknown_h3: set[str] = set()
        self._lock = threading.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._cache: dict[Path, tuple[float, dict]] = {}
        self._replay()

    # ---------- files ----------
    def _first_existing(self, candidates: list[Path]) -> Path:
        for p in candidates:
            if p.is_file():
                return p
        return candidates[-1]

    def cells_path(self, month: str | None = None) -> Path:
        c = []
        if month:
            c.append(self.data_dir / "model" / "out" / f"cells_{month}.json")
        c += [self.data_dir / "model" / "out" / "cells.json", self.data_dir / "city" / "cells.fixture.json"]
        return self._first_existing(c)

    def plan_path(self, month: str | None = None) -> Path:
        c = []
        if month:
            c.append(self.data_dir / "model" / "out" / f"plan_{month}.json")
        c += [self.data_dir / "model" / "out" / "plan.json", self.data_dir / "city" / "plan.fixture.json"]
        return self._first_existing(c)

    def backtest_path(self) -> Path:
        return self._first_existing([self.data_dir / "model" / "out" / "backtest.json", API_DIR / "fixtures" / "backtest.json"])

    def load_json(self, path: Path) -> dict:
        """Read with an mtime cache; returns a deep copy so callers can mutate."""
        mtime = path.stat().st_mtime
        hit = self._cache.get(path)
        if hit is None or hit[0] != mtime:
            with path.open() as f:
                hit = (mtime, json.load(f))
            self._cache[path] = hit
        return copy.deepcopy(hit[1])

    # ---------- reads ----------
    def cells(self, month: str | None = None) -> tuple[dict, Path]:
        path = self.cells_path(month)
        data = self.load_json(path)
        if month:
            data["month"] = month
        data["generated_at"] = data.get("generated_at") or utcnow_iso()
        self._overlay(data.get("cells", []))
        return data, path

    def _overlay(self, cells: list[dict]) -> None:
        """Replace posterior/score_b for touched cells, then recompute pct_b and silence over the set."""
        with self._lock:
            touched = False
            for cell in cells:
                post = self.posteriors.get(cell.get("h3"))
                if post is None:
                    continue
                touched = True
                cell["posterior"] = post.to_dict()
                cell["score_b"] = round(post.mean, 4)
                cell["last_event_at"] = self.last_event_at.get(cell["h3"], cell.get("last_event_at"))
        if not touched or not cells:
            return
        pct_b = percentile_rank([float(c.get("score_b", 0.0)) for c in cells])
        for cell, pb in zip(cells, pct_b):
            cell["pct_b"] = pb
            cell["silence"] = round(pb - float(cell.get("pct_a", 0.0)), 1)

    def plan(self, month: str | None = None, k: int | None = None) -> tuple[dict, Path]:
        path = self.plan_path(month)
        data = self.load_json(path)
        nodes = data.get("nodes", [])
        if k is not None:
            nodes = nodes[:k]
        data["nodes"] = nodes
        data["k"] = len(nodes) if k is None else k
        if month:
            data["month"] = month
        return data, path

    def placements(self) -> tuple[dict, Path]:
        """Node spot options inside ranked hexagons (model/09_placements.py). No fixture."""
        path = self.data_dir / "model" / "out" / "placements.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return self.load_json(path), path

    def backtest(self) -> tuple[dict, Path]:
        path = self.backtest_path()
        return self.load_json(path), path

    def queue(self, limit: int = 50) -> list[dict]:
        with self._lock:
            items = list(self.events)
        items.reverse()  # newest first
        return items[:limit]

    def score_b_for(self, h3: str) -> float | None:
        """Prior mean for a cell from the default cells file (no month), None if unknown."""
        try:
            data = self.load_json(self.cells_path())
        except (OSError, ValueError):
            return None
        for cell in data.get("cells", []):
            if cell.get("h3") == h3:
                return float(cell.get("score_b", PRIOR_SCORE_B))
        return None

    # ---------- writes ----------
    def add_event(self, event: dict, persist: bool = True) -> tuple[dict, Posterior, bool, bool]:
        """Returns (stored_event, posterior, accepted, known_h3)."""
        h3 = event["h3"]
        stored = dict(event)
        stored.setdefault("received_at", utcnow_iso())
        known = True
        with self._lock:
            post = self.posteriors.get(h3)
            if post is None:
                prior = self.score_b_for(h3)
                if prior is None:
                    known = False
                    self.unknown_h3.add(h3)
                    prior = PRIOR_SCORE_B
                post = Posterior.from_score_b(prior)
                self.posteriors[h3] = post
            accepted = accepts(float(stored["conf"]), int(stored["n_hits"]))
            if accepted:
                post.update(float(stored["conf"]))
            self.last_event_at[h3] = stored.get("ts") or stored["received_at"]
            self.events.append(stored)
            if persist:
                self._append_jsonl(stored)
        self._publish(stored)
        return stored, post, accepted, known

    def _append_jsonl(self, stored: dict) -> None:
        try:
            self.events_file.parent.mkdir(parents=True, exist_ok=True)
            with self.events_file.open("a") as f:
                f.write(json.dumps(stored, separators=(",", ":")) + "\n")
        except OSError as e:  # never let disk trouble break the stage
            print(f"WARN could not append {self.events_file}: {e}", flush=True)

    def _replay(self) -> None:
        if not self.events_file.is_file():
            return
        n = 0
        with self.events_file.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    self.add_event(ev, persist=False)
                    n += 1
                except (ValueError, KeyError) as e:
                    print(f"WARN skipping bad line in {self.events_file}: {e}", flush=True)
        if n:
            print(f"replayed {n} events from {self.events_file}", flush=True)

    def reset(self) -> int:
        with self._lock:
            n = len(self.events)
            self.events.clear()
            self.posteriors.clear()
            self.last_event_at.clear()
            self.unknown_h3.clear()
            try:
                if self.events_file.exists():
                    self.events_file.write_text("")
            except OSError as e:
                print(f"WARN could not truncate {self.events_file}: {e}", flush=True)
        self._publish({"reset": True, "at": utcnow_iso()})
        return n

    # ---------- SSE ----------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _publish(self, payload: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    @property
    def n_events(self) -> int:
        return len(self.events)
