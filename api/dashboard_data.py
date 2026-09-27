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
MAX_SERIES = 6
MAX_FILTERS = 4
MAX_FILTER_VALUES = 20
MAX_SPLIT_VALUES = 12
HISTORY_COUNTS = {"n_complaints", "n_rat_sightings", "n_inspections", "n_active"}
SUM_METRICS = {"cells": {"n_inspections", "n_complaints_12m", "n_events"},
               "backtest": {"n_positives", "n_swept_cells"},
               "events": {"n_hits"}, "sites": set(),
               "borough_months": set(HISTORY_COUNTS), "zip_years": set(HISTORY_COUNTS), "zips": set()}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
YEAR = re.compile(r"^\d{4}$")
CARD_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
# Datasets with a date range: (field, pattern, human format). Events use timestamps and are validated separately.
DATE_FIELDS = {"backtest": ("month", MONTH, "YYYY-MM"), "borough_months": ("month", MONTH, "YYYY-MM"),
               "zip_years": ("year", YEAR, "YYYY"), "events": ("ts", None, "UTC ISO dates or timestamps")}
HISTORY_DATASETS = ("borough_months", "zip_years", "zips")

_HISTORY_METRICS = {"n_complaints": ("311 rodent complaints", "complaints"),
                    "n_rat_sightings": ("311 rat sightings", "complaints"),
                    "n_inspections": ("Initial rodent inspections", "inspections"),
                    "n_active": ("Inspections finding rat activity", "inspections"),
                    "active_rate": ("Share of inspections finding rat activity", "fraction")}
_ACS_METRICS = {"median_income": ("Median household income (ACS)", "USD"),
                "population": ("Residents (ACS)", "residents")}

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
    "borough_months": {
        "label": "Borough complaint and inspection history", "dimensions": ["month", "year", "borough", "period"],
        "metrics": {**_HISTORY_METRICS,
                    "complaints_per_100k": ("Monthly complaints per 100k residents", "per 100k residents"),
                    **_ACS_METRICS},
        "notes": ["One row per borough per complete month since 2010-01 from NYC Open Data 311 and DOHMH inspections; sum counts for totals, mean for rates.",
                  "period is before COVID (through 2020-02), COVID (2020-03 to 2021-12) or after COVID (from 2022-01); periods differ in length, so compare mean monthly values rather than sums.",
                  "Complaints are 311 reports and inspections are city visits; neither is a count of rats.",
                  "Population and income are one ACS 5-year estimate applied to every month."],
    },
    "zip_years": {
        "label": "ZIP code area yearly history", "dimensions": ["zip", "neighborhood", "borough", "year", "period", "income_band"],
        "metrics": {**_HISTORY_METRICS,
                    "complaints_per_100k": ("Yearly complaints per 100k residents", "per 100k residents"),
                    **_ACS_METRICS},
        "notes": ["One row per ZIP code area per calendar year since 2010; the current year is partial.",
                  "ZIP year period uses calendar years: before COVID is 2010–2019, COVID is 2020–2021 (including January–February 2020), and after COVID starts in 2022. Use borough_months for the March 2020 boundary.",
                  "income_band splits the areas into fifths by ACS median household income, Q1 lowest to Q5 highest; filter it or borough and group by year to compare trends.",
                  "Complaints are 311 reports and inspections are city visits; neither is a count of rats.",
                  "ZIP coverage includes areas with at least 1,000 ACS residents, known income, and 50 rodent complaints across the history window.",
                  "Population and income are one ACS 5-year estimate applied to every year."],
    },
    "zips": {
        "label": "ZIP code areas before and after COVID", "dimensions": ["zip", "neighborhood", "borough", "income_band"],
        "metrics": {**_ACS_METRICS,
                    "income_rank": ("Income rank, 1 = highest", "rank"),
                    "complaints_per_year_pre": ("Complaints per year, 2017–2019", "complaints"),
                    "complaints_per_year_post": ("Complaints per year, 2022–2025", "complaints"),
                    "complaints_change_pct": ("Change in yearly complaints", "%"),
                    "complaints_per_100k_pre": ("Yearly complaints per 100k residents, 2017–2019", "per 100k residents"),
                    "complaints_per_100k_post": ("Yearly complaints per 100k residents, 2022–2025", "per 100k residents"),
                    "inspections_per_year_pre": ("Inspections per year, 2017–2019", "inspections"),
                    "inspections_per_year_post": ("Inspections per year, 2022–2025", "inspections"),
                    "active_rate_pre": ("Share of inspections finding rat activity, 2017–2019", "fraction"),
                    "active_rate_post": ("Share of inspections finding rat activity, 2022–2025", "fraction")},
        "notes": ["One row per ZIP code area; use raw aggregation with sort_by and limit for rankings, for example the richest areas by median_income.",
                  "pre is the 2017–2019 yearly mean and post is 2022–2025; 2020–2021 are excluded.",
                  "ACS top-codes median household income at $250,001.",
                  "Rankings cover areas with at least 1,000 ACS residents, known income, and 50 rodent complaints across the history window."],
    },
}


