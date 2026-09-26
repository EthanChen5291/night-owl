"""Barn Owl API: the hub between the Pi node (POST /event), the model output (model/out/*.json) and the web app.

Run:  api/run.sh   or   uv run --project api uvicorn main:app --app-dir api --host 0.0.0.0 --port 8000
Contract: plan/master-plan.md §6 (frozen). Stage fallback: api/fake_event.sh (plan §9).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Literal

from datetime import datetime, timezone

import h3
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from store import Store

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Event(BaseModel):
    """POST /event body, exactly the 9 keys of the contract."""
    model_config = {"extra": "forbid"}

    node_id: str = Field(min_length=1, max_length=64)
    h3: str = Field(min_length=1, max_length=32)
    ts: str = Field(min_length=1, max_length=40)
    class_: Literal["rat", "person"] = Field(alias="class")
    conf: float = Field(ge=0.0, le=1.0)
    n_hits: int = Field(ge=0, le=10_000)
    bbox: list[float] = Field(min_length=4, max_length=4)
    crop_b64: str = Field(default="", max_length=4_000_000)
    fw: str = Field(default="", max_length=32)

    @field_validator("bbox")
    @classmethod
    def _bbox_unit(cls, v: list[float]) -> list[float]:
        if any(not (0.0 <= x <= 1.0) for x in v):
            raise ValueError("bbox must be [x, y, w, h] normalised to 0-1")
        return v

    @field_validator("h3")
    @classmethod
    def _h3_hex(cls, v: str) -> str:
        v = v.lower()
        if not re.fullmatch(r"[0-9a-f]{15}", v) or not h3.is_valid_cell(v) or h3.get_resolution(v) != 9:
            raise ValueError("h3 must be a valid resolution-9 H3 cell")
        return v

    @field_validator("ts")
    @classmethod
    def _utc_timestamp(cls, v: str) -> str:
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("ts must be an ISO 8601 UTC timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("ts must be an ISO 8601 UTC timestamp")
        return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def create_app(data_dir: Path | None = None, events_file: Path | None = None) -> FastAPI:
    store = Store(data_dir=data_dir, events_file=events_file)
    app = FastAPI(title="Barn Owl API", version="0.1.0")
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*", "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_store() -> Store:
        return store

    def month_param(month: str | None = Query(default=None, pattern=MONTH_RE.pattern)) -> str | None:
        return month

    @app.get("/health")
    async def health(s: Store = Depends(get_store)):
        return {"ok": True, "events": s.n_events, "cells_source": str(s.cells_path())}

    @app.get("/cells")
    async def cells(month: str | None = Depends(month_param), s: Store = Depends(get_store)):
        try:
            data, _ = s.cells(month)
        except FileNotFoundError as e:
            raise HTTPException(503, f"no cells file: {e}")
        return data

    @app.get("/plan")
    async def plan(month: str | None = Depends(month_param), k: int | None = Query(default=None, ge=0, le=10_000),
                   s: Store = Depends(get_store)):
        try:
            data, _ = s.plan(month, k)
        except FileNotFoundError as e:
            raise HTTPException(503, f"no plan file: {e}")
        return data

    @app.get("/queue")
    async def queue(limit: int = Query(default=50, ge=1, le=2000), s: Store = Depends(get_store)):
        return {"events": s.queue(limit)}

    @app.get("/backtest")
    async def backtest(s: Store = Depends(get_store)):
        try:
            data, path = s.backtest()
        except FileNotFoundError as e:
            raise HTTPException(503, f"no backtest file: {e}")
        data.setdefault("source", str(path))
        return data

    @app.get("/placements")
    async def placements(h3: str | None = None, s: Store = Depends(get_store)):
        """Top node spots (H3 r11, ~50 m) inside a hexagon, each with a street tree to mount on."""
        try:
            data, _ = s.placements()
        except FileNotFoundError as e:
            raise HTTPException(503, f"no placements file: {e}")
        if h3 is None:
            return {"month": data.get("month"), "n_cells": len(data.get("cells", {}))}
        return {"month": data.get("month"), "h3": h3, "spots": data.get("cells", {}).get(h3, [])}

    @app.post("/event")
    async def post_event(event: Event, s: Store = Depends(get_store)):
        body = event.model_dump(by_alias=True)
        stored, post, accepted, known = s.add_event(body)
        tag = "ok" if accepted else "below-threshold(no update)"
        if not known:
            tag += " unknown-h3(prior 0.2)"
        print(f"EVENT node={stored['node_id']} h3={stored['h3']} class={stored['class']} conf={stored['conf']:.2f} "
              f"n_hits={stored['n_hits']} -> posterior mean {post.mean:.3f} "
              f"(a={post.alpha:.2f} b={post.beta:.2f} n={post.n_events}) [{tag}]", flush=True)
        return {"ok": True, "accepted": accepted, "h3": stored["h3"],
                "posterior": post.to_dict(), "score_b_updated": round(post.mean, 4)}

    @app.delete("/events")
    async def reset(x_demo_reset: str | None = Header(default=None), s: Store = Depends(get_store)):
        if x_demo_reset != "yes":
            raise HTTPException(403, "send header X-Demo-Reset: yes")
        n = s.reset()
        print(f"RESET cleared {n} events", flush=True)
        return {"ok": True, "cleared": n}

    @app.get("/stream")
    async def stream(request: Request, limit: int | None = Query(default=None, ge=0, le=10_000),
                     s: Store = Depends(get_store)):
        """Server-Sent Events: 'hello' on connect, then one 'event' per POST /event, 'reset' on DELETE /events.
        ?limit=N closes the stream after N messages (curl / tests)."""
        q = s.subscribe()

        async def gen():
            sent = 0
            try:
                yield f"event: hello\ndata: {json.dumps({'events': s.n_events})}\n\n"
                while limit is None or sent < limit:
                    if await request.is_disconnected():
                        break
                    try:
                        payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    kind = "reset" if payload.get("reset") else "event"
                    slim = {k: v for k, v in payload.items() if k != "crop_b64"}
                    if "crop_b64" in payload:
                        slim["crop_b64"] = payload["crop_b64"]  # the web app wants the thumbnail
                    yield f"event: {kind}\ndata: {json.dumps(slim)}\n\n"
                    sent += 1
            finally:
                s.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.exception_handler(json.JSONDecodeError)
    async def _bad_json(_: Request, exc: Exception):
        return JSONResponse({"ok": False, "detail": f"bad JSON: {exc}"}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        if request.url.path == "/event":
            return JSONResponse({"ok": False, "detail": "invalid event body"}, status_code=400)
        return JSONResponse({"detail": exc.errors()}, status_code=422)

    return app


app = create_app()
