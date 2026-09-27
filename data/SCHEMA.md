# NightOwl open-data schema

Every source the models read, what `data/bake_open_data.py` turns it into, the join keys, the gotchas, and the P0
finding that justifies the validation claim. Raw CSVs (~2.7 GB) live in `data/raw/open/`, baked Parquet (~222 MB)
in `data/parquet/`; both are gitignored, never committed. Rebuilt clean-room from the handoff README (§4 "Data").

Unit of analysis for the models: H3 r9 cell × month. Every point table carries `h3_r9`; every dated table carries
`month` (DATE, first of month).

## 1. Sources

Dataset ids marked **verify id** were not carried in the handoff; check the NYC Open Data page before `--download`
(the script skips them with a warning and expects the CSV placed by hand under the raw filename shown).

| # | Source | Where / dataset id | Raw file | Parquet table |
|---|---|---|---|---|
| 1 | DOHMH Rodent Inspection | NYC Open Data `p937-wjvj` | `rodent_inspection.csv` | `rodent_inspection` (3.13M rows; `Initial` = 2.16M) |
| 2 | 311 Service Requests 2010–present | NYC Open Data `erm2-nwe9` | `311_2010.csv` | `complaints_rodent` (rows < 2020-01-01) |
| 3 | 311 Service Requests 2020-onward split | NYC Open Data, **verify id** | `311_2020.csv` | `complaints_rodent` (rows ≥ 2020), `complaints_cb_month`, `complaints_zip_month` |
| 4 | PLUTO | NYC Open Data `64uk-42ks` | `pluto.csv` | `pluto` |
| 5 | DOHMH Restaurant Inspection Results | NYC Open Data `43nn-pn8j` | `restaurant_inspection.csv` | `restaurant_inspection` |
| 6 | DOB Permit Issuance | NYC Open Data `ipu4-2q9a` | `dob_permits.csv` | `dob_permits` (NB, DM only) |
| 7 | DSNY Litter Basket Inventory | NYC Open Data, **verify id** | `litter_baskets.csv` | `litter_baskets` |
| 8 | DEP catch basins | NYC Open Data, **verify id** | `catch_basins.csv` | `catch_basins` |
| 9 | Parks Properties | NYC Open Data, **verify id** | `parks_properties.csv` | `parks_properties` |
| 10 | 2015 Street Tree Census | NYC Open Data `uvpi-gqnh` | `street_trees_2015.csv` | `street_trees` |
| 11 | ACS 2023 5-year (tract) | `api.census.gov/data/2023/acs/acs5`, key `CENSUS_DATA_KEY` in `.env` | `acs_2023_5yr.csv` (cache written by `--acs`) | `acs_tract` |
| 12 | 2020 Census tract polygons | NYC Open Data, **verify id** | `census_tracts.csv` | `census_tracts` |
| 13 | NOAA Central Park monthly | NCEI GSOM, station `USW00094728`; download by hand | `noaa_central_park.csv` | `noaa_central_park` |
| 14 | Rat Mitigation Zone polygons (4 zones) | NYC Open Data / DOHMH, **verify id** (may need hand-drawing) | `rmz.csv` (WKT) or `rmz.geojson` | `rmz` |
| 15 | Community districts | NYC Open Data, **verify id** | `community_districts.csv` | `community_districts` (59 CDs + JIAs in raw) |
| 16 | HUD CDBG LMISD (tract `lomod_pct`) | HUD exchange; download by hand | `cdbg_lomod.csv` | `cdbg_lomod` (fallback for #11 nulls) |

The handoff counts 17 sources and 15 baked tables (before the ACS table was added). This list names 16 distinct
downloads; the 17th is most likely a second export of #3 (all complaint types, for the denominators) counted
separately. Reconcile against the working repo's `SCHEMA.md` when the two are merged; nothing downstream depends on
the count.

Socrata export endpoint used by `--download`: `https://data.cityofnewyork.us/api/views/<id>/rows.csv?accessType=DOWNLOAD`.

## 2. Join keys

| Key | Type | Where | Notes |
|---|---|---|---|
| `bbl` | BIGINT, 10 digits `BBBBBLLLL` (boro 1–5, block 5, lot 4) | inspections, complaints, pluto, restaurants, dob, trees | normalised from `1000010001.0` strings; DOB built from borough+block+lot. Primary key of `pluto`. |
| `h3_r9` | VARCHAR, H3 index at resolution 9 | every point table | from lat/lon; NULL when no coordinates |
| `cd` | VARCHAR, 3-digit community district GEOCODE (`101` … `595`) | inspections, complaints, pluto, restaurants, dob, baskets, basins, trees, `community_districts.cd`, `complaints_cb_month.cd` | see gotcha: 311 and inspections spell it differently; normalised by `cd_geocode()` |
| `geoid` | VARCHAR, 11-char tract `36 + county + tract` | `acs_tract`, `census_tracts`, `cdbg_lomod` | counties: Manhattan 061, Bronx 005, Brooklyn 047, Queens 081, Staten Island 085 |
| `month` | DATE, first of month | every dated table, `noaa_central_park`, the two aggregates | `date_trunc('month', …)` |
| `zip` | VARCHAR 5 | complaints, `complaints_zip_month`, pluto, restaurants, dob, trees | secondary; ZIP polygons not baked |
| `zone` | VARCHAR, RMZ name or NULL | `rmz`, `initial_inspections_linked` | point-in-polygon at P0 time |

Polygon tables (`census_tracts`, `community_districts`, `parks_properties`, `rmz`) store geometry as `geom_wkt`
VARCHAR plus `centroid_lat/lon`; load with the DuckDB `spatial` extension (`ST_GeomFromText`) to join.

## 3. Tables

Types are what DuckDB writes. `VARCHAR` unless stated. Columns in parquet order.

**rodent_inspection** — one row per inspection visit, 2010–2026.
`inspection_id` (job ticket / work order id), `job_id`, `job_progress` INT, `inspection_type` (`Initial`,
`Compliance`, `BAIT`, `CLEAN_UPS`, `STOPPAGE`), `inspection_date` DATE, `month` DATE, `result` (`Passed`,
`Rat Activity`, `Failed for Other R`, `Bait applied`, `Monitoring visit`, …), `active` BOOL (= result starts
`Rat Activity`), `is_initial` BOOL, `bbl` BIGINT, `bin`, `borough`, `zip`, `cd`, `census_tract_raw`, `nta`,
`latitude` DOUBLE, `longitude` DOUBLE, `h3_r9`, `approved_date` DATE.

**complaints_rodent** — 311 rows with `Complaint Type = Rodent`, two datasets stitched at 2020-01-01 (513k rows).
`unique_key`, `created_date` TIMESTAMP, `month` DATE, `closed_date` TIMESTAMP, `agency`, `complaint_type`,
`descriptor` (`Rat Sighting`, `Mouse Sighting`, `Signs of Rodents`, `Condition Attracting Rodents`, …),
`location_type`, `zip`, `incident_address`, `borough`, `cd`, `bbl` BIGINT, `latitude`, `longitude`, `h3_r9`,
`source` (`2010` | `2020`: which dataset the row came from).

**complaints_cb_month** / **complaints_zip_month** — all-complaint civic-engagement denominator, 2020→ only.
`cd` (or `zip`), `month` DATE, `n_all` BIGINT, `n_rodent` BIGINT.

**pluto** — one row per lot. `bbl` BIGINT (pk), `borough`, `block` INT, `lot` INT, `cd`, `bct2020`, `ct2010`,
`zip`, `address`, `bldgclass`, `landuse`, `ownertype`, `lotarea`, `bldgarea`, `comarea`, `resarea`, `numbldgs`,
`numfloors`, `unitsres`, `unitstotal` DOUBLE, `yearbuilt` INT, `yearalter1` INT (0 → NULL), `assesstot`,
`builtfar` DOUBLE, `latitude`, `longitude`, `h3_r9`.

**restaurant_inspection** — one row per violation line, 2010–2026 (the `1900-01-01` "not yet inspected" rows are
dropped). `camis`, `dba`, `borough`, `zip`, `cuisine`, `inspection_date` DATE, `month` DATE, `action`,
`violation_code`, `violation_description`, `critical_flag`, `score` INT, `grade`, `inspection_type`,
`vermin` BOOL (code in `04K` rats, `04L` mice, `08A` not vermin-proof), `rats` BOOL (`04K` only), `bbl` BIGINT,
`bin`, `cd`, `latitude`, `longitude`, `h3_r9`.

**dob_permits** — `job_type IN ('NB','DM')` (new building, demolition) only. `job_number`, `job_doc_number`,
`job_type`, `work_type`, `permit_type`, `permit_status`, `filing_date`, `issuance_date`, `month` (of issuance),
`expiration_date`, `job_start_date` DATE, `bin`, `borough`, `block` INT, `lot` INT, `bbl` BIGINT (built),
`cd`, `zip`, `latitude`, `longitude`, `h3_r9`.

**litter_baskets** — `id`, `borough`, `basket_type`, `location`, `latitude`, `longitude`, `cd`, `h3_r9`.
**catch_basins** — `id`, `borough`, `basin_type`, `latitude`, `longitude`, `cd`, `h3_r9`.
Both accept either lat/lon columns or a `the_geom` `POINT (lon lat)` WKT column.

**street_trees** — every 2015 census tree pit (the pits the planner snaps node placements to). `tree_id`,
`block_id`, `status` (`Alive`/`Dead`/`Stump`), `health`, `spc_common`, `tree_dbh` INT, `curb_loc`, `guards`
(`None`/`Helpful`/`Harmful`/`Unsure`: the tree-guard rail the node hangs from), `sidewalk`, `problems`, `zip`,
`borough`, `bbl` BIGINT, `bin`, `nta`, `boro_ct`, `latitude`, `longitude`, `cd`, `h3_r9`.

**acs_tract** — ACS 2023 5-year per tract. `geoid`, `name`, `county`, `median_income` (B19013_001E),
`population` (B01003_001E), `poverty_universe` (B17001_001E), `poverty_pop` (B17001_002E), `poverty_pct`
DOUBLE. Census sentinels (−666666666 etc.) → NULL. 135 park/industrial tracts are NULL: fall back to
`cdbg_lomod.lomod_pct`.

**cdbg_lomod** — `geoid`, `lomod_pct`, `lowmod`, `lowmod_univ` DOUBLE. NYC tracts only.

**census_tracts** — `boroname`, `ct2020`, `boro_ct2020`, `nta_name`, `nta`, `cdta2020`, `geoid`, `geom_wkt`,
`centroid_lat`, `centroid_lon`.

**community_districts** — `cd`, `boro_digit`, `shape_area`, `geom_wkt`, `centroid_lat`, `centroid_lon`. Raw file
has 59 CDs plus joint-interest areas and park districts; filter on `cd` if you need exactly 59.

**parks_properties** — `park_id`, `name`, `borough`, `type_category`, `acres`, `cd_raw` (can list several CDs,
left as text), `zip`, `geom_wkt`, `centroid_lat`, `centroid_lon`.

**rmz** — 4 rows. `zone`, `geom_wkt`, `centroid_lat`, `centroid_lon`. The script warns if the count is not 4.

**noaa_central_park** — `month` DATE, `station`, `tavg`, `tmax`, `tmin`, `prcp`, `snow` DOUBLE (GSOM units).

**initial_inspections_linked** — see §5.

## 4. Gotchas

- **Date clipping.** Inspection, complaint, restaurant and permit dates are clipped to 2010-01-01 … 2026-12-31;
  outside that is junk (1900 sentinels, typos). Done in every table function.
- **COVID dip.** 2020–21 inspection and complaint volumes drop. It is real, not a bake error; do not "fix" it.
- **`community_board` formats differ.** 311 writes `01 MANHATTAN` / `Unspecified BROOKLYN`; inspections, PLUTO and
  DOB write `101` (sometimes `101.0`). Everything is normalised to the 3-digit GEOCODE (`boro digit + 2-digit CB`)
  in `cd`; `Unspecified` → NULL. Join on `cd`, never on the raw string.
- **Pre-2020 complaints lack BBL.** 23% of pre-2020 311 rodent rows have no BBL, so every BBL-linked count
  (`l60`, `l180`) is an undercount; "no prior complaint" is therefore slightly overstated pre-2020.
- **Two 311 datasets.** `complaints_rodent` takes rows before 2020-01-01 from the 2010–present dataset and rows
  from 2020-01-01 on from the 2020-onward split; `source` says which. The CB/ZIP-month denominators exist only
  from 2020 because they come from the split alone.
- **ACS nulls.** 135 tracts (parks, industrial, water) have no median income. Fall back to `cdbg_lomod.lomod_pct`
  on `geoid`; do not drop the tract.
- **Containerization status is not available anywhere.** If the model needs it, hand-code the rollout from DSNY
  announcements (CD × start month); it is not in this bake.
- **Restaurant rows are violation lines**, not inspections. Aggregate on `camis, inspection_date` before counting.
- **`is_initial` is the only visit-type flag.** No field says proactive vs complaint-driven; that is what P0 is for.
- **H3 coverage.** `h3_r9` is NULL when the row has no usable coordinates (bounding box 40.45–40.95 N,
  −74.30 … −73.65 E); rows are kept, not dropped, except in the pure point tables (baskets, basins, trees).

## 5. P0: `initial_inspections_linked.parquet`

The validation claim ("proactive inspections are ~130k near-unbiased outcomes a year") rests on this table.

Every `Initial` inspection from 2015-01 to 2026-08, joined to `complaints_rodent` on `bbl`:

| Column | Type | Meaning |
|---|---|---|
| `inspection_id` | VARCHAR | from `rodent_inspection` |
| `bbl` | BIGINT | lot |
| `inspection_date` | DATE | |
| `month` | DATE | first of month |
| `result` | VARCHAR | raw result string |
| `active` | BOOL | `result` = `Rat Activity` |
| `zone` | VARCHAR | RMZ name the point falls in, or NULL |
| `l60` | INT 0/1 | a rodent complaint on the same BBL in the prior 60 days |
| `l180` | INT 0/1 | same, prior 180 days |
| `h3_r9` | VARCHAR | cell |
| `cd` | VARCHAR | community district GEOCODE |

**Result** (from the handoff, reproduced by `--p0`): no field says proactive vs complaint-driven, but the BBL join
shows **75–91% of Initial inspections have no prior complaint on the lot**, i.e. ~130k quasi-unbiased outcomes a
year, half inside RMZs. Complaint-linked inspections find active rats **2–3× as often (≈40% vs 15–20%)**. That is
the selection bias in one number and the reason Model B never sees complaint counts.

**Use:** `l60 = 0` rows are the Model B target and the backtest set (decision 8 in the handoff). `l60 = 1` rows
are "what the city sees" and feed Model A only. Remember the pre-2020 BBL undercount when reading the yearly shares.

`--p0` prints, per year, the share of Initial inspections with `l60 = 0` and `l180 = 0` and the share inside an
RMZ, then the active-rate for `l60 = 0` vs `l60 = 1`. Compare against the numbers above; if they move, the bake
changed, not the city.

## 6. How to regenerate

```
./data/bake_open_data.py --download        # Socrata CSVs for the sources with ids; hand-place the "verify id" ones
./data/bake_open_data.py --acs             # ACS via api.census.gov (CENSUS_DATA_KEY in .env)
./data/bake_open_data.py                   # CSV -> parquet, one DuckDB statement per table, prints row counts
./data/bake_open_data.py --p0              # initial_inspections_linked + the P0 summary
./data/bake_open_data.py --only pluto,rmz  # rebake a subset
```

Tooling: there is no `duckdb` CLI on the box; `uv` is installed and the script's shebang is
`#!/usr/bin/env -S uv run --with duckdb --with h3 --with requests python`, so `./data/bake_open_data.py` just
works. H3 comes from the DuckDB `h3` community extension when it installs, else the `h3` Python package as a UDF,
else NULL with a warning. Polygon centroids and the P0 `zone` need the DuckDB `spatial` extension; without it they
are NULL and the script says so. Every run rewrites the parquet it touches; nothing under `data/raw/` or
`data/parquet/` is ever committed.
