"""xAI Responses tool loop for creating dashboards from bounded Night Owl data."""
from __future__ import annotations

import asyncio
import json
import math
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from contextlib import aclosing
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from dashboard_data import DATASETS, DashboardError, catalog, render_dashboard, run_query
from store import Store

XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
MAX_REQUEST_BYTES = 100_000
MAX_ROUNDS = 8
MAX_TOOL_CALLS = 16
MAX_HISTORY = 12
MAX_QUERY_PREVIEW = 40
MAX_TEXT = 6000
MAX_THINKING = 2000
MAX_SSE_EVENT_BYTES = 1_000_000
RATE_PER_MIN, RATE_PER_DAY = 10, 100
_hits: dict[str, deque[float]] = defaultdict(deque)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

QUERY_TOOL = {
    "type": "function", "name": "query_data",
    "description": ("Query allowlisted Night Owl data: the model month (cells, sites), the inspection backtest, recent events, "
                    "and NYC Open Data history (borough_months, zip_years, zips). Dates follow each dataset's date_format in the "
                    "catalog. filters narrows rows by dimension values; split_by pivots one metric by a second dimension so each "
                    "value becomes a y column. Count uses metrics ['records']."),
    "parameters": {"type": "object", "properties": {"query": {"type": "object", "properties": {
        "dataset": {"type": "string", "enum": list(DATASETS)},
        "group_by": {"type": "string"}, "split_by": {"type": "string"},
        "metrics": {"type": "array", "items": {"type": "string"}},
        "aggregation": {"type": "string", "enum": ["raw", "mean", "sum", "count"]},
        "borough": {"type": "string"},
        "filters": {"type": "object", "additionalProperties": {"anyOf": [{"type": "string"}, {"type": "number"},
                                                                          {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "number"}]}}]}},
        "start": {"type": "string"}, "end": {"type": "string"},
        "limit": {"type": "integer"}, "sort_by": {"type": "string"},
        "direction": {"type": "string", "enum": ["asc", "desc"]}},
        "required": ["dataset", "metrics", "aggregation"], "additionalProperties": False}},
        "required": ["query"], "additionalProperties": False},
}

