"""xAI Responses tool loop for creating dashboards from bounded Night Owl data."""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from dashboard_data import DATASETS, DashboardError, catalog, render_dashboard, run_query
from store import Store

XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
MAX_REQUEST_BYTES = 100_000
MAX_ROUNDS = 5
MAX_TOOL_CALLS = 10
MAX_HISTORY = 12
MAX_QUERY_PREVIEW = 40
RATE_PER_MIN, RATE_PER_DAY = 10, 100
_hits: dict[str, deque[float]] = defaultdict(deque)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

QUERY_TOOL = {
    "type": "function", "name": "query_data",
    "description": "Query allowlisted Night Owl model, backtest, event, or site data. Dates are only supported for backtest and events. Count uses metrics ['records'].",
    "parameters": {"type": "object", "properties": {"query": {"type": "object", "properties": {
        "dataset": {"type": "string", "enum": list(DATASETS)},
        "group_by": {"type": "string"}, "metrics": {"type": "array", "items": {"type": "string"}},
        "aggregation": {"type": "string", "enum": ["raw", "mean", "sum", "count"]},
        "borough": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
        "limit": {"type": "integer"}, "sort_by": {"type": "string"},
        "direction": {"type": "string", "enum": ["asc", "desc"]}},
        "required": ["dataset", "metrics", "aggregation"], "additionalProperties": False}},
        "required": ["query"], "additionalProperties": False},
}

PUBLISH_TOOL = {
    "type": "function", "name": "publish_dashboard",
    "description": "Publish a dashboard spec. Every card query runs on the server; x and y must match query result columns. Call this to finish a dashboard request.",
    "parameters": {"type": "object", "properties": {"spec": {"type": "object", "properties": {
        "title": {"type": "string"}, "description": {"type": "string"},
        "cards": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"},
            "kind": {"type": "string", "enum": ["bar", "line", "scatter", "table", "metric"]},
            "query": QUERY_TOOL["parameters"]["properties"]["query"],
            "x": {"type": "string"}, "y": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"}},
            "required": ["id", "title", "kind", "query", "x", "y"], "additionalProperties": False}}},
        "required": ["title", "description", "cards"], "additionalProperties": False}},
        "required": ["spec"], "additionalProperties": False},
}

SYSTEM = """You build editable Night Owl dashboards from the supplied catalog and tool results. Never invent numbers.
First use query_data to inspect relevant data, then publish_dashboard with 1–6 valid cards. Use the exact field keys
from the query results for x and y. Explain the result briefly after publishing. A cell/site export is a single
model month, not a time series; only backtest and events have dates. Model B estimates active rat signs conditional
on inspection, not rat counts. Event counts include queued detections, including rejected ones. For follow-ups,
revise the supplied dashboard using the user's chart selection; preserve useful cards. Do not claim a chart exists
until publish_dashboard succeeds. Use only the Night Owl data tools. Do not make external research claims,
request URLs or files, execute code, or ask for secrets."""


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 86_400:
        q.popleft()
    if len(q) >= RATE_PER_DAY or sum(now - stamp < 60 for stamp in q) >= RATE_PER_MIN:
        return False
    q.append(now)
    return True