class DashboardError(ValueError):
    pass


def catalog(store: Store | None = None) -> dict:
    result = {"datasets": {name: {"label": info["label"], "dimensions": info["dimensions"],
                                  "metrics": {key: {"label": label, "unit": unit}
                                              for key, (label, unit) in info["metrics"].items()},
                                  "notes": info["notes"], "aggregations": ["raw", "mean", "count"] + (["sum"] if SUM_METRICS[name] else []),
                                  "sum_metrics": sorted(SUM_METRICS[name]),
                                  "date_filter": name in DATE_FIELDS,
                                  "date_format": DATE_FIELDS[name][2] if name in DATE_FIELDS else None}
                           for name, info in DATASETS.items()},
              "count_metric": "records", "max_rows": MAX_ROWS, "max_cards": MAX_CARDS,
              "filters": f"filters maps up to {MAX_FILTERS} dimensions to a value or list of values (case-insensitive equality)",
              "split_by": f"split_by pivots one metric by a second dimension (at most {MAX_SPLIT_VALUES} values); each value becomes a y column"}
    if store is not None:
        try:
            history, _ = store.history()
        except (OSError, ValueError):
            history = None
        if isinstance(history, dict):
            result["history"] = {key: history.get(key) for key in ("window", "periods", "zip_windows", "acs_release")}
            window = history.get("window")
            last_month = window[-1] if isinstance(window, list) and window and isinstance(window[-1], str) else None
            last_year = last_month[:4] if last_month and MONTH.fullmatch(last_month) else "unknown"
            result["history"]["zip_periods"] = history.get("zip_periods") or {
                "before COVID": "2010 to 2019", "COVID": "2020 to 2021 (includes January–February 2020)",
                "after COVID": f"2022 to {last_year}" + (f" ({last_year} partial through {last_month})" if last_month and last_month[5:] != "12" else "")}
            result["history"]["income_bands"] = [{"band": b.get("band"), "min_income": b.get("min_income"), "max_income": b.get("max_income")}
                                                 for b in history.get("income_bands", []) if isinstance(b, dict)]
    return result


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


