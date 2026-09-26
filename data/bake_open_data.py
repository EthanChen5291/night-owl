#!/usr/bin/env -S uv run --with duckdb --with h3 --with requests python
"""Bake NYC open data CSVs into Parquet for Barn Owl.

    data/raw/open/*.csv  ->  data/parquet/*.parquet   (DuckDB, one function per table)

No duckdb CLI on the box; the shebang runs it via uv. See data/SCHEMA.md for
columns, join keys and gotchas, data/README.md for the three commands you need.

    ./data/bake_open_data.py --download          # fetch CSVs (Socrata export endpoint)
    ./data/bake_open_data.py                     # bake every table whose CSV exists
    ./data/bake_open_data.py --only pluto,rmz    # subset
    ./data/bake_open_data.py --acs               # ACS 2023 5-yr via api.census.gov (CENSUS_DATA_KEY)
    ./data/bake_open_data.py --p0                # initial_inspections_linked + P0 summary

Idempotent: every run rewrites the parquet it touches. Raw and baked data are gitignored.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOCRATA = "https://data.cityofnewyork.us/api/views/{id}/rows.csv?accessType=DOWNLOAD"
ACS_URL = "https://api.census.gov/data/2023/acs/acs5"
ACS_VARS = ["B19013_001E", "B01003_001E", "B17001_001E", "B17001_002E"]
NYC_COUNTIES = {"005": "Bronx", "047": "Brooklyn", "061": "Manhattan", "081": "Queens", "085": "Staten Island"}

DATE_MIN, DATE_MAX = "2010-01-01", "2026-12-31"      # clip: junk outside
P0_MIN, P0_MAX = "2015-01-01", "2026-08-31"          # backtest window

# raw source registry: name -> (socrata id | None, raw filename, note). None id => not fetched by --download.
SOURCES = {
    "rodent_inspection":   ("p937-wjvj", "rodent_inspection.csv", "DOHMH Rodent Inspection"),
    "complaints_311_2010": ("erm2-nwe9", "311_2010.csv", "311 Service Requests 2010-present (rows < 2020 used)"),
    "complaints_311_2020": (None, "311_2020.csv", "311 Service Requests 2020-onward split: verify id"),
    "pluto":               ("64uk-42ks", "pluto.csv", "PLUTO"),
    "restaurant_inspection": ("43nn-pn8j", "restaurant_inspection.csv", "DOHMH Restaurant Inspection Results"),
    "dob_permits":         ("ipu4-2q9a", "dob_permits.csv", "DOB Permit Issuance"),
    "litter_baskets":      (None, "litter_baskets.csv", "DSNY Litter Basket Inventory: verify id"),
    "catch_basins":        (None, "catch_basins.csv", "DEP catch basins: verify id"),
    "parks_properties":    (None, "parks_properties.csv", "Parks Properties: verify id"),
    "street_trees":        ("uvpi-gqnh", "street_trees_2015.csv", "2015 Street Tree Census"),
    "census_tracts":       (None, "census_tracts.csv", "2020 Census Tracts polygons: verify id"),
    "community_districts": (None, "community_districts.csv", "Community Districts polygons: verify id"),
    "rmz":                 (None, "rmz.csv", "Rat Mitigation Zones (4) as WKT csv or rmz.geojson: verify id"),
    "noaa_central_park":   (None, "noaa_central_park.csv", "NOAA NCEI GSOM, USW00094728: not Socrata, download by hand"),
    "cdbg_lomod":          (None, "cdbg_lomod.csv", "HUD LMISD tract lomod_pct: not Socrata, download by hand"),
    "acs_tract":           (None, "acs_2023_5yr.csv", "ACS 2023 5-yr: fetched by --acs, cached here"),
}


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr)


def load_dotenv() -> None:
    for p in (REPO / ".env", Path.cwd() / ".env", Path.home() / "divMap" / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            return


# ---------------------------------------------------------------- csv column picking
def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


class Src:
    """One raw CSV read all-varchar. c(*candidates) -> quoted column or NULL if absent."""

    def __init__(self, con, path: Path):
        self.path = path
        self.rel = f"read_csv('{path}', all_varchar=true, header=true, ignore_errors=true)"
        cols = [d[0] for d in con.execute(f"SELECT * FROM {self.rel} LIMIT 0").description]
        self.cols = {_norm(c): c for c in cols}
        self.missing: list[str] = []

    def c(self, *cands: str) -> str:
        for cand in cands:
            hit = self.cols.get(_norm(cand))
            if hit is not None:
                return '"' + hit.replace('"', '""') + '"'
        self.missing.append(cands[0])
        return "NULL::VARCHAR"

    def has(self, *cands: str) -> bool:
        return any(_norm(c) in self.cols for c in cands)


def src(con, raw: Path, name: str) -> Src | None:
    fn = SOURCES[name][1]
    p = raw / fn
    if not p.exists():
        warn(f"{name}: {p} missing, skipped ({SOURCES[name][2]})")
        return None
    s = Src(con, p)
    return s


# ---------------------------------------------------------------- sql macros
MACROS = r"""
CREATE OR REPLACE MACRO parse_ts(x) AS try_strptime(x, [
    '%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M', '%m/%d/%Y',
    '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m']);