def _provider(body: dict) -> dict:
    """Kept separate so tests never call xAI and request cancellation can stop later rounds."""
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise DashboardError("dashboard assistant is not configured")
    request = urllib.request.Request(XAI_RESPONSES_URL, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise DashboardError(f"xAI request returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DashboardError("xAI request timed out or could not connect") from exc
    if not isinstance(result, dict) or not isinstance(result.get("output"), list):
        raise DashboardError("xAI returned an invalid response")
    return result


def _output_text(response: dict) -> str:
    return "\n".join(part.get("text", "") for item in response.get("output", []) if isinstance(item, dict)
                     and item.get("type") == "message" for part in item.get("content", [])
                     if isinstance(part, dict) and part.get("type") == "output_text")[:6000]


def _chat_body(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) - {"message", "history", "dashboard", "selection", "version"}:
        raise DashboardError("invalid chat request")
    message = raw.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise DashboardError("message must be 1–2000 characters")
    history = raw.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise DashboardError(f"history must contain at most {MAX_HISTORY} messages")
    for item in history:
        if (not isinstance(item, dict) or set(item) != {"role", "content"}
                or item["role"] not in ("user", "assistant") or not isinstance(item["content"], str)
                or len(item["content"]) > 4000):
            raise DashboardError("invalid chat history")
    version = raw.get("version", 1)
    if type(version) is not int or not 1 <= version <= 1000:
        raise DashboardError("version must be an integer from 1 to 1000")
    selection, dashboard = raw.get("selection"), raw.get("dashboard")
    if dashboard is not None:
        if (not isinstance(dashboard, dict) or not isinstance(dashboard.get("cards"), list)
                or len(dashboard["cards"]) > 6
                or any(not isinstance(card, dict) or not isinstance(card.get("id"), str)
                       or not isinstance(card.get("x"), str) or not isinstance(card.get("y"), list)
                       or any(not isinstance(field, str) for field in card["y"]) for card in dashboard["cards"])
                or len(json.dumps(dashboard)) > 30000):
            raise DashboardError("invalid dashboard context")
    if selection is not None:
        if (dashboard is None or not isinstance(selection, dict) or set(selection) != {"card_id", "field", "value"}
                or not isinstance(selection["card_id"], str) or not isinstance(selection["field"], str)
                or not (isinstance(selection["value"], str) and len(selection["value"]) <= 200
                        or isinstance(selection["value"], (int, float)) and not isinstance(selection["value"], bool)
                        and math.isfinite(selection["value"]))):
            raise DashboardError("invalid chart selection")
        card = next((c for c in dashboard.get("cards", []) if isinstance(c, dict) and c.get("id") == selection["card_id"]), None)
        if card is None or selection["field"] not in [card.get("x"), *(card.get("y") or [])]:
            raise DashboardError("selection is not in the current dashboard")
    return {"message": message.strip(), "history": history, "dashboard": dashboard, "selection": selection,
            "version": version}


async def agent_events(store: Store, body: dict) -> AsyncIterator[dict]:
    tools = [QUERY_TOOL, PUBLISH_TOOL]
    context: list[dict] = [{"role": "system", "content": SYSTEM + "\nCatalog: " + json.dumps(catalog(), separators=(",", ":"))}]
    model = os.environ.get("XAI_DASHBOARD_MODEL") or os.environ.get("XAI_MODEL") or "grok-4.7"
    context += body["history"]
    message = body["message"]
    if body["dashboard"] is not None:
        message += "\nCurrent dashboard spec: " + json.dumps(body["dashboard"], separators=(",", ":"))
    if body["selection"] is not None:
        message += "\nSelected chart value: " + json.dumps(body["selection"], separators=(",", ":"))
    context.append({"role": "user", "content": message})
    artifact = None
    final_text = ""
    calls_used = 0
    for round_index in range(MAX_ROUNDS):
        yield {"type": "status", "text": "Working with Night Owl data…"}
        response = await asyncio.to_thread(_provider, {"model": model, "input": context, "tools": tools,
                                                       "store": False, "max_output_tokens": 2500})
        output = response["output"]
        context.extend(output)
        calls = [item for item in output if isinstance(item, dict) and item.get("type") == "function_call"]
        if not calls:
            final_text = _output_text(response)
            break
        calls_used += len(calls)
        if calls_used > MAX_TOOL_CALLS:
            raise DashboardError("dashboard tool limit reached")
        for call in calls:
            name, call_id = call.get("name"), call.get("call_id")
            if not isinstance(call_id, str) or not call_id:
                raise DashboardError("xAI returned an invalid tool call")
            try:
                args = json.loads(call.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise DashboardError("tool arguments must be an object")
                if name == "query_data":
                    result = run_query(store, args.get("query"))
                    result = {**result, "rows": result["rows"][:MAX_QUERY_PREVIEW],
                              "preview_rows": min(len(result["rows"]), MAX_QUERY_PREVIEW)}
                    yield {"type": "status", "text": "Queried " + result["source"]["label"]}
                elif name == "publish_dashboard":
                    artifact = render_dashboard(store, args.get("spec"), body["version"])
                    result = {"ok": True, "id": artifact["id"], "cards": list(artifact["results"]),
                              "total_rows": {key: value["total_rows"] for key, value in artifact["results"].items()}}
                    yield {"type": "status", "text": "Dashboard ready"}
                else:
                    result = {"error": "unknown tool"}
            except (DashboardError, TypeError, ValueError) as exc:
                result = {"error": str(exc)[:300]}
            context.append({"type": "function_call_output", "call_id": call_id,
                            "output": json.dumps(result, separators=(",", ":"), allow_nan=False)})
        if round_index == MAX_ROUNDS - 1:
            if artifact is None:
                raise DashboardError("dashboard reasoning limit reached")
            break
    text = final_text.strip()
    if artifact is not None and not text:
        text = "Dashboard ready: " + artifact["spec"]["title"] + "."
    if artifact is not None:
        yield {"type": "dashboard", "dashboard": artifact}
    if text:
        for offset in range(0, len(text), 500):
            yield {"type": "delta", "text": text[offset:offset + 500]}
    if artifact is None and not text:
        yield {"type": "error", "text": "The assistant did not produce a dashboard or answer. Try a more specific request."}
    yield {"type": "done"}


def mount_dashboards(app: FastAPI, store: Store) -> None:
    @app.get("/dashboards/catalog")
    async def dashboard_catalog():
        return catalog()

    @app.post("/dashboards/query")
    async def dashboard_query(request: Request):
        try:
            return run_query(store, await _json_body(request))
        except DashboardError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/dashboards/render")
    async def dashboard_render(request: Request):
        try:
            body = await _json_body(request)
            if not isinstance(body, dict) or set(body) - {"spec", "version"}:
                raise DashboardError("invalid render request")
            return render_dashboard(store, body.get("spec"), body.get("version", 1))
        except DashboardError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/dashboards/chat")
    async def dashboard_chat(request: Request):
        if not os.environ.get("XAI_API_KEY"):
            raise HTTPException(503, "dashboard assistant is not configured")
        try:
            body = _chat_body(await _json_body(request))
        except DashboardError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not _rate_ok(request.client.host if request.client else "?"):
            raise HTTPException(429, "too many dashboard requests")

        async def stream():
            try:
                async for event in agent_events(store, body):
                    if await request.is_disconnected():
                        break
                    yield "data: " + json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n\n"
            except asyncio.CancelledError:
                raise
            except DashboardError as exc:
                yield "data: " + json.dumps({"type": "error", "text": str(exc)}) + "\n\n"
                yield 'data: {"type":"done"}\n\n'
            except Exception:
                yield 'data: {"type":"error","text":"Dashboard assistant failed"}\n\n'
                yield 'data: {"type":"done"}\n\n'

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _json_body(request: Request) -> Any:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST_BYTES:
            raise DashboardError("request is too large")
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise DashboardError("invalid JSON") from exc
