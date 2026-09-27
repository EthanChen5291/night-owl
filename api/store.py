"""In-memory state for the demo hub, mirrored to an append-only JSONL so a restart keeps the events.

Data files resolve relative to the repo root (parent of api/), overridable with NIGHT_OWL_DATA_DIR:
  cells:    model/out/cells_<month>.json -> model/out/cells.json -> city/cells.fixture.json
  plan:     model/out/plan_<month>.json  -> model/out/plan.json  -> city/plan.fixture.json
  backtest: model/out/backtest.json      -> api/fixtures/backtest.json
  history:  model/out/history.json       -> api/fixtures/history.json
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from posterior import PRIOR_SCORE_B, Posterior, accepts, percentile_rank

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parent
RING_SIZE = int(os.environ.get("NIGHT_OWL_RING", os.environ.get("BARN_OWL_RING", "2000")))


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, data_dir: Path | None = None, events_file: Path | None = None):
        self.data_dir = Path(data_dir or os.environ.get("NIGHT_OWL_DATA_DIR", os.environ.get("BARN_OWL_DATA_DIR")) or REPO_ROOT).resolve()
        self.events_file = Path(events_file or os.environ.get("NIGHT_OWL_EVENTS_FILE", os.environ.get("BARN_OWL_EVENTS_FILE")) or (API_DIR / "events.jsonl"))
        self.events: deque[dict] = deque(maxlen=RING_SIZE)  # oldest -> newest
        self.posteriors: dict[tuple[str, str], Posterior] = {}
        self.last_event_at: dict[tuple[str, str], str] = {}
        self.event_ids: set[str] = set()
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

    def _source_path(self, kind: str, month: str | None = None) -> Path:
        model = self.data_dir / "model" / "out"
        fixture = self.data_dir / "city" / f"{kind}.fixture.json"
        paths = ([model / f"{kind}_{month}.json"] if month else []) + [model / f"{kind}.json", fixture]
        if month:
            # A dated request prefers an actual match, including a fixture, over
            # a newer generic model file. Never rename that newer file's month.
            for path in paths:
                if path.is_file() and self.load_json(path).get("month") == month:
                    return path
        return self._first_existing(paths)

    def cells_path(self, month: str | None = None) -> Path:
        return self._source_path("cells", month)

    def plan_path(self, month: str | None = None) -> Path:
        return self._source_path("plan", month)

    def backtest_path(self) -> Path:
        return self._first_existing([self.data_dir / "model" / "out" / "backtest.json", API_DIR / "fixtures" / "backtest.json"])

    def history_path(self) -> Path:
        return self._first_existing([self.data_dir / "model" / "out" / "history.json", API_DIR / "fixtures" / "history.json"])

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
            data["requested_month"] = month
        data["source"] = "fixture" if path.name.endswith(".fixture.json") else "model"
        data["synthetic"] = data["source"] == "fixture"
        data["generated_at"] = data.get("generated_at") or utcnow_iso()
        self._overlay(data.get("cells", []), data.get("month"))
        return data, path

    def _overlay(self, cells: list[dict], month: str | None) -> None:
        """Replace posterior/score_b for touched cells, then recompute pct_b and silence over the set."""
        with self._lock:
            touched = False
            for cell in cells:
                post = self.posteriors.get((month, cell.get("h3")))
                if post is None:
                    continue
                touched = True
                cell["posterior"] = post.to_dict()
                cell["score_b"] = round(post.mean, 4)
                cell["model_ci_b"] = cell.get("ci_b")
                cell["ci_b"] = post.interval()
                cell["ci_b_basis"] = "sensor_posterior_wilson_approx"
                cell["last_event_at"] = self.last_event_at.get((month, cell["h3"]), cell.get("last_event_at"))
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
        source_month = data.get("month")
        with self._lock:
            touched = {h3 for (event_month, h3), post in self.posteriors.items()
                       if event_month == source_month and post.n_events}
        if touched:
            nodes = self._rank_plan_nodes(nodes, source_month, path)
        data["replanned"] = nodes != data.get("nodes", [])
        if k is not None:
            nodes = nodes[:k]
        data["nodes"] = nodes
        data["k"] = len(nodes)
        if month:
            data["requested_month"] = month
        data["source"] = "fixture" if path.name.endswith(".fixture.json") else "model"
        data["synthetic"] = data["source"] == "fixture"
        return data, path

    @staticmethod
    def _distance_m(a: dict, b: dict) -> float:
        lat1, lat2 = math.radians(float(a["lat"])), math.radians(float(b["lat"]))
        dlat = lat2 - lat1
        dlon = math.radians(float(b["lon"]) - float(a["lon"]))
        x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 12_742_000 * math.asin(min(1.0, math.sqrt(x)))

    def _rank_plan_nodes(self, original: list[dict], month: str, plan_path: Path) -> list[dict]:
        """Re-rank real tree locations; never synthesize a mount or move a pin."""
        cells_path = self.cells_path(month)
        cells_data = self.load_json(cells_path)
        if cells_data.get("month") != month:
            return original
        cells = {c["h3"]: c for c in cells_data.get("cells", [])}
        shown_cells = copy.deepcopy(cells_data.get("cells", []))
        self._overlay(shown_cells, month)
        shown = {c["h3"]: c for c in shown_cells}
        candidates = {n["h3"]: copy.deepcopy(n) for n in original
                      if n.get("tree_id") and "catch_basin" not in n.get("reason", "")}
        # Placements supply additional real, tree-backed candidate cells for
        # model output. The fixture has no matching placement pool.
        placements_path = self.data_dir / "model" / "out" / "placements.json"
        if plan_path.parent.name == "out" and placements_path.is_file():
            placements = self.load_json(placements_path)
            if placements.get("month") == month:
                for h3, spots in placements.get("cells", {}).items():
                    if h3 in candidates or h3 not in cells or not spots:
                        continue
                    spot = spots[0]
                    if not spot.get("tree_id"):
                        continue
                    candidates[h3] = {"h3": h3, "lat": spot["lat"], "lon": spot["lon"],
                                      "tree_id": spot["tree_id"], "reason": "Tree pit at " + spot.get("mount_address", "recorded site")}
        with self._lock:
            posts = {h3: post for (m, h3), post in self.posteriors.items() if m == month and post.n_events}
        if not set(candidates).intersection(posts):
            return original
        ranked = []
        for h3, node in candidates.items():
            cell = cells.get(h3)
            if cell is None:
                continue
            try:
                if not all(math.isfinite(float(node[k])) for k in ("lat", "lon")):
                    continue
                baseline = float(node.get("expected_gain", float(cell["score_b"]) * float(cell.get("data_gap", 1))))
                post = posts.get(h3)
                if post:
                    risk_ratio = post.mean / max(1e-6, float(cell["score_b"]))
                    prior_strength = post.prior_strength
                    gain = baseline * risk_ratio * prior_strength / (prior_strength + post.n_events)
                    node["reason"] = f"{node['reason']}; sensor posterior {post.mean:.1%}, {post.n_events} accepted detections"
                else:
                    gain = baseline
                node["expected_gain"] = round(gain, 5)
                node["silence"] = float(shown[h3].get("silence", 0))
                ranked.append(node)
            except (KeyError, TypeError, ValueError):
                continue
        ranked.sort(key=lambda n: (-n["expected_gain"], n["h3"], str(n["tree_id"])))
        picked = []
        for node in ranked:
            if all(self._distance_m(node, other) >= 100 for other in picked):
                node["rank"] = len(picked) + 1
                picked.append(node)
            if len(picked) >= len(original):
                break
        return picked

    def placements(self) -> tuple[dict, Path]:
        """Node spot options inside ranked hexagons (model/09_placements.py). No fixture."""
        path = self.data_dir / "model" / "out" / "placements.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return self.load_json(path), path

    def backtest(self) -> tuple[dict, Path]:
        path = self.backtest_path()
        return self.load_json(path), path

    def history(self) -> tuple[dict, Path]:
        """Dated 311 complaint and inspection history by borough and ZIP code area (data/fetch_history.py)."""
        path = self.history_path()
        return self.load_json(path), path

    def queue(self, limit: int = 50) -> list[dict]:
        with self._lock:
            items = list(self.events)
        items.reverse()  # newest first
        return items[:limit]

    def prior_for(self, h3: str, month: str) -> Posterior | None:
        """Use a coherent exported prior for the event's own month."""
        try:
            data = self.load_json(self.cells_path(month))
        except (OSError, ValueError):
            return None
        if data.get("month") != month:
            return None
        for cell in data.get("cells", []):
            if cell.get("h3") == h3:
                score = float(cell.get("score_b", PRIOR_SCORE_B))
                exported = cell.get("posterior") or {}
                try:
                    alpha, beta = float(exported["alpha"]), float(exported["beta"])
                    if (alpha > 0 and beta > 0 and exported.get("n_events") == 0
                            and abs(alpha / (alpha + beta) - score) <= 0.0002):
                        return Posterior(alpha, beta)
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    pass
                return Posterior.from_score_b(score)
        return None

    # ---------- writes ----------
    def add_event(self, event: dict, persist: bool = True) -> tuple[dict, Posterior, bool, bool]:
        """Returns (stored_event, posterior, accepted, known_h3)."""
        h3 = event["h3"]
        month = event["ts"][:7]
        key = (month, h3)
        stored = dict(event)
        stored.setdefault("received_at", utcnow_iso())
        event_id = hashlib.sha256(json.dumps({k: v for k, v in stored.items() if k != "received_at"},
                                            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        known = True
        with self._lock:
            if event_id in self.event_ids:
                prior = self.prior_for(h3, month)
                post = self.posteriors.get(key) or prior or Posterior.from_score_b(PRIOR_SCORE_B)
                return stored, post, False, prior is not None
            post = self.posteriors.get(key)
            if post is None:
                post = self.prior_for(h3, month)
                if post is None:
                    known = False
                    post = Posterior.from_score_b(PRIOR_SCORE_B)
            accepted = stored["class"] == "rat" and accepts(float(stored["conf"]), int(stored["n_hits"]))
            if accepted:
                self.posteriors[key] = post
                post.update(float(stored["conf"]))
                self.last_event_at[key] = stored.get("ts") or stored["received_at"]
            self.events.append(stored)
            self.event_ids.add(event_id)
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
            self.event_ids.clear()
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