CREATE OR REPLACE MACRO month_of(d) AS date_trunc('month', d::DATE)::DATE;
CREATE OR REPLACE MACRO boro_digit(b) AS CASE upper(trim(coalesce(b, '')))
    WHEN 'MANHATTAN' THEN '1' WHEN 'NEW YORK' THEN '1' WHEN 'MN' THEN '1' WHEN '1' THEN '1'
    WHEN 'BRONX' THEN '2' WHEN 'BX' THEN '2' WHEN '2' THEN '2'
    WHEN 'BROOKLYN' THEN '3' WHEN 'KINGS' THEN '3' WHEN 'BK' THEN '3' WHEN '3' THEN '3'
    WHEN 'QUEENS' THEN '4' WHEN 'QN' THEN '4' WHEN '4' THEN '4'
    WHEN 'STATEN ISLAND' THEN '5' WHEN 'RICHMOND' THEN '5' WHEN 'SI' THEN '5' WHEN '5' THEN '5'
    ELSE NULL END;
-- community board -> 3-digit GEOCODE (boro digit + 2-digit CB). 311 writes '01 MANHATTAN' / 'Unspecified BRONX';
-- inspections and PLUTO write '101' or '101.0'; DOB writes '101'. Unspecified / JIA leftovers -> NULL.
CREATE OR REPLACE MACRO cd_geocode(raw, boro) AS CASE
    WHEN raw IS NULL THEN NULL
    WHEN regexp_matches(trim(raw), '^[1-5][0-9]{2}(\.0+)?$') THEN substr(trim(raw), 1, 3)
    WHEN regexp_matches(trim(raw), '^[0-9]{1,2} +[A-Za-z ]+$')
        THEN boro_digit(regexp_extract(trim(raw), '^[0-9]{1,2} +(.*)$', 1))
             || lpad(regexp_extract(trim(raw), '^([0-9]{1,2})', 1), 2, '0')
    WHEN regexp_matches(trim(raw), '^[0-9]{1,2}$') AND boro_digit(boro) IS NOT NULL
        THEN boro_digit(boro) || lpad(trim(raw), 2, '0')
    ELSE NULL END;
CREATE OR REPLACE MACRO bbl_norm(x) AS CASE
    WHEN regexp_matches(trim(coalesce(x, '')), '^[1-5][0-9]{9}(\.0+)?$')
    THEN try_cast(substr(trim(x), 1, 10) AS BIGINT) END;
CREATE OR REPLACE MACRO bbl_make(boro, block, lot) AS CASE
    WHEN boro_digit(boro) IS NOT NULL AND try_cast(block AS INT) > 0 AND try_cast(lot AS INT) > 0
    THEN try_cast(boro_digit(boro) || lpad(try_cast(block AS INT)::VARCHAR, 5, '0')
                  || lpad(try_cast(lot AS INT)::VARCHAR, 4, '0') AS BIGINT) END;