def _match_key(value: Any) -> str:
    """Comparison form for filter values and split columns: numbers print without a trailing .0."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip().casefold()


def validate_query(raw: Any) -> dict:
    if not isinstance(raw, dict) or set(raw) - {"dataset", "group_by", "split_by", "metrics", "aggregation", "borough", "filters",
                                                "start", "end", "limit", "sort_by", "direction"}:
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
    split = raw.get("split_by")
    if split is not None:
        if split not in info["dimensions"] or split == group:
            raise DashboardError("split_by must be a dataset dimension different from group_by")
        if aggregation == "raw" or group is None or len(metrics) != 1:
            raise DashboardError("split_by requires group_by, one metric, and mean, sum, or count")
    borough = raw.get("borough")
    if borough is not None:
        if "borough" not in info["dimensions"]:
            raise DashboardError(f"{dataset} has no borough breakdown")
        borough = _text(borough, "borough", 80)
    filters = raw.get("filters")
    clean_filters: dict[str, list[str | int | float]] = {}
    if filters is not None:
        if not isinstance(filters, dict) or not filters or len(filters) > MAX_FILTERS:
            raise DashboardError(f"filters must map 1–{MAX_FILTERS} dimensions to values")
        for dim, values in filters.items():
            if dim not in info["dimensions"]:
                raise DashboardError("filter dimension is not available for this dataset")
            values = values if isinstance(values, list) else [values]
            if not 1 <= len(values) <= MAX_FILTER_VALUES:
                raise DashboardError(f"each filter takes 1–{MAX_FILTER_VALUES} values")
            cleaned = []
            for value in values:
                if isinstance(value, str):
                    cleaned.append(_text(value, f"filter {dim}", 80))
                elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    cleaned.append(value)
                else:
                    raise DashboardError("filter values must be text or numbers")
            clean_filters[dim] = cleaned
    start, end = raw.get("start"), raw.get("end")
    if (start is not None or end is not None) and dataset not in DATE_FIELDS:
        raise DashboardError("this dataset has only one snapshot; date range filtering is unavailable")
    if dataset == "events":
        if start is not None:
            _event_bound(start, end=False)
        if end is not None:
            _event_bound(end, end=True)
    elif dataset in DATE_FIELDS:
        _field, pattern, human = DATE_FIELDS[dataset]
        for value in (start, end):
            if value is not None and (not isinstance(value, str) or not pattern.fullmatch(value)):
                raise DashboardError(f"{dataset} dates must be {human}")
    if start is not None and end is not None:
        if dataset == "events" and _event_bound(start, end=False) > _event_bound(end, end=True):
            raise DashboardError("start must be before end")
        if dataset != "events" and start > end:
            raise DashboardError("start must be before end")
    limit = raw.get("limit", MAX_ROWS)
    if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise DashboardError(f"limit must be an integer from 1 to {MAX_ROWS}")
    direction = raw.get("direction", "asc")
    if direction not in ("asc", "desc"):
        raise DashboardError("direction must be asc or desc")
    output_fields = set(metrics) | ({group} if group else {"scope"} if aggregation != "raw" else set())
    sort_by = raw.get("sort_by")
    if sort_by is not None and (not isinstance(sort_by, str) or (split is None and sort_by not in output_fields) or len(sort_by) > 200):
        raise DashboardError(f"sort_by must be an output column; this query returns {', '.join(sorted(output_fields))}"
                             " (add the field to metrics to sort by it)")
    return {"dataset": dataset, **({"group_by": group} if group is not None else {}),
            **({"split_by": split} if split is not None else {}),
            "metrics": metrics, "aggregation": aggregation,
            **({"borough": borough} if borough is not None else {}),
            **({"filters": clean_filters} if clean_filters else {}),
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
    elif name in HISTORY_DATASETS:
        data, _ = store.history()
        rows = [row for row in data.get(name, []) if isinstance(row, dict)]
        window = data.get("window") or [None, "unknown"]
        source = {"label": "NYC Open Data history", "as_of": window[-1], "kind": "history",
                  "notes": DATASETS[name]["notes"] +
                  [f"311 rodent complaints and DOHMH initial inspections from {window[0]} to {window[-1]}; "
                   f"income and population from the {data.get('acs_release', 'ACS 5-year')} estimate."]}
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


def _aggregate(subset: list[dict], metric: str, aggregation: str) -> int | float | None:
    if aggregation == "count":
        return len(subset)
    present = [n for n in (_number(row.get(metric)) for row in subset) if n is not None]
    if not present:
        return None
    value = sum(present) / len(present) if aggregation == "mean" else sum(present)
    return round(value, 6) if math.isfinite(value) else None


def run_query(store: Store, raw: Any) -> dict:
    query = validate_query(raw)
    name, group, split = query["dataset"], query.get("group_by"), query.get("split_by")
    metrics, aggregation = query["metrics"], query["aggregation"]
    info = DATASETS[name]
    try:
        rows, source = _records(store, name)
    except FileNotFoundError as exc:
        raise DashboardError(f"{name} dataset is unavailable") from exc
    if "borough" in query:
        rows = [row for row in rows if str(row.get("borough") or "").casefold() == query["borough"].casefold()]
    for dim, values in query.get("filters", {}).items():
        wanted = {_match_key(value) for value in values}
        rows = [row for row in rows if row.get(dim) is not None and _match_key(row.get(dim)) in wanted]
    if name in DATE_FIELDS and name != "events":
        field = DATE_FIELDS[name][0]
        rows = [row for row in rows if ("start" not in query or _match_key(row.get(field, "")) >= query["start"])
                and ("end" not in query or _match_key(row.get(field, "")) <= query["end"])]
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
    columns = ([{"key": group, "label": group.replace("_", " ").title(), "unit": "year" if group == "year" else ""}] if group else
               ([{"key": "scope", "label": "Scope", "unit": ""}] if aggregation != "raw" else []))
    metric_unit = {metric: "events" if name == "events" and metric == "records" else "rows" if metric == "records" else info["metrics"][metric][1]
                   for metric in metrics}
    if aggregation == "raw":
        columns += [{"key": metric, "label": info["metrics"][metric][0], "unit": metric_unit[metric]} for metric in metrics]
        output = [{**({group: _safe(row.get(group))} if group else {}),
                   **{metric: _safe(row.get(metric)) for metric in metrics}} for row in rows]
    elif split:
        metric = metrics[0]
        buckets: dict[Any, dict[Any, list[dict]]] = defaultdict(lambda: defaultdict(list))
        split_values: dict[str, Any] = {}
        for row in rows:
            value = _safe(row.get(split))
            if value is None:
                continue
            key = str(int(value) if isinstance(value, float) and value.is_integer() else value)
            split_values.setdefault(key, value)
            buckets[_safe(row.get(group))][key].append(row)
        if len(split_values) > MAX_SPLIT_VALUES:
            raise DashboardError(f"split_by produced more than {MAX_SPLIT_VALUES} values; add filters or choose another dimension")
        ordered = sorted(split_values, key=lambda k: (not isinstance(split_values[k], (int, float)),
                                                      split_values[k] if isinstance(split_values[k], (int, float)) else k.casefold()))
        column_key = {key: f"{split}_{key}" if key == group else key for key in ordered}  # a value may spell the group key
        columns += [{"key": column_key[key], "label": key, "unit": metric_unit[metric]} for key in ordered]
        output = [{group: value, **{column_key[key]: _aggregate(subset[key], metric, aggregation) if key in subset else None
                                    for key in ordered}} for value, subset in buckets.items()]
    else:
        columns += [{"key": metric, "label": "Records" if metric == "records" else info["metrics"][metric][0], "unit": metric_unit[metric]}
                    for metric in metrics]
        buckets: dict[Any, list[dict]] = defaultdict(list)
        for row in rows:
            buckets[_safe(row.get(group)) if group else "All rows"].append(row)
        if not rows and group is None:
            buckets["All rows"] = []
        output = [{group or "scope": value, **{metric: _aggregate(subset, metric, aggregation) for metric in metrics}}
                  for value, subset in buckets.items()]
    keys = {column["key"] for column in columns}
    sort_by = query.get("sort_by") or (group if group else None)
    if sort_by is not None and sort_by not in keys:
        raise DashboardError(f"sort_by must be an output column; this query returns {', '.join(column['key'] for column in columns)}")
    if sort_by:
        present = [row for row in output if row.get(sort_by) is not None]
        missing = [row for row in output if row.get(sort_by) is None]
        present.sort(key=lambda row: row[sort_by].casefold() if isinstance(row[sort_by], str) else row[sort_by],
                     reverse=query["direction"] == "desc")
        output = present + missing
    if name in HISTORY_DATASETS and aggregation == "mean":
        row_unit = {"borough_months": "borough-month", "zip_years": "ZIP-year", "zips": "ZIP area"}[name]
        source["notes"] = [*source["notes"],
                           f"Means give each {row_unit} with a value equal weight. Mean inspection-positive shares are not the pooled share of inspections; mean household incomes average area medians."]
        if not split:
            for column in columns:
                if column["key"] in metrics:
                    label = column["label"]
                    if column["key"].startswith("active_rate"):
                        label = label.replace("Share of inspections finding rat activity", "Inspection-positive share")
                    elif column["key"] == "median_income":
                        label = "Area median household income (ACS)"
                    column["label"] = f"Mean {label[:1].lower() + label[1:]} per {row_unit}"
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
        if not isinstance(x, str) or x not in keys or not isinstance(y, list) or len(y) > MAX_SERIES or any(not isinstance(k, str) or k not in keys for k in y) or len(set(y)) != len(y):
            wanted = [x] + (y if isinstance(y, list) else [])
            missing = [str(k)[:40] for k in wanted if not isinstance(k, str) or k not in keys]
            raise DashboardError(f"card '{ident}': x and up to {MAX_SERIES} distinct y keys must be columns of its own query result; "
                                 f"missing {', '.join(missing) or 'none'}; returned {', '.join(c['key'] for c in result['columns'])}")
        if kind != "table" and not y:
            raise DashboardError("chart requires a y metric")
        if kind == "metric" and len(y) != 1:
            raise DashboardError("metric card requires one y metric")
        label_key = result["query"].get("group_by") or ("scope" if result["query"]["aggregation"] != "raw" else None)
        numeric = keys - {label_key}
        if any(k not in numeric for k in y) or (kind == "scatter" and x not in numeric):
            raise DashboardError(f"card '{ident}': chart y and scatter x must be numeric metrics, not the {label_key} column")
        if kind in ("bar", "line") and len({next(c["unit"] for c in result["columns"] if c["key"] == k) for k in y}) > 1:
            raise DashboardError(f"card '{ident}': chart y metrics must share a unit; use separate cards")
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
