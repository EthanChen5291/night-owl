#!/usr/bin/env python3
"""Build model/out/history.json: dated rat complaint and inspection history for the dashboard assistant.

Everything is fetched as server-side aggregates, so no raw CSV is downloaded:
  311 rodent complaints   NYC Open Data 76ig-c548 (2010–2019) and erm2-nwe9 (2020→), Complaint Type = Rodent
  DOHMH rodent inspections NYC Open Data p937-wjvj, Initial inspections only; "active" = result names Rat Activity
  Income and population    ACS 5-year via api.censusreporter.org (no key): B19013 median household income, B01003 population
  ZIP neighborhood names   DOHMH MODZCTA table (github.com/nychealth/coronavirus-data), optional

Output tables (see dashboard_data.DATASETS for the served fields):
  borough_months  one row per borough per complete month since 2010-01
  zip_years       one row per ZIP code area per calendar year (the current year is partial)
  zips            one row per ZIP code area comparing 2017–2019 with 2022–2025

Run: ./data/fetch_history.py [--out model/out/history.json]
Optional SOCRATA_APP_TOKEN in the environment raises the NYC Open Data rate limit.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOCRATA = "https://data.cityofnewyork.us/resource/{id}.json"
CENSUS_REPORTER = "https://api.censusreporter.org/1.0/data/show/latest"
MODZCTA_URL = "https://raw.githubusercontent.com/nychealth/coronavirus-data/master/totals/data-by-modzcta.csv"
COMPLAINTS = [("76ig-c548", "2010-01-01", "2020-01-01"), ("erm2-nwe9", "2020-01-01", None)]
INSPECTIONS = "p937-wjvj"
COUNTIES = {"Bronx": "05000US36005", "Brooklyn": "05000US36047", "Manhattan": "05000US36061",
            "Queens": "05000US36081", "Staten Island": "05000US36085"}
BOROUGHS = list(COUNTIES)
FIRST_MONTH = "2010-01"
PRE_YEARS, POST_YEARS = range(2017, 2020), range(2022, 2026)
MIN_POPULATION = 1000
MIN_COMPLAINTS = 50
PAGE = 50000


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 300) -> bytes:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "NightOwl history fetch", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise
            log(f"  retry after {exc}")
    raise RuntimeError("unreachable")


def soql(dataset: str, select: str, where: str, group: str) -> list[dict]:
    headers = {"X-App-Token": os.environ["SOCRATA_APP_TOKEN"]} if os.environ.get("SOCRATA_APP_TOKEN") else {}
    rows: list[dict] = []
    offset = 0
    while True:
        page = json.loads(fetch(SOCRATA.format(id=dataset), {"$select": select, "$where": where, "$group": group,
                                                            "$order": group, "$limit": PAGE, "$offset": offset}, headers))
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def borough_name(value: str | None) -> str | None:
    if not value:
        return None
    name = " ".join(part.capitalize() for part in value.split())
    return name if name in COUNTIES else None


def zip5(value: str | None) -> str | None:
    value = (value or "").strip()[:5]
    return value if len(value) == 5 and value.isdigit() else None


def month_period(month: str) -> str:
    return "before COVID" if month < "2020-03" else "COVID" if month < "2022-01" else "after COVID"


def year_period(year: int) -> str:
    return "before COVID" if year < 2020 else "COVID" if year < 2022 else "after COVID"


def rate(numerator: float | int | None, denominator: float | int | None, scale: float = 1.0, digits: int = 4) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator * scale, digits)


def complaint_rows(select_time: str, extra_group: str, last_month: str) -> list[dict]:
    out: list[dict] = []
    for dataset, start, end in COMPLAINTS:
        where = f"complaint_type='Rodent' and created_date >= '{start}T00:00:00' and created_date < '{last_month_end(last_month)}T00:00:00'"
        if end:
            where += f" and created_date < '{end}T00:00:00'"
        log(f"311 {dataset}: {select_time} by {extra_group}")
        out += soql(dataset, f"{select_time}, {extra_group}, descriptor, count(*) as n", where, f"t, {extra_group}, descriptor")
    return out


def last_month_end(last_month: str) -> str:
    year, month = int(last_month[:4]), int(last_month[5:])
    return date(year + (month == 12), month % 12 + 1, 1).isoformat()


def inspection_rows(select_time: str, extra_group: str, last_month: str) -> list[dict]:
    where = (f"inspection_type='Initial' and inspection_date >= '{FIRST_MONTH}-01T00:00:00' "
             f"and inspection_date < '{last_month_end(last_month)}T00:00:00'")
    log(f"inspections {INSPECTIONS}: {select_time} by {extra_group}")
    return soql(INSPECTIONS, f"{select_time}, {extra_group}, result, count(*) as n", where, f"t, {extra_group}, result")


def is_active(result: str | None) -> bool:
    return "rat activity" in (result or "").lower()


def census(geo_ids: list[str]) -> dict[str, tuple[float | None, float | None, str]]:
    """geo id -> (median income, population, release name)."""
    out: dict[str, tuple[float | None, float | None, str]] = {}
    for start in range(0, len(geo_ids), 200):
        chunk = geo_ids[start:start + 200]
        data = json.loads(fetch(CENSUS_REPORTER, {"table_ids": "B19013,B01003", "geo_ids": ",".join(chunk)}, timeout=120))
        release = data.get("release", {}).get("name", "ACS 5-year")
        for geo, tables in data.get("data", {}).items():
            income = tables.get("B19013", {}).get("estimate", {}).get("B19013001")
            population = tables.get("B01003", {}).get("estimate", {}).get("B01003001")
            out[geo] = (income, population, release)
    return out


def neighborhoods() -> dict[str, str]:
    try:
        text = fetch(MODZCTA_URL, timeout=60).decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        log(f"neighborhood names unavailable ({exc}); ZIP codes will be shown without names")
        return {}
    names: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get("NEIGHBORHOOD_NAME") or "").strip()
        for value in (row.get("label") or row.get("MODIFIED_ZCTA") or "").split(","):
            if zip5(value) and name:
                names[zip5(value)] = name
    return names


def build(last_month: str) -> dict:
    # ---- borough × month ----
    complaints = complaint_rows("date_trunc_ym(created_date) as t", "borough", last_month)
    inspections = inspection_rows("date_trunc_ym(inspection_date) as t", "borough", last_month)
    monthly: dict[tuple[str, str], dict] = defaultdict(lambda: {"n_complaints": 0, "n_rat_sightings": 0, "n_inspections": 0, "n_active": 0})
    for row in complaints:
        borough, month = borough_name(row.get("borough")), str(row.get("t", ""))[:7]
        if borough and FIRST_MONTH <= month <= last_month:
            n = int(row["n"])
            monthly[(borough, month)]["n_complaints"] += n
            if row.get("descriptor") == "Rat Sighting":
                monthly[(borough, month)]["n_rat_sightings"] += n
    for row in inspections:
        borough, month = borough_name(row.get("borough")), str(row.get("t", ""))[:7]
        if borough and FIRST_MONTH <= month <= last_month:
            n = int(row["n"])
            monthly[(borough, month)]["n_inspections"] += n
            monthly[(borough, month)]["n_active"] += n if is_active(row.get("result")) else 0

    county = census(list(COUNTIES.values()))
    release = next(iter(county.values()))[2] if county else "ACS 5-year"
    borough_pop = {name: county.get(geo, (None, None, ""))[1] for name, geo in COUNTIES.items()}
    borough_income = {name: county.get(geo, (None, None, ""))[0] for name, geo in COUNTIES.items()}

    months = sorted({m for _, m in monthly})
    borough_months = []
    for month in months:
        for borough in BOROUGHS:
            item = monthly.get((borough, month), {"n_complaints": 0, "n_rat_sightings": 0, "n_inspections": 0, "n_active": 0})
            borough_months.append({"month": month, "year": int(month[:4]), "borough": borough, "period": month_period(month),
                                   **item, "active_rate": rate(item["n_active"], item["n_inspections"]),
                                   "complaints_per_100k": rate(item["n_complaints"], borough_pop[borough], 1e5, 3),
                                   "population": borough_pop[borough], "median_income": borough_income[borough]})

    # ---- ZIP × year ----
    complaints = complaint_rows("date_extract_y(created_date) as t", "incident_zip, borough", last_month)
    inspections = inspection_rows("date_extract_y(inspection_date) as t", "zip_code, borough", last_month)
    yearly: dict[tuple[str, int], dict] = defaultdict(lambda: {"n_complaints": 0, "n_rat_sightings": 0, "n_inspections": 0, "n_active": 0})
    zip_borough: dict[str, Counter] = defaultdict(Counter)
    for row in complaints:
        code, year = zip5(row.get("incident_zip")), int(float(row.get("t", 0) or 0))
        if code and year >= int(FIRST_MONTH[:4]):
            n = int(row["n"])
            yearly[(code, year)]["n_complaints"] += n
            if row.get("descriptor") == "Rat Sighting":
                yearly[(code, year)]["n_rat_sightings"] += n
            if borough_name(row.get("borough")):
                zip_borough[code][borough_name(row.get("borough"))] += n
    for row in inspections:
        code, year = zip5(row.get("zip_code")), int(float(row.get("t", 0) or 0))
        if code and year >= int(FIRST_MONTH[:4]):
            n = int(row["n"])
            yearly[(code, year)]["n_inspections"] += n
            yearly[(code, year)]["n_active"] += n if is_active(row.get("result")) else 0

    totals = Counter()
    for (code, _year), item in yearly.items():
        totals[code] += item["n_complaints"]
    candidates = sorted(code for code, n in totals.items() if n >= MIN_COMPLAINTS and zip_borough[code])
    log(f"census for {len(candidates)} ZIP code areas")
    acs = census([f"86000US{code}" for code in candidates])
    names = neighborhoods()
    kept = [code for code in candidates if (acs.get(f"86000US{code}", (None, None, ""))[1] or 0) >= MIN_POPULATION
            and acs.get(f"86000US{code}", (None, None, ""))[0]]
    ranked = sorted(kept, key=lambda code: -acs[f"86000US{code}"][0])
    income_rank = {code: index + 1 for index, code in enumerate(ranked)}
    quintile = {code: 5 - (index * 5) // len(ranked) for index, code in enumerate(ranked)}  # 5 = richest fifth
    band_bounds: dict[int, list[float]] = defaultdict(list)
    for code in ranked:
        band_bounds[quintile[code]].append(acs[f"86000US{code}"][0])
    band_label = {q: f"Q{q} {'highest' if q == 5 else 'lowest' if q == 1 else ['', 'lower-middle', 'middle', 'upper-middle'][q - 1]} income"
                  for q in range(1, 6)}
    bands = [{"band": band_label[q], "min_income": min(v), "max_income": max(v), "zips": len(v)} for q, v in sorted(band_bounds.items())]

    def area(code: str) -> dict:
        income, population, _ = acs[f"86000US{code}"]
        return {"zip": code, "borough": zip_borough[code].most_common(1)[0][0], "neighborhood": names.get(code) or f"ZIP {code}",
                "income_band": band_label[quintile[code]], "median_income": income, "population": population}

    last_year = int(last_month[:4])
    zip_years = []
    for code in ranked:
        base = area(code)
        for year in range(int(FIRST_MONTH[:4]), last_year + 1):
            item = yearly.get((code, year), {"n_complaints": 0, "n_rat_sightings": 0, "n_inspections": 0, "n_active": 0})
            zip_years.append({"zip": code, "borough": base["borough"], "neighborhood": base["neighborhood"], "year": year,
                              "period": year_period(year), "income_band": base["income_band"], **item,
                              "active_rate": rate(item["n_active"], item["n_inspections"]),
                              "complaints_per_100k": rate(item["n_complaints"], base["population"], 1e5, 2),
                              "median_income": base["median_income"], "population": base["population"]})

    def window(code: str, years: range) -> dict:
        items = [yearly.get((code, y), {"n_complaints": 0, "n_rat_sightings": 0, "n_inspections": 0, "n_active": 0}) for y in years]
        n_c = sum(i["n_complaints"] for i in items)
        n_i, n_a = sum(i["n_inspections"] for i in items), sum(i["n_active"] for i in items)
        pop = acs[f"86000US{code}"][1]
        return {"complaints_per_year": round(n_c / len(years), 1), "complaints_per_100k": rate(n_c / len(years), pop, 1e5, 2),
                "inspections_per_year": round(n_i / len(years), 1), "active_rate": rate(n_a, n_i)}

    zips = []
    for code in ranked:
        pre, post = window(code, PRE_YEARS), window(code, POST_YEARS)
        zips.append({**area(code), "income_rank": income_rank[code],
                     "complaints_per_year_pre": pre["complaints_per_year"], "complaints_per_year_post": post["complaints_per_year"],
                     "complaints_change_pct": rate(post["complaints_per_year"] - pre["complaints_per_year"], pre["complaints_per_year"], 100, 1),
                     "complaints_per_100k_pre": pre["complaints_per_100k"], "complaints_per_100k_post": post["complaints_per_100k"],
                     "inspections_per_year_pre": pre["inspections_per_year"], "inspections_per_year_post": post["inspections_per_year"],
                     "active_rate_pre": pre["active_rate"], "active_rate_post": post["active_rate"]})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "window": [FIRST_MONTH, last_month],
        "acs_release": release,
        "periods": {"before COVID": f"{FIRST_MONTH} to 2020-02", "COVID": "2020-03 to 2021-12", "after COVID": f"2022-01 to {last_month}"},
        "zip_periods": {"before COVID": f"{FIRST_MONTH[:4]} to 2019", "COVID": "2020 to 2021 (includes January–February 2020)",
                        "after COVID": f"2022 to {last_year}" + (f" ({last_year} partial through {last_month})" if last_month[5:] != "12" else "")},
        "zip_windows": {"pre": f"{PRE_YEARS[0]}–{PRE_YEARS[-1]}", "post": f"{POST_YEARS[0]}–{POST_YEARS[-1]}"},
        "income_bands": bands,
        "sources": ["NYC Open Data 76ig-c548 and erm2-nwe9 (311, Complaint Type Rodent)",
                    "NYC Open Data p937-wjvj (DOHMH rodent inspections, Initial only)",
                    f"{release} via censusreporter.org (B19013, B01003)",
                    "DOHMH MODZCTA neighborhood names" if names else "no neighborhood names"],
        "borough_months": borough_months, "zip_years": zip_years, "zips": zips,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "model" / "out" / "history.json")
    parser.add_argument("--last-month", help="last complete month, YYYY-MM (default: the previous calendar month)")
    args = parser.parse_args()
    today = date.today()
    last_month = args.last_month or date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1).strftime("%Y-%m")
    data = build(last_month)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n")
    log(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB): {len(data['borough_months'])} borough-months, "
        f"{len(data['zip_years'])} zip-years, {len(data['zips'])} zips; window {data['window']}")


if __name__ == "__main__":
    main()