CREATE OR REPLACE MACRO wkt_lon(g) AS try_cast(regexp_extract(g, 'POINT *\(\s*(-?[0-9.]+)\s+(-?[0-9.]+)', 1) AS DOUBLE);
CREATE OR REPLACE MACRO wkt_lat(g) AS try_cast(regexp_extract(g, 'POINT *\(\s*(-?[0-9.]+)\s+(-?[0-9.]+)', 2) AS DOUBLE);
CREATE OR REPLACE MACRO nyc_lat(x) AS CASE WHEN x BETWEEN 40.45 AND 40.95 THEN x END;
CREATE OR REPLACE MACRO nyc_lon(x) AS CASE WHEN x BETWEEN -74.30 AND -73.65 THEN x END;
CREATE OR REPLACE MACRO zip5(z) AS CASE WHEN regexp_matches(trim(coalesce(z, '')), '^[0-9]{5}') THEN substr(trim(z), 1, 5) END;
"""


def setup_h3(con) -> str:
    """Return the SQL expression template for H3 r9 from (lat, lon). Degrades to NULL."""
    try:
        con.execute("INSTALL h3 FROM community; LOAD h3;")
        con.execute("SELECT h3_latlng_to_cell_string(40.7, -73.9, 9)").fetchone()
        print("  h3: duckdb community extension")
        return "CASE WHEN {lat} IS NOT NULL AND {lon} IS NOT NULL THEN h3_latlng_to_cell_string({lat}, {lon}, 9) END"
    except Exception:
        pass
    try:
        import h3

        def h3_r9(lat: float, lon: float) -> str:
            return h3.latlng_to_cell(lat, lon, 9)

        # string type names: duckdb >= 1.4 dropped duckdb.typing; NULL in -> NULL out by default
        con.create_function("h3_r9_py", h3_r9, ["DOUBLE", "DOUBLE"], "VARCHAR")
        print("  h3: python UDF (h3.latlng_to_cell)")
        return "CASE WHEN {lat} IS NOT NULL AND {lon} IS NOT NULL THEN h3_r9_py({lat}, {lon}) END"
    except Exception as e:
        warn(f"h3 unavailable ({e}); h3_r9 will be NULL")
        return "NULL::VARCHAR"


def setup_spatial(con) -> bool:
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        return True
    except Exception as e:
        warn(f"spatial extension unavailable ({e}); polygon tables keep WKT only, P0 zone = NULL")
        return False


class Ctx:
    def __init__(self, con, raw: Path, out: Path):
        self.con, self.raw, self.out = con, raw, out
        self.h3 = setup_h3(con)
        self.spatial: bool | None = None

    def h3_expr(self, lat="latitude", lon="longitude") -> str:
        return self.h3.format(lat=lat, lon=lon)

    def latlon(self, s: Src) -> tuple[str, str]:
        """lat/lon expressions for a point table: explicit columns, else WKT POINT in the_geom."""
        lat = s.c("latitude", "lat", "y", "point_y")
        lon = s.c("longitude", "lon", "lng", "long", "x", "point_x")
        geom = s.c("the_geom", "geom", "geometry", "point", "location")
        return (f"nyc_lat(coalesce(try_cast({lat} AS DOUBLE), wkt_lat({geom})))",
                f"nyc_lon(coalesce(try_cast({lon} AS DOUBLE), wkt_lon({geom})))")

    def write(self, name: str, sql: str) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        dst = self.out / f"{name}.parquet"
        self.con.execute(f"COPY ({sql}) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        n = self.con.execute(f"SELECT count(*) FROM read_parquet('{dst}')").fetchone()[0]
        print(f"  {name:32s} {n:>12,} rows  -> {dst.relative_to(REPO) if dst.is_relative_to(REPO) else dst}")
        return n

    def parquet(self, name: str) -> str:
        p = self.out / f"{name}.parquet"
        if not p.exists():
            raise SystemExit(f"{p} missing: bake '{name}' first")
        return f"read_parquet('{p}')"


# ---------------------------------------------------------------- tables (one function each)
def t_rodent_inspection(ctx: Ctx) -> int | None:
    s = src(ctx.con, ctx.raw, "rodent_inspection")
    if s is None:
        return None
    lat, lon = ctx.latlon(s)
    sql = f"""
    WITH r AS (
      SELECT {s.c('job_ticket_or_work_order_id', 'inspection_id', 'ticket_id')} AS inspection_id,
             {s.c('job_id')} AS job_id,
             try_cast({s.c('job_progress')} AS INTEGER) AS job_progress,
             trim({s.c('inspection_type')}) AS inspection_type,
             parse_ts({s.c('inspection_date')}) AS inspection_ts,
             parse_ts({s.c('approved_date')}) AS approved_ts,
             trim({s.c('result')}) AS result,
             bbl_norm({s.c('bbl')}) AS bbl,
             {s.c('bin')} AS bin,
             upper(trim({s.c('borough', 'boro')})) AS borough,
             zip5({s.c('zip_code', 'zipcode', 'zip')}) AS zip,
             {s.c('community board', 'community_board', 'cd')} AS cb_raw,
             {s.c('census tract', 'census_tract')} AS census_tract_raw,
             {s.c('nta')} AS nta,
             {lat} AS latitude, {lon} AS longitude
      FROM {s.rel})
    SELECT coalesce(inspection_id, job_id || '/' || job_progress) AS inspection_id, job_id, job_progress,
           inspection_type, inspection_ts::DATE AS inspection_date, month_of(inspection_ts) AS month,
           result, upper(result) LIKE 'RAT ACTIVITY%' AS active,
           inspection_type = 'Initial' AS is_initial,
           bbl, bin, borough, zip, cd_geocode(cb_raw, borough) AS cd, census_tract_raw, nta,
           latitude, longitude, {ctx.h3_expr()} AS h3_r9, approved_ts::DATE AS approved_date
    FROM r
    WHERE inspection_ts::DATE BETWEEN '{DATE_MIN}' AND '{DATE_MAX}'
    """
    n = ctx.write("rodent_inspection", sql)
    k = ctx.con.execute(f"SELECT count(*) FROM {ctx.parquet('rodent_inspection')} WHERE is_initial").fetchone()[0]
    print(f"  {'':32s} {k:>12,} of them Initial")
    return n


def _sel_311(s: Src, ctx: Ctx, tag: str) -> str:
    lat, lon = ctx.latlon(s)
    return f"""
      SELECT {s.c('unique key', 'unique_key')} AS unique_key,
             parse_ts({s.c('created date', 'created_date')}) AS created_ts,
             parse_ts({s.c('closed date', 'closed_date')}) AS closed_ts,
             trim({s.c('agency')}) AS agency,
             trim({s.c('complaint type', 'complaint_type')}) AS complaint_type,
             trim({s.c('descriptor')}) AS descriptor,
             trim({s.c('location type', 'location_type')}) AS location_type,
             zip5({s.c('incident zip', 'incident_zip')}) AS zip,
             {s.c('incident address', 'incident_address')} AS incident_address,
             upper(trim({s.c('borough')})) AS borough,
             {s.c('community board', 'community_board')} AS cb_raw,
             bbl_norm({s.c('bbl')}) AS bbl,
             {lat} AS latitude, {lon} AS longitude,
             '{tag}' AS source
      FROM {s.rel}"""


def t_complaints_rodent(ctx: Ctx) -> int | None:
    """311 rodent complaints. Two datasets stitched at 2020-01-01 (< 2020 from 2010-present, >= 2020 from the split)."""
    a = src(ctx.con, ctx.raw, "complaints_311_2010")
    b = src(ctx.con, ctx.raw, "complaints_311_2020")
    if a is None and b is None:
        return None
    parts = []
    if a is not None:
        cut = "created_ts < '2020-01-01'" if b is not None else "TRUE"
        if b is None:
            warn("311_2020.csv missing: using 2010-present for all years")
        parts.append(f"SELECT * FROM ({_sel_311(a, ctx, '2010')}) WHERE {cut}")
    if b is not None:
        parts.append(f"SELECT * FROM ({_sel_311(b, ctx, '2020')}) WHERE created_ts >= '2020-01-01'")
    union = " UNION ALL ".join(parts)
    sql = f"""
    WITH u AS ({union})
    SELECT unique_key, created_ts AS created_date, month_of(created_ts) AS month, closed_ts AS closed_date,
           agency, complaint_type, descriptor, location_type, zip, incident_address, borough,
           cd_geocode(cb_raw, borough) AS cd, bbl, latitude, longitude, {ctx.h3_expr()} AS h3_r9, source
    FROM u
    WHERE upper(complaint_type) = 'RODENT'
      AND created_ts::DATE BETWEEN '{DATE_MIN}' AND '{DATE_MAX}'
    """
    n = ctx.write("complaints_rodent", sql)
    q = ctx.con.execute(f"""SELECT round(100.0 * count(*) FILTER (WHERE bbl IS NULL) / count(*), 1)
                            FROM {ctx.parquet('complaints_rodent')} WHERE created_date < '2020-01-01'""").fetchone()[0]
    print(f"  {'':32s} pre-2020 rows without BBL: {q}% (README: ~23%)")
    return n


def t_complaints_cb_month(ctx: Ctx) -> int | None:
    """All-complaint CB-month denominator, 2020-> only (from the 2020 split)."""
    b = src(ctx.con, ctx.raw, "complaints_311_2020")
    if b is None:
        return None
    sql = f"""
    WITH u AS ({_sel_311(b, ctx, '2020')})
    SELECT cd_geocode(cb_raw, borough) AS cd, month_of(created_ts) AS month,
           count(*) AS n_all, count(*) FILTER (WHERE upper(complaint_type) = 'RODENT') AS n_rodent
    FROM u WHERE created_ts >= '2020-01-01' AND created_ts::DATE <= '{DATE_MAX}'
    GROUP BY 1, 2 ORDER BY 1, 2"""
    return ctx.write("complaints_cb_month", sql)


def t_complaints_zip_month(ctx: Ctx) -> int | None:
    b = src(ctx.con, ctx.raw, "complaints_311_2020")
    if b is None:
        return None
    sql = f"""
    WITH u AS ({_sel_311(b, ctx, '2020')})
    SELECT zip, month_of(created_ts) AS month,
           count(*) AS n_all, count(*) FILTER (WHERE upper(complaint_type) = 'RODENT') AS n_rodent
    FROM u WHERE created_ts >= '2020-01-01' AND created_ts::DATE <= '{DATE_MAX}'
    GROUP BY 1, 2 ORDER BY 1, 2"""
    return ctx.write("complaints_zip_month", sql)


def t_pluto(ctx: Ctx) -> int | None:
    s = src(ctx.con, ctx.raw, "pluto")
    if s is None:
        return None
    lat, lon = ctx.latlon(s)
    num = lambda *c: f"try_cast({s.c(*c)} AS DOUBLE)"  # noqa: E731
    sql = f"""
    WITH p AS (
      SELECT bbl_norm({s.c('bbl')}) AS bbl_raw, {s.c('borough')} AS borough_raw,
             {s.c('block')} AS block, {s.c('lot')} AS lot,
             {s.c('cd')} AS cb_raw, {s.c('bct2020')} AS bct2020, {s.c('ct2010')} AS ct2010,
             zip5({s.c('zipcode')}) AS zip, {s.c('address')} AS address,
             {s.c('bldgclass')} AS bldgclass, {s.c('landuse')} AS landuse, {s.c('ownertype')} AS ownertype,
             {num('lotarea')} AS lotarea, {num('bldgarea')} AS bldgarea, {num('comarea')} AS comarea,
             {num('resarea')} AS resarea, {num('numbldgs')} AS numbldgs, {num('numfloors')} AS numfloors,
             {num('unitsres')} AS unitsres, {num('unitstotal')} AS unitstotal,
             try_cast({s.c('yearbuilt')} AS INTEGER) AS yearbuilt, try_cast({s.c('yearalter1')} AS INTEGER) AS yearalter1,
             {num('assesstot')} AS assesstot, {num('builtfar')} AS builtfar,
             {lat} AS latitude, {lon} AS longitude
      FROM {s.rel})
    SELECT coalesce(bbl_raw, bbl_make(borough_raw, block, lot)) AS bbl, upper(borough_raw) AS borough,
           try_cast(block AS INTEGER) AS block, try_cast(lot AS INTEGER) AS lot,
           cd_geocode(cb_raw, borough_raw) AS cd, bct2020, ct2010, zip, address, bldgclass, landuse, ownertype,
           lotarea, bldgarea, comarea, resarea, numbldgs, numfloors, unitsres, unitstotal,
           CASE WHEN yearbuilt > 0 THEN yearbuilt END AS yearbuilt, CASE WHEN yearalter1 > 0 THEN yearalter1 END AS yearalter1,
           assesstot, builtfar, latitude, longitude, {ctx.h3_expr()} AS h3_r9
    FROM p WHERE coalesce(bbl_raw, bbl_make(borough_raw, block, lot)) IS NOT NULL
    """
    return ctx.write("pluto", sql)


def t_restaurant_inspection(ctx: Ctx) -> int | None:
    """Row = one violation line. vermin = code in 04K (rats), 04L (mice), 08A (not vermin proof)."""
    s = src(ctx.con, ctx.raw, "restaurant_inspection")
    if s is None:
        return None
    lat, lon = ctx.latlon(s)
    sql = f"""
    WITH r AS (
      SELECT {s.c('camis')} AS camis, {s.c('dba')} AS dba, upper(trim({s.c('boro')})) AS borough,
             zip5({s.c('zipcode')}) AS zip, {s.c('cuisine description', 'cuisine_description')} AS cuisine,
             parse_ts({s.c('inspection date', 'inspection_date')}) AS inspection_ts,
             {s.c('action')} AS action, trim({s.c('violation code', 'violation_code')}) AS violation_code,
             {s.c('violation description', 'violation_description')} AS violation_description,
             {s.c('critical flag', 'critical_flag')} AS critical_flag,
             try_cast({s.c('score')} AS INTEGER) AS score, {s.c('grade')} AS grade,
             {s.c('inspection type', 'inspection_type')} AS inspection_type,
             bbl_norm({s.c('bbl')}) AS bbl, {s.c('bin')} AS bin,
             {s.c('community board', 'community_board')} AS cb_raw,
             {lat} AS latitude, {lon} AS longitude
      FROM {s.rel})
    SELECT camis, dba, borough, zip, cuisine, inspection_ts::DATE AS inspection_date, month_of(inspection_ts) AS month,
           action, violation_code, violation_description, critical_flag, score, grade, inspection_type,
           violation_code IN ('04K', '04L', '08A') AS vermin, violation_code = '04K' AS rats,
           bbl, bin, cd_geocode(cb_raw, borough) AS cd, latitude, longitude, {ctx.h3_expr()} AS h3_r9
    FROM r WHERE inspection_ts::DATE BETWEEN '{DATE_MIN}' AND '{DATE_MAX}'   -- drops the 1900-01-01 'not yet inspected' rows
    """
    return ctx.write("restaurant_inspection", sql)


def t_dob_permits(ctx: Ctx) -> int | None:
    """DOB permit issuance, NB (new building) and DM (demolition) only."""
    s = src(ctx.con, ctx.raw, "dob_permits")
    if s is None:
        return None
    lat, lon = ctx.latlon(s)
    sql = f"""
    WITH d AS (
      SELECT {s.c('job #', 'job_')} AS job_number, {s.c('job doc. #', 'job_doc__')} AS job_doc_number,
             trim({s.c('job type', 'job_type')}) AS job_type, trim({s.c('work type', 'work_type')}) AS work_type,
             trim({s.c('permit type', 'permit_type')}) AS permit_type, {s.c('permit status', 'permit_status')} AS permit_status,
             parse_ts({s.c('filing date', 'filing_date')}) AS filing_ts,
             parse_ts({s.c('issuance date', 'issuance_date')}) AS issuance_ts,
             parse_ts({s.c('expiration date', 'expiration_date')}) AS expiration_ts,
             parse_ts({s.c('job start date', 'job_start_date')}) AS job_start_ts,
             {s.c('bin #', 'bin_')} AS bin, upper(trim({s.c('borough')})) AS borough,
             {s.c('block')} AS block, {s.c('lot')} AS lot,
             {s.c('community board', 'community_board')} AS cb_raw, zip5({s.c('zip code', 'zip_code')}) AS zip,
             {lat} AS latitude, {lon} AS longitude
      FROM {s.rel})
    SELECT job_number, job_doc_number, job_type, work_type, permit_type, permit_status,
           filing_ts::DATE AS filing_date, issuance_ts::DATE AS issuance_date, month_of(issuance_ts) AS month,
           expiration_ts::DATE AS expiration_date, job_start_ts::DATE AS job_start_date,
           bin, borough, try_cast(block AS INTEGER) AS block, try_cast(lot AS INTEGER) AS lot,
           bbl_make(borough, block, lot) AS bbl, cd_geocode(cb_raw, borough) AS cd, zip,
           latitude, longitude, {ctx.h3_expr()} AS h3_r9
    FROM d WHERE job_type IN ('NB', 'DM') AND issuance_ts::DATE BETWEEN '{DATE_MIN}' AND '{DATE_MAX}'
    """
    return ctx.write("dob_permits", sql)


def _point_table(ctx: Ctx, name: str, id_cands: tuple[str, ...], extra: dict[str, tuple[str, ...]] = {}) -> int | None:
    s = src(ctx.con, ctx.raw, name)
    if s is None:
        return None
    lat, lon = ctx.latlon(s)
    extra_sql = "".join(f", {s.c(*c)} AS {k}" for k, c in extra.items())
    sql = f"""
    WITH p AS (
      SELECT {s.c(*id_cands)} AS id, upper(trim({s.c('borough', 'boro', 'boroname')})) AS borough,
             {s.c('community board', 'community_board', 'cb', 'communityboard', 'boro_cd', 'cd')} AS cb_raw
             {extra_sql}, {lat} AS latitude, {lon} AS longitude
      FROM {s.rel})
    SELECT * EXCLUDE (cb_raw), cd_geocode(cb_raw, borough) AS cd, {ctx.h3_expr()} AS h3_r9
    FROM p WHERE latitude IS NOT NULL
    """
    return ctx.write(name, sql)


def t_litter_baskets(ctx: Ctx) -> int | None:
    return _point_table(ctx, "litter_baskets", ("basketid", "basket_id", "objectid", "id"),
                        {"basket_type": ("baskettype", "basket_type", "type"), "location": ("location", "address")})


def t_catch_basins(ctx: Ctx) -> int | None:
    return _point_table(ctx, "catch_basins", ("unitid", "unit_id", "objectid", "id"),
                        {"basin_type": ("cb_type", "type", "structure_type")})


def t_street_trees(ctx: Ctx) -> int | None:
    """2015 Street Tree Census: every tree pit. 'guards' is the tree-guard field the node hangs from."""
    s = src(ctx.con, ctx.raw, "street_trees")
    if s is None:
        return None
    lat, lon = ctx.latlon(s)
    sql = f"""
    WITH t AS (
      SELECT {s.c('tree_id')} AS tree_id, {s.c('block_id')} AS block_id, {s.c('status')} AS status,
             {s.c('health')} AS health, {s.c('spc_common')} AS spc_common,
             try_cast({s.c('tree_dbh')} AS INTEGER) AS tree_dbh, {s.c('curb_loc')} AS curb_loc,
             {s.c('guards')} AS guards, {s.c('sidewalk')} AS sidewalk, {s.c('problems')} AS problems,
             zip5({s.c('zipcode', 'postcode')}) AS zip, upper(trim({s.c('boroname', 'borough')})) AS borough,
             {s.c('cb_num', 'community board', 'community_board')} AS cb_raw,
             bbl_norm({s.c('bbl')}) AS bbl, {s.c('bin')} AS bin, {s.c('nta')} AS nta,
             {s.c('boro_ct')} AS boro_ct, {lat} AS latitude, {lon} AS longitude
      FROM {s.rel})
    SELECT * EXCLUDE (cb_raw), cd_geocode(cb_raw, borough) AS cd, {ctx.h3_expr()} AS h3_r9
    FROM t WHERE latitude IS NOT NULL
    """
    return ctx.write("street_trees", sql)


def _polygon_table(ctx: Ctx, name: str, select_cols: str, s: Src) -> int | None:
    geom = s.c("the_geom", "geom", "geometry", "multipolygon", "polygon")
    if ctx.spatial is None:
        ctx.spatial = setup_spatial(ctx.con)
    cen = ("ST_Y(ST_Centroid(ST_GeomFromText(geom_wkt))) AS centroid_lat, "
           "ST_X(ST_Centroid(ST_GeomFromText(geom_wkt))) AS centroid_lon") if ctx.spatial else \
          "NULL::DOUBLE AS centroid_lat, NULL::DOUBLE AS centroid_lon"
    sql = f"""
    WITH g AS (SELECT {select_cols}, {geom} AS geom_wkt FROM {s.rel})
    SELECT *, {cen} FROM g WHERE geom_wkt IS NOT NULL
    """
    return ctx.write(name, sql)


def t_parks_properties(ctx: Ctx) -> int | None:
    s = src(ctx.con, ctx.raw, "parks_properties")
    if s is None:
        return None
    cols = (f"{s.c('gispropnum', 'gis_prop_num', 'objectid')} AS park_id, {s.c('signname', 'name311', 'name')} AS name, "
            f"upper(trim({s.c('borough')})) AS borough, {s.c('typecategory', 'type_category')} AS type_category, "
            f"try_cast({s.c('acres')} AS DOUBLE) AS acres, {s.c('communityb', 'community_board', 'cb')} AS cd_raw, "
            f"zip5({s.c('zipcode', 'zip')}) AS zip")
    return _polygon_table(ctx, "parks_properties", cols, s)


def t_census_tracts(ctx: Ctx) -> int | None:
    """2020 tract polygons. geoid = 11-char state+county+tract, the ACS/CDBG join key."""
    s = src(ctx.con, ctx.raw, "census_tracts")
    if s is None:
        return None
    county = "CASE upper(trim(boroname)) WHEN 'MANHATTAN' THEN '061' WHEN 'BRONX' THEN '005' WHEN 'BROOKLYN' THEN '047' " \
             "WHEN 'QUEENS' THEN '081' WHEN 'STATEN ISLAND' THEN '085' END"
    cols = (f"{s.c('boroname', 'borough')} AS boroname, {s.c('ct2020', 'ct2010', 'ctlabel')} AS ct2020, "
            f"{s.c('boroct2020', 'boroct2010')} AS boro_ct2020, {s.c('ntaname')} AS nta_name, {s.c('nta2020', 'ntacode')} AS nta, "
            f"{s.c('cdta2020')} AS cdta2020, "
            f"coalesce({s.c('geoid')}, '36' || ({county}) || lpad(regexp_replace({s.c('ct2020', 'ct2010')}, '[^0-9]', '', 'g'), 6, '0')) AS geoid")
    return _polygon_table(ctx, "census_tracts", cols, s)


def t_community_districts(ctx: Ctx) -> int | None:
    """59 community districts (+ JIAs and parks CDs in the raw file). cd = 3-digit GEOCODE."""
    s = src(ctx.con, ctx.raw, "community_districts")
    if s is None:
        return None
    cols = (f"substr(trim({s.c('borocd', 'boro_cd', 'cd')}), 1, 3) AS cd, "
            f"boro_digit(substr(trim({s.c('borocd', 'boro_cd', 'cd')}), 1, 1)) AS boro_digit, "
            f"try_cast({s.c('shape_area', 'shape__area')} AS DOUBLE) AS shape_area")
    return _polygon_table(ctx, "community_districts", cols, s)


def t_rmz(ctx: Ctx) -> int | None:
    """Rat Mitigation Zones, 4 polygons. Accepts rmz.geojson (needs spatial) or rmz.csv with a WKT column."""
    gj = ctx.raw / "rmz.geojson"
    if gj.exists():
        if ctx.spatial is None:
            ctx.spatial = setup_spatial(ctx.con)
        if not ctx.spatial:
            warn("rmz.geojson needs the spatial extension; provide rmz.csv with WKT instead")
            return None
        sql = f"""SELECT coalesce(zone, name, zone_name, rmz) AS zone, ST_AsText(geom) AS geom_wkt,
                         ST_Y(ST_Centroid(geom)) AS centroid_lat, ST_X(ST_Centroid(geom)) AS centroid_lon
                  FROM (SELECT * FROM ST_Read('{gj}'))"""
        return ctx.write("rmz", sql)
    s = src(ctx.con, ctx.raw, "rmz")
    if s is None:
        return None
    cols = f"coalesce({s.c('zone', 'name', 'zone_name', 'rmz')}, 'zone ' || row_number() OVER ()) AS zone"
    n = _polygon_table(ctx, "rmz", cols, s)
    if n is not None and n != 4:
        warn(f"rmz: expected 4 zones, got {n}")
    return n


def t_noaa_central_park(ctx: Ctx) -> int | None:
    """NOAA NCEI GSOM monthly for Central Park (USW00094728). month = first of month."""
    s = src(ctx.con, ctx.raw, "noaa_central_park")
    if s is None:
        return None
    sql = f"""
    WITH n AS (SELECT {s.c('date', 'month')} AS d, {s.c('station')} AS station,
                      try_cast({s.c('tavg')} AS DOUBLE) AS tavg, try_cast({s.c('tmax')} AS DOUBLE) AS tmax,
                      try_cast({s.c('tmin')} AS DOUBLE) AS tmin, try_cast({s.c('prcp')} AS DOUBLE) AS prcp,
                      try_cast({s.c('snow')} AS DOUBLE) AS snow
               FROM {s.rel})
    SELECT month_of(parse_ts(CASE WHEN length(d) = 7 THEN d || '-01' ELSE d END)) AS month, station, tavg, tmax, tmin, prcp, snow
    FROM n WHERE month IS NOT NULL AND month BETWEEN '{DATE_MIN}' AND '{DATE_MAX}' ORDER BY month
    """
    return ctx.write("noaa_central_park", sql)


def t_cdbg_lomod(ctx: Ctx) -> int | None:
    """HUD LMISD by tract: fallback income proxy for the 135 tracts where ACS is null."""
    s = src(ctx.con, ctx.raw, "cdbg_lomod")
    if s is None:
        return None
    sql = f"""
    SELECT regexp_replace({s.c('geoid', 'tract_geoid', 'geoid10', 'geoid20')}, '[^0-9]', '', 'g') AS geoid,
           try_cast({s.c('lowmodpct', 'lomod_pct', 'low_mod_pct')} AS DOUBLE) AS lomod_pct,
           try_cast({s.c('lowmod', 'low_mod')} AS DOUBLE) AS lowmod,
           try_cast({s.c('lowmoduniv', 'low_mod_univ')} AS DOUBLE) AS lowmod_univ
    FROM {s.rel} WHERE geoid LIKE '36%' AND length(geoid) = 11
    """
    return ctx.write("cdbg_lomod", sql)


def t_acs_tract(ctx: Ctx) -> int | None:
    """ACS 2023 5-yr from the cached CSV (--acs writes it). Use --acs to fetch."""
    p = ctx.raw / SOURCES["acs_tract"][1]
    if not p.exists():
        warn(f"acs_tract: {p} missing; run --acs (needs CENSUS_DATA_KEY)")
        return None
    return _bake_acs_csv(ctx, p)


def _bake_acs_csv(ctx: Ctx, p: Path) -> int:
    sql = f"""
    WITH a AS (SELECT * FROM read_csv('{p}', all_varchar=true, header=true))
    SELECT state || county || tract AS geoid, "NAME" AS name, county,
           CASE WHEN try_cast(B19013_001E AS DOUBLE) >= 0 THEN try_cast(B19013_001E AS DOUBLE) END AS median_income,
           CASE WHEN try_cast(B01003_001E AS DOUBLE) >= 0 THEN try_cast(B01003_001E AS DOUBLE) END AS population,
           CASE WHEN try_cast(B17001_001E AS DOUBLE) >= 0 THEN try_cast(B17001_001E AS DOUBLE) END AS poverty_universe,
           CASE WHEN try_cast(B17001_002E AS DOUBLE) >= 0 THEN try_cast(B17001_002E AS DOUBLE) END AS poverty_pop,
           CASE WHEN try_cast(B17001_001E AS DOUBLE) > 0 AND try_cast(B17001_002E AS DOUBLE) >= 0
                THEN try_cast(B17001_002E AS DOUBLE) / try_cast(B17001_001E AS DOUBLE) END AS poverty_pct
    FROM a
    """
    n = ctx.write("acs_tract", sql)
    k = ctx.con.execute(f"SELECT count(*) FROM {ctx.parquet('acs_tract')} WHERE median_income IS NULL").fetchone()[0]
    print(f"  {'':32s} {k:,} tracts with null median income (README: 135; fall back to cdbg_lomod.lomod_pct)")
    return n


TABLES = {
    "rodent_inspection": t_rodent_inspection,
    "complaints_rodent": t_complaints_rodent,
    "complaints_cb_month": t_complaints_cb_month,
    "complaints_zip_month": t_complaints_zip_month,
    "pluto": t_pluto,
    "restaurant_inspection": t_restaurant_inspection,
    "dob_permits": t_dob_permits,
    "litter_baskets": t_litter_baskets,
    "catch_basins": t_catch_basins,
    "parks_properties": t_parks_properties,
    "street_trees": t_street_trees,
    "census_tracts": t_census_tracts,
    "community_districts": t_community_districts,
    "rmz": t_rmz,
    "noaa_central_park": t_noaa_central_park,
    "cdbg_lomod": t_cdbg_lomod,
    "acs_tract": t_acs_tract,
}


# ---------------------------------------------------------------- P0
def build_p0(ctx: Ctx) -> None:
    """initial_inspections_linked: every Initial inspection 2015-01 -> 2026-08, l60/l180 = rodent complaint on
    the same BBL in the prior 60/180 days (0/1), zone = RMZ name or NULL. Prints the P0 summary."""
    con = ctx.con
    ri, cr = ctx.parquet("rodent_inspection"), ctx.parquet("complaints_rodent")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE p0 AS
    WITH i AS (SELECT * FROM {ri} WHERE is_initial AND inspection_date BETWEEN '{P0_MIN}' AND '{P0_MAX}'),
         c AS (SELECT bbl, created_date::DATE AS d FROM {cr} WHERE bbl IS NOT NULL)
    SELECT i.inspection_id, i.bbl, i.inspection_date, i.month, i.result, i.active,
           NULL::VARCHAR AS zone,
           coalesce(bool_or(c.d >= i.inspection_date - INTERVAL 60 DAY), false)::INTEGER AS l60,
           coalesce(bool_or(c.d >= i.inspection_date - INTERVAL 180 DAY), false)::INTEGER AS l180,
           i.h3_r9, i.cd, i.latitude, i.longitude
    FROM i LEFT JOIN c ON c.bbl = i.bbl AND c.d < i.inspection_date AND c.d >= i.inspection_date - INTERVAL 180 DAY
    GROUP BY ALL
    """)
    rmz = ctx.out / "rmz.parquet"
    if ctx.spatial is None:
        ctx.spatial = setup_spatial(con)
    if rmz.exists() and ctx.spatial:
        con.execute(f"""
        UPDATE p0 SET zone = z.zone
        FROM (SELECT zone, ST_GeomFromText(geom_wkt) AS g FROM read_parquet('{rmz}')) z
        WHERE p0.latitude IS NOT NULL AND ST_Within(ST_Point(p0.longitude, p0.latitude), z.g)
        """)
    else:
        warn("zone left NULL (no rmz.parquet or no spatial extension)")
    ctx.write("initial_inspections_linked",
              "SELECT inspection_id, bbl, inspection_date, month, result, active, zone, l60, l180, h3_r9, cd FROM p0")

    print("\nP0: share of Initial inspections with no rodent complaint on the BBL in the prior 60 / 180 days")
    print(f"  {'year':>4} {'initial':>9} {'no_l60':>7} {'no_l180':>8} {'in_rmz':>7}")
    for y, n, s60, s180, z in con.execute("""
        SELECT year(inspection_date), count(*),
               100.0 * avg(1 - l60), 100.0 * avg(1 - l180), 100.0 * avg((zone IS NOT NULL)::INT)
        FROM p0 GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"  {y:>4} {n:>9,} {s60:>6.1f}% {s180:>7.1f}% {z:>6.1f}%")
    print("  README: 75-91% with no prior complaint, ~130k/yr, about half inside RMZs")
    print("\nP0: active-rate (result = Rat Activity) by prior-complaint flag")
    for k, n, a in con.execute(
            "SELECT l60, count(*), 100.0 * avg(active::INT) FROM p0 GROUP BY 1 ORDER BY 1").fetchall():
        print(f"  l60={k}  n={n:>9,}  active={a:5.1f}%")
    print("  README: complaint-linked ~40% vs ~15-20% (2-3x). Model B target + backtest set = l60 = 0 rows.")


# ---------------------------------------------------------------- download / acs
def download(raw: Path, only: set[str] | None, force: bool) -> None:
    import requests

    raw.mkdir(parents=True, exist_ok=True)
    for name, (sid, fn, note) in SOURCES.items():
        if only and name not in only:
            continue
        if sid is None:
            warn(f"{name}: no dataset id ({note}); download by hand to {raw / fn}")
            continue
        dst = raw / fn
        if dst.exists() and not force:
            print(f"  {name}: {dst.name} exists, skip (--force to refetch)")
            continue
        url = SOCRATA.format(id=sid)
        print(f"  {name}: {url} -> {dst}")
        tmp = dst.with_suffix(".part")
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        tmp.replace(dst)
        print(f"  {name}: {dst.stat().st_size / 1e6:,.0f} MB")


def fetch_acs(ctx: Ctx) -> None:
    import csv
    import requests

    key = os.environ.get("CENSUS_DATA_KEY")
    if not key:
        raise SystemExit("CENSUS_DATA_KEY not set (put it in .env)")
    ctx.raw.mkdir(parents=True, exist_ok=True)
    rows, header = [], None
    for county in NYC_COUNTIES:
        r = requests.get(ACS_URL, params={"get": "NAME," + ",".join(ACS_VARS), "for": "tract:*",
                                          "in": f"state:36 county:{county}", "key": key}, timeout=120)
        r.raise_for_status()
        data = r.json()
        header = data[0]
        rows += data[1:]
        print(f"  acs: county {county} {NYC_COUNTIES[county]}: {len(data) - 1} tracts")
    p = ctx.raw / SOURCES["acs_tract"][1]
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    _bake_acs_csv(ctx, p)


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=HERE / "raw" / "open", help="raw CSV dir (default data/raw/open)")
    ap.add_argument("--out", type=Path, default=HERE / "parquet", help="parquet dir (default data/parquet)")
    ap.add_argument("--only", default=None, help="comma-separated table names: " + ",".join(TABLES))
    ap.add_argument("--download", action="store_true", help="fetch CSVs from the Socrata export endpoint first")
    ap.add_argument("--force", action="store_true", help="with --download: refetch files that exist")
    ap.add_argument("--acs", action="store_true", help="pull ACS 2023 5-yr tract table via api.census.gov")
    ap.add_argument("--p0", action="store_true", help="build initial_inspections_linked and print the P0 summary")
    ap.add_argument("--no-bake", action="store_true", help="skip the CSV -> parquet step (with --download/--acs/--p0)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)

    import duckdb

    load_dotenv()
    only = set(a.only.split(",")) if a.only else None
    if only:
        bad = only - set(TABLES)
        if bad:
            raise SystemExit(f"unknown table(s): {', '.join(sorted(bad))}")

    if a.download:
        print("download")
        download(a.raw, only, a.force)

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    con.execute(MACROS)
    ctx = Ctx(con, a.raw, a.out)

    if a.acs:
        print("acs")
        fetch_acs(ctx)

    if not a.no_bake:
        print(f"bake  {a.raw} -> {a.out}")
        counts: dict[str, int | None] = {}
        for name, fn in TABLES.items():
            if only and name not in only:
                continue
            if name == "acs_tract" and a.acs:
                continue
            counts[name] = fn(ctx)
        baked = [k for k, v in counts.items() if v is not None]
        print(f"baked {len(baked)}/{len(counts)} tables")

    if a.p0:
        print("p0")
        build_p0(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
