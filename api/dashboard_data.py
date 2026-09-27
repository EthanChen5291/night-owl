"""Bounded, read-only datasets and chart validation for the dashboard assistant."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Any

from store import Store, utcnow_iso

MAX_ROWS = 500
MAX_CARDS = 6
SUM_METRICS = {"cells": {"n_inspections", "n_complaints_12m", "n_events"},
               "backtest": {"n_positives", "n_swept_cells"},
               "events": {"n_hits"}, "sites": set()}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CARD_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")

# Labels and units describe the wire values, rather than inventing a new measure.
DATASETS = {
    "cells": {
        "label": "Modelled NYC cells", "dimensions": ["h3", "borough", "neighborhood", "cd", "tier_risk", "tier_silent"],
        "metrics": {"score_a": ("Predicted complaint score", "model score"),
                    "score_b": ("Active rat signs if inspected", "probability"),
                    "pct_a": ("Complaint percentile", "percentile 0–100"),
                    "pct_b": ("Rat-risk percentile", "percentile 0–100"),
                    "silence": ("Risk minus complaint percentile", "percentile points"),
                    "n_inspections": ("Prior inspections", "inspections"),
                    "n_complaints_12m": ("Rat complaints, prior 12 months", "complaints"),
                    "n_events": ("Accepted sensor detections", "detections")},
        "notes": ["One exported model month; no historical cell-by-cell series.",
                  "Model B estimates active signs conditional on an inspection, not a rat count."],
    },
    "backtest": {
        "label": "Inspection backtest", "dimensions": ["month"],
        "metrics": {"precision_silent": ("Precision of silent picks", "fraction"),
                    "precision_311": ("Precision of complaint picks", "fraction"),
                    "precision_positives": ("Precision of prior-finding picks", "fraction"),
                    "precision_random": ("Precision of random picks", "fraction"),
                    "n_positives": ("Positive swept cells", "cells"),
                    "n_swept_cells": ("Swept cells", "cells")},
        "notes": ["Monthly aggregates for cells inspected by the city; no borough breakdown or per-cell backtest rows."],
    },
    "events": {
        "label": "Recent node events", "dimensions": ["ts", "day", "month", "class", "node_id", "h3", "borough"],
        "metrics": {"conf": ("Detector confidence", "fraction"), "n_hits": ("Detector hits", "hits")},
        "notes": ["Only the API's bounded recent-event ring is available; count means queued events, including rejected detections.",
                  "Crops and images are never included in dashboard queries.",
                  "Borough is joined from the current model cell snapshot and may be missing for an unknown H3."],
    },
    "sites": {
        "label": "Ranked owl sites", "dimensions": ["h3", "borough", "neighborhood", "tree_id"],
        "metrics": {"rank": ("Current site rank", "rank"),
                    "expected_gain": ("Expected information gain", "planner score"),
                    "silence": ("Risk minus complaint percentile", "percentile points")},
        "notes": ["One exported plan month; accepted detections may re-rank existing tree-backed sites."],
    },
}


class DashboardError(ValueError):
    pass


def catalog() -> dict:
    return {"datasets": {name: {"label": info["label"], "dimensions": info["dimensions"],
                                "metrics": {key: {"label": label, "unit": unit}
                                            for key, (label, unit) in info["metrics"].items()},
                                "notes": info["notes"], "aggregations": ["raw", "mean", "count"] + (["sum"] if SUM_METRICS[name] else []),
                                "sum_metrics": sorted(SUM_METRICS[name]),
                                "date_filter": name in ("events", "backtest")}
                         for name, info in DATASETS.items()},
            "count_metric": "records", "max_rows": MAX_ROWS, "max_cards": MAX_CARDS}


def _text(value: Any, label: str, max_len: int = 100) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise DashboardError(f"{label} must be nonempty text of at most {max_len} characters")
    return value.strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _safe(value: Any) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def validate_query(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) - {"dataset", "group_by", "metrics", "aggregation", "borough", "start", "end", "limit", "sort_by", "direction"}:
        raise DashboardError("query has unknown fields or is not an object")
    dataset = raw.get("dataset")
    if not isinstance(dataset, str) or dataset not in DATASETS:
        raise DashboardError("unknown dataset")
    info = DATASETS[dataset]
    aggregation = raw.get("aggregation")
    if aggregation not in ("raw", "mean", "sum", "count"):
        raise DashboardError("aggregation must be raw, mean, sum, or count")
    metrics = raw.get("metrics")
    if not isinstance(metrics, list) or not 1 <= len(metrics) <= 6 or any(not isinstance(m, str) for m in metrics) or len(set(metrics)) != len(metrics):
        raise DashboardError("metrics must contain 1–6 distinct field names")
    if aggregation == "count":
        if metrics != ["records"]:
            raise DashboardError("count requires metrics ['records']")
    elif any(m not in info["metrics"] for m in metrics):
        raise DashboardError("metric is not available for this dataset")
    if aggregation == "sum" and any(m not in SUM_METRICS[dataset] for m in metrics):
        raise DashboardError("sum is available only for additive count metrics")
    group = raw.get("group_by")
    if group is not None and group not in info["dimensions"]:
        raise DashboardError("group_by is not available for this dataset")
    borough = raw.get("borough")
    if borough is not None:
        if dataset == "backtest":
            raise DashboardError("backtest has no borough breakdown")
        borough = _text(borough, "borough", 80)
    start, end = raw.get("start"), raw.get("end")
    if (start is not None or end is not None) and dataset not in ("backtest", "events"):
        raise DashboardError("this dataset has only one snapshot; date range filtering is unavailable")
    if dataset == "backtest":
        for value in (start, end):
            if value is not None and (not isinstance(value, str) or not MONTH.fullmatch(value)):
                raise DashboardError("backtest dates must be YYYY-MM")
    elif dataset == "events":
        if start is not None:
            _event_bound(start, end=False)
        if end is not None:
            _event_bound(end, end=True)
    if start is not None and end is not None:
        if dataset == "backtest" and start > end:
            raise DashboardError("start must be before end")
        if dataset == "events" and _event_bound(start, end=False) > _event_bound(end, end=True):
            raise DashboardError("start must be before end")
    limit = raw.get("limit", 200)
    if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise DashboardError(f"limit must be an integer from 1 to {MAX_ROWS}")
    direction = raw.get("direction", "asc")
    if direction not in ("asc", "desc"):
        raise DashboardError("direction must be asc or desc")
    output_fields = set(metrics) | ({group} if group else {"scope"} if aggregation != "raw" else set())
    sort_by = raw.get("sort_by")
    if sort_by is not None and (not isinstance(sort_by, str) or sort_by not in output_fields):
        raise DashboardError("sort_by must be an output column")
    return {"dataset": dataset, **({"group_by": group} if group is not None else {}),
            "metrics": metrics, "aggregation": aggregation,
            **({"borough": borough} if borough is not None else {}),
            **({"start": start} if start is not None else {}), **({"end": end} if end is not None else {}),
            "limit": limit, **({"sort_by": sort_by} if sort_by is not None else {}), "direction": direction}


def _event_bound(value: Any, *, end: bool) -> datetime:
    if not isinstance(value, str):
        raise DashboardError("event dates must be UTC ISO dates or timestamps")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return datetime.combine(date.fromisoformat(value), time.max if end else time.min, timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise DashboardError("event dates must be UTC ISO dates or timestamps") from exc


def _records(store: Store, name: str) -> tuple[list[dict], dict]:
    if name == "cells":
        data, _ = store.cells()
        rows = [{**c, "n_events": (c.get("posterior") or {}).get("n_events")} for c in data.get("cells", [])]
        source = {"label": "NYC cell model", "as_of": data.get("month") or "unknown",
                  "kind": data.get("source", "model"), "notes": DATASETS[name]["notes"] +
                  (["Live accepted events are overlaid on this model month."] if any(r.get("n_events") for r in rows) else [])}
    elif name == "backtest":
        data, _ = store.backtest()
        rows = data.get("series", [])
        source = {"label": "Historical inspection backtest", "as_of": (data.get("window") or [None, "unknown"])[-1],
                  "kind": "fixture" if data.get("synthetic") else "model", "notes": DATASETS[name]["notes"]}
    elif name == "sites":
        data, _ = store.plan()
        cells, _ = store.cells(data.get("month"))
        by_h3 = {c["h3"]: c for c in cells.get("cells", [])} if cells.get("month") == data.get("month") else {}
        rows = [{**n, "borough": by_h3.get(n.get("h3"), {}).get("borough"),
                 "neighborhood": by_h3.get(n.get("h3"), {}).get("neighborhood")} for n in data.get("nodes", [])]
        source = {"label": "Owl placement plan", "as_of": data.get("month") or "unknown",
                  "kind": data.get("source", "model"), "notes": DATASETS[name]["notes"]}
    else:
        rows = store.queue(2000)
        event_times = sorted(str(e.get("ts")) for e in rows if e.get("ts"))
        cells, _ = store.cells()
        borough_by_h3 = {c["h3"]: c.get("borough") for c in cells.get("cells", [])}
        rows = [{"ts": e.get("ts"), "day": str(e.get("ts", ""))[:10], "month": str(e.get("ts", ""))[:7],
                 "class": e.get("class"), "node_id": e.get("node_id"), "h3": e.get("h3"),
                 "borough": borough_by_h3.get(e.get("h3")), "conf": e.get("conf"), "n_hits": e.get("n_hits")}
                for e in rows]
        window = (f"Retained {len(rows)} events from {event_times[0]} to {event_times[-1]}; not an all-time total."
                  if event_times else "No events are currently retained in the queue.")
        source = {"label": "Recent node event queue", "as_of": utcnow_iso(), "kind": "events",
                  "notes": DATASETS[name]["notes"] + [window]}
    return rows, source


def run_query(store: Store, raw: Any) -> dict:
    query = validate_query(raw)
    name, group, metrics, aggregation = query["dataset"], query.get("group_by"), query["metrics"], query["aggregation"]
    info = DATASETS[name]
    try:
        rows, source = _records(store, name)
    except FileNotFoundError as exc:
        raise DashboardError(f"{name} dataset is unavailable") from exc
    if "borough" in query:
        rows = [row for row in rows if str(row.get("borough") or "").casefold() == query["borough"].casefold()]
    if name == "backtest":
        rows = [row for row in rows if ("start" not in query or str(row.get("month", "")) >= query["start"])
                and ("end" not in query or str(row.get("month", "")) <= query["end"])]
    elif name == "events" and ("start" in query or "end" in query):
        low = _event_bound(query["start"], end=False) if "start" in query else None
        high = _event_bound(query["end"], end=True) if "end" in query else None
        def in_range(row: dict) -> bool:
            try:
                ts = _event_bound(row["ts"], end=False)
            except DashboardError:
                return False
            return (low is None or ts >= low) and (high is None or ts <= high)
        rows = [row for row in rows if in_range(row)]
    columns = ([{"key": group, "label": group.replace("_", " ").title(), "unit": ""}] if group else
               ([{"key": "scope", "label": "Scope", "unit": ""}] if aggregation != "raw" else []))
    columns += [{"key": metric, "label": "Records" if metric == "records" else info["metrics"][metric][0],
                 "unit": "events" if name == "events" and metric == "records" else "rows" if metric == "records" else info["metrics"][metric][1]}
                for metric in metrics]
    if aggregation == "raw":
        output = [{**({group: _safe(row.get(group))} if group else {}),
                   **{metric: _safe(row.get(metric)) for metric in metrics}} for row in rows]
    else:
        buckets: dict[Any, list[dict]] = defaultdict(list)
        for row in rows:
            buckets[_safe(row.get(group)) if group else "All rows"].append(row)
        if not rows and group is None:
            buckets["All rows"] = []
        output = []
        for value, subset in buckets.items():
            item = {group or "scope": value}
            for metric in metrics:
                if aggregation == "count":
                    item[metric] = len(subset)
                    continue
                numbers = [_number(row.get(metric)) for row in subset]
                present = [n for n in numbers if n is not None]
                if present:
                    value = sum(present) / len(present) if aggregation == "mean" else sum(present)
                    item[metric] = round(value, 6) if math.isfinite(value) else None
                else:
                    item[metric] = None
            output.append(item)
    sort_by = query.get("sort_by") or (group if group else None)
    if sort_by:
        present = [row for row in output if row.get(sort_by) is not None]
        missing = [row for row in output if row.get(sort_by) is None]
        present.sort(key=lambda row: row[sort_by].casefold() if isinstance(row[sort_by], str) else row[sort_by],
                     reverse=query["direction"] == "desc")
        output = present + missing
    total = len(output)
    return {"rows": output[:query["limit"]], "columns": columns, "source": source, "total_rows": total, "query": query}


def render_dashboard(store: Store, raw: Any, version: Any = 1) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"title", "description", "cards"}:
        raise DashboardError("spec must have title, description, and cards only")
    if type(version) is not int or not 1 <= version <= 1000:
        raise DashboardError("version must be an integer from 1 to 1000")
    title, description = _text(raw["title"], "title", 120), _text(raw["description"], "description", 500)
    cards = raw["cards"]
    if not isinstance(cards, list) or not 1 <= len(cards) <= MAX_CARDS:
        raise DashboardError(f"cards must contain 1–{MAX_CARDS} charts")
    cleaned, results, ids = [], {}, set()
    for card in cards:
        if not isinstance(card, dict) or set(card) - {"id", "title", "kind", "query", "x", "y", "description"}:
            raise DashboardError("card has unknown fields or is not an object")
        ident = card.get("id")
        if not isinstance(ident, str) or not CARD_ID.fullmatch(ident) or ident in ids:
            raise DashboardError("card id must be unique and use lowercase letters, numbers, _ or -")
        ids.add(ident)
        kind = card.get("kind")
        if kind not in ("bar", "line", "scatter", "table", "metric"):
            raise DashboardError("invalid chart kind")
        result = run_query(store, card.get("query"))
        keys = {c["key"] for c in result["columns"]}
        x, y = card.get("x"), card.get("y")
        if not isinstance(x, str) or x not in keys or not isinstance(y, list) or len(y) > 3 or any(not isinstance(k, str) or k not in keys for k in y) or len(set(y)) != len(y):
            raise DashboardError("chart x/y must refer to returned columns")
        if kind != "table" and not y:
            raise DashboardError("chart requires a y metric")
        if kind == "metric" and len(y) != 1:
            raise DashboardError("metric card requires one y metric")
        numeric = set(result["query"]["metrics"])
        if any(k not in numeric for k in y) or (kind == "scatter" and x not in numeric):
            raise DashboardError("chart y and scatter x must be numeric metrics")
        if kind in ("bar", "line") and len({next(c["unit"] for c in result["columns"] if c["key"] == k) for k in y}) > 1:
            raise DashboardError("chart y metrics must share a unit; use separate cards")
        if kind == "metric" and len(result["rows"]) != 1:
            raise DashboardError("metric card needs a single result row")
        if x in y:
            raise DashboardError("chart x and y must differ")
        cleaned.append({"id": ident, "title": _text(card.get("title"), "card title", 120), "kind": kind,
                        "query": result["query"], "x": x, "y": y,
                        **({"description": _text(card["description"], "card description", 400)} if "description" in card else {})})
        results[ident] = result
    spec = {"title": title, "description": description, "cards": cleaned}
    artifact = {"id": hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16],
                "version": version, "created_at": utcnow_iso(), "spec": spec, "results": results}
    return artifact