PUBLISH_TOOL = {
    "type": "function", "name": "publish_dashboard",
    "description": "Publish a dashboard spec. Every card query runs on the server; x and y must match query result columns. Title at most 60 characters, description at most 160, card titles at most 60, optional card descriptions at most 140. Call this to finish a dashboard request.",
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
First use query_data to inspect relevant data, then publish_dashboard with 1–6 valid cards. Use the exact column keys
from the query results for x and y. Explain the result briefly after publishing, naming what each chart measures.
Datasets: cells and sites are one model month with no dates. backtest is a monthly citywide validation series.
borough_months (one row per borough per month since 2010), zip_years (one row per ZIP code area per year) and zips
(one row per ZIP code area comparing 2017–2019 with 2022–2025) come from NYC Open Data 311 rodent complaints, DOHMH
initial inspections and ACS income. Use borough_months for borough trends and COVID comparisons, zip_years for
income-band or neighborhood trends, and zips with sort_by and limit for rankings. "Richest" or "poorest" areas mean
ZIP code areas ranked by ACS median household income; the only cities are NYC boroughs and ZIP code areas.
The borough_months COVID period starts in March 2020. The zip_years COVID period covers calendar years 2020–2021,
including January–February 2020; use borough_months when the March boundary matters.
Use filters to narrow rows (for example filters {"borough": ["Bronx", "Manhattan"]} or {"period": "after COVID"}).
To put several boroughs, periods or income bands on one chart, set split_by to that dimension with one metric;
each value becomes its own y column. Use mean for rates such as complaints_per_100k and active_rate and sum for
counts; periods differ in length, so compare mean monthly values. Mean rates give each source row equal weight:
call these mean borough-month or ZIP-year rates, never a pooled inspection share or population-wide rate.
Mean median_income is an average of area medians, not the median income of all households in the group.
ZIP rankings cover the eligible areas described in the catalog, not every NYC ZIP code.
311 complaints and inspection findings are not rat counts, so say which one a chart shows. Model B estimates
active rat signs conditional on inspection. Event counts include queued detections, including rejected ones.
In publish_dashboard, each card's x and y must be column keys returned by that card's own query (a pivot returns
the split values as keys; a ranking must list its sort_by field in metrics). If a card is rejected, fix only that
card and publish again.
For follow-ups, revise the supplied dashboard using the user's chart selection; preserve useful cards. Do not claim a
chart exists until publish_dashboard succeeds. Use only the Night Owl data tools. Do not make external research
claims, request URLs or files, execute code, or ask for secrets."""


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 86_400:
        q.popleft()
    if len(q) >= RATE_PER_DAY or sum(now - stamp < 60 for stamp in q) >= RATE_PER_MIN:
        return False
    q.append(now)
    return True


def _provider(body: dict, emit: Callable[[str, str], None] = lambda _kind, _text: None) -> dict:
    """Streams one Responses round, handing text and reasoning-summary deltas to emit(); returns the completed response.

    Kept separate so tests never call xAI. It runs in a worker thread, so emit must be thread-safe."""
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise DashboardError("dashboard assistant is not configured")
    request = urllib.request.Request(XAI_RESPONSES_URL, data=json.dumps({**body, "stream": True}).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                              "Accept": "text/event-stream"})
    result = None
    text_sent = thinking_sent = 0

    def handle_event(data: str) -> bool:
        nonlocal result, text_sent, thinking_sent
        if data == "[DONE]":
            return True
        event = json.loads(data)
        kind = event.get("type") if isinstance(event, dict) else None
        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
            piece = event["delta"][:MAX_TEXT - text_sent]
            text_sent += len(piece)
            if piece:
                emit("delta", piece)
        elif kind == "response.reasoning_summary_text.delta" and isinstance(event.get("delta"), str):
            piece = event["delta"][:MAX_THINKING - thinking_sent]
            thinking_sent += len(piece)
            if piece:
                emit("thinking", piece)
        elif kind == "response.completed":
            result = event.get("response")
            return True
        elif kind in ("response.failed", "response.incomplete", "error"):
            raise DashboardError("xAI response did not complete")
        return False

    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=60) as response:
            data_lines: list[str] = []
            event_bytes = 0
            for raw in response:
                if callable(cancelled := getattr(emit, "cancelled", None)) and cancelled():
                    raise _RoundStopped()
                if len(raw) > MAX_SSE_EVENT_BYTES:
                    raise DashboardError("xAI returned an oversized stream event")
                line = raw.decode("utf-8", "strict").rstrip("\r\n")
                if not line:
                    if data_lines:
                        complete = handle_event("\n".join(data_lines))
                        data_lines.clear()
                        event_bytes = 0
                        if complete:
                            break
                elif line.startswith("data:"):
                    part = line[5:].lstrip(" ")
                    event_bytes += len(raw)
                    if event_bytes > MAX_SSE_EVENT_BYTES:
                        raise DashboardError("xAI returned an oversized stream event")
                    data_lines.append(part)
            if data_lines:
                handle_event("\n".join(data_lines))
    except urllib.error.HTTPError as exc:
        raise DashboardError(f"xAI request returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DashboardError("xAI request timed out or could not connect") from exc
    except DashboardError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise DashboardError("xAI returned an invalid stream") from exc
    if not isinstance(result, dict) or not isinstance(result.get("output"), list):
        raise DashboardError("xAI returned an invalid response")
    return result


async def _round(body: dict) -> AsyncIterator[tuple[str, Any]]:
    """Yields ("delta" | "thinking", text) while one provider round streams, then ("response", completed)."""
    events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=64)
    stopped = threading.Event()

    def offer(item: tuple[str, Any]) -> None:
        while not stopped.is_set():
            try:
                events.put(item, timeout=0.1)
                return
            except queue.Full:
                continue
        raise _RoundStopped()

    def work() -> None:
        try:
            item = ("response", _provider(body, _RoundEmitter(offer, stopped)))
        except _RoundStopped:
            return
        except Exception as exc:  # noqa: BLE001 - re-raised on the event loop
            item = ("raise", exc)
        if not stopped.is_set():
            try:
                offer(item)
            except _RoundStopped:
                pass

    threading.Thread(target=work, daemon=True).start()
    try:
        while True:
            try:
                kind, value = await asyncio.to_thread(events.get, True, 0.1)
            except queue.Empty:
                continue
            if kind == "raise":
                raise value
            yield kind, value
            if kind == "response":
                return
    finally:
        stopped.set()


class _RoundStopped(Exception):
    """The SSE consumer disconnected while the provider round was running."""


class _RoundEmitter:
    def __init__(self, offer: Callable[[tuple[str, Any]], None], stopped: threading.Event):
        self.offer = offer
        self.cancelled = stopped.is_set

    def __call__(self, kind: str, value: str) -> None:
        self.offer((kind, value))


def _query_detail(result: dict) -> str:
    query, labels = result["query"], {column["key"]: column["label"] for column in result["columns"]}
    metrics = ", ".join(labels.get(metric, metric) for metric in query["metrics"] if metric != "records") or "Record count"
    filters = ", ".join(", ".join(str(v) for v in values) for values in query.get("filters", {}).values())
    parts = [metrics, f"by {labels.get(query['group_by'], query['group_by']).lower()}" if query.get("group_by") else "",
             f"split by {query['split_by'].replace('_', ' ')}" if query.get("split_by") else "",
             query.get("borough") or "", filters[:80], f"{result['total_rows']} row{'s' if result['total_rows'] != 1 else ''}"]
    return " · ".join(part for part in parts if part)


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
    context: list[dict] = [{"role": "system", "content": SYSTEM + "\nCatalog: " + json.dumps(catalog(store), separators=(",", ":"))}]
    model = os.environ.get("XAI_DASHBOARD_MODEL") or os.environ.get("XAI_MODEL") or "grok-4.7"
    context += body["history"]
    message = body["message"]
    if body["dashboard"] is not None:
        message += "\nCurrent dashboard spec: " + json.dumps(body["dashboard"], separators=(",", ":"))
    if body["selection"] is not None:
        message += "\nSelected chart value: " + json.dumps(body["selection"], separators=(",", ":"))
    context.append({"role": "user", "content": message})
    artifact = None
    text = ""
    calls_used = 0
    for round_index in range(MAX_ROUNDS):
        yield {"type": "status", "text": "Thinking"}
        round_text = ""
        response: dict = {}
        async with aclosing(_round({"model": model, "input": context, "tools": tools,
                                    "store": False, "max_output_tokens": 2500})) as provider_stream:
            async for kind, value in provider_stream:
                if kind == "response":
                    response = value
                elif kind == "thinking":
                    yield {"type": "thinking", "text": value}
                elif kind == "delta" and len(text) < MAX_TEXT:
                    separator = "\n\n" if not round_text and text and not text.endswith("\n") else ""
                    piece = (separator + value)[:MAX_TEXT - len(text)]
                    if piece:
                        round_text += piece
                        text += piece
                        yield {"type": "delta", "text": piece}
        output = response["output"]
        context.extend(output)
        calls = [item for item in output if isinstance(item, dict) and item.get("type") == "function_call"]
        if not calls:
            if not round_text:  # final text may be unstreamed after an earlier tool round streamed prose
                final = _output_text(response).strip()[:MAX_TEXT - len(text)]
                if final:
                    if text and not text.endswith("\n"):
                        final = ("\n\n" + final)[:MAX_TEXT - len(text)]
                    text += final
                    yield {"type": "delta", "text": final}
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
                    raw_query = args.get("query")
                    dataset = raw_query.get("dataset") if isinstance(raw_query, dict) else None
                    label = DATASETS.get(dataset, {}).get("label", "Data") if isinstance(dataset, str) else "Data"
                    label = label[:1].lower() + label[1:] if label[1:2].islower() else label
                    yield {"type": "status", "text": f"Querying {label}"}
                    result = run_query(store, args.get("query"))
                    yield {"type": "step", "text": f"Queried {label}", "detail": _query_detail(result)}
                    result = {**result, "rows": result["rows"][:MAX_QUERY_PREVIEW],
                              "preview_rows": min(len(result["rows"]), MAX_QUERY_PREVIEW)}
                elif name == "publish_dashboard":
                    yield {"type": "status", "text": "Building dashboard"}
                    artifact = render_dashboard(store, args.get("spec"), body["version"])
                    count = len(artifact["results"])
                    yield {"type": "step", "text": "Built dashboard", "detail": f"{count} chart{'s' if count != 1 else ''}"}
                    yield {"type": "dashboard", "dashboard": artifact}
                    result = {"ok": True, "id": artifact["id"], "cards": list(artifact["results"]),
                              "total_rows": {key: value["total_rows"] for key, value in artifact["results"].items()}}
                else:
                    result = {"error": "unknown tool"}
            except DashboardError as exc:
                yield {"type": "step", "text": "Dashboard rejected" if name == "publish_dashboard" else "Query rejected",
                       "detail": str(exc)[:160], "error": True}
                result = {"error": str(exc)[:300]}
            except Exception:  # noqa: BLE001 - provider tool arguments must never expose internal errors
                yield {"type": "step", "text": "Dashboard rejected" if name == "publish_dashboard" else "Query rejected",
                       "detail": "The data tool failed", "error": True}
                result = {"error": "The data tool failed"}
            context.append({"type": "function_call_output", "call_id": call_id,
                            "output": json.dumps(result, separators=(",", ":"), allow_nan=False)})
        if round_index == MAX_ROUNDS - 1:
            if artifact is None:
                raise DashboardError("dashboard reasoning limit reached")
            break
    if artifact is not None and not text:
        yield {"type": "delta", "text": "Dashboard ready: " + artifact["spec"]["title"] + "."}
    if artifact is None and not text:
        yield {"type": "error", "text": "The assistant did not produce a dashboard or answer. Try a more specific request."}
    yield {"type": "done"}


def mount_dashboards(app: FastAPI, store: Store) -> None:
    @app.get("/dashboards/catalog")
    async def dashboard_catalog():
        return catalog(store)

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
                async with aclosing(agent_events(store, body)) as events:
                    async for event in events:
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
