> **Note (Sat 2026-09-26):** written the night before the event as a checklist. Decisions made since, which
> override the TODOs below: sweep = ≥10 Initial inspections on one tax block on one day; restaurant 04K/08A are
> held out of Model B as an independent check; HPD violations are Model A only; binning is built from DSNY rule
> dates (see `README.md`); NOAA station `USW00094728` and ACS tables `B19013`, `B01003`, `C16002` verified and used;
> inspection `community_board` is the district number only (boro_cd = boro_code × 100 + community_board).
> Current results and methods: `model/README.md`.

# DATA DICTIONARY — Silent Blocks (DivHacks 2026)

Documentation only. Verified against the NYC Open Data metadata API on
2026-09-25 unless marked **TODO** (= from memory / not found, confirm on the
portal). Portal base: `https://data.cityofnewyork.us/resource/<id>.csv`.
Download full CSV exports (Export → CSV). Don't page the Socrata API, since it
returns only 1,000 rows by default.

---

## 0. Headline findings (read these first)

1. **04L is MICE, not rats.** Restaurant violation **04K** = "Evidence of rats
   or live rats". **04L** = "Evidence of mice or live mice". The pre-event plan said 04L. Use **04K** (rare: ~2.7k rows) as the rat signal.
   04L and 08A (harborage/conditions conducive) can serve as secondary features.
2. **Rodent Inspection has no "sweep" vs "complaint" field.** `inspection_type`
   has only Initial / Compliance / Treatments / Stoppage / Clean Ups. The sweep
   split is **structural**: see §1.
3. **311 is split across two datasets**: `erm2-nwe9` (2020–present) and
   `76ig-c548` (2010–2019). Backtests before 2020 need both.
4. **Rodent Inspection dates are dirty**: min 1918, max 2045. Filter to a sane
   window (e.g. 2010-01-01 → today).

---

## 1. DOHMH Rodent Inspection — `p937-wjvj` (TARGET for Model B)

~3.13M rows. Updated daily.

| field | type | notes |
|---|---|---|
| `job_id` | text | e.g. `PC8566721`. Since 2022, every row has the `PC` prefix, so the prefix doesn't encode the source |
| `inspection_date` | timestamp | dirty tails (1918, 2029, 2045) |
| `inspection_type` | text | `Initial`, `Compliance`, `Treatments`, `Stoppage`, `Clean Ups` |
| `result` | text | see below |
| `observations` | text | comma list: Burrows, Harborage, Droppings, Garbage, Mice, … |
| `letter_type` | text | blank / `COTA` / `Summons Issued` / `City Agency Referral` |
| `bbl`, `boro_code`, `block`, `lot`, `bin` | | join keys (bbl present on ~97%) |
| `latitude`, `longitude` | number | present on ~99% |
| `x_coord`, `y_coord` | number | NY State Plane (EPSG:2263) |
| `community_board`, `council_district`, `census_tract`, `nta`, `zip_code`, `borough` | text | |

**`result` values** (with `inspection_type`):
- Initial: `Passed` (1.63M), `Failed for Rat Activity` (256k),
  `Failed for Other Reason` (189k), `Failed for Rat Activity and Other Reason` (81k)
- Compliance: same four values (a re-check after a failed Initial)
- Treatments: `Bait applied`, `Monitoring visit`
- Stoppage: `Stoppage done` · Clean Ups: `Cleanup done`

**Model B label:** `inspection_type == "Initial"` AND result contains
`"Rat Activity"` → 1; `Initial` + any other result → 0. Drop Compliance,
Treatments, Stoppage, and Clean Ups from the label. They follow up on a
failure, so they aren't independent draws.

### Separating routine block sweeps from complaint-driven visits

There is no label. The pattern in the data is **bimodal by lots per tax block
per day** (2025 Initial inspections, grouped by `boro_code, block, date`):

| lots inspected on that block that day | block-days | inspections |
|---|---|---|
| 1 | 20,536 | 20,536 |
| 2 | 1,874 | 3,748 |
| 3–4 | 767 | 2,583 |
| 5–9 | 928 | 6,244 |
| 10+ | 4,052 | 110,880 |

- **Sweep (indexing)** = an inspector walks every lot on the block. Most
  Initial inspections (~75% in 2025) fall in 10+ lot block-days.
- **Single-lot visit** = 1 lot that day. This is the complaint-driven pattern.
- **TODO:** pick the threshold (e.g. ≥5 or ≥10 lots) and confirm with Ethan
  that it matches how he got **2% vs 67% prior-311** in the dataset tab. His
  definition and ours must agree before the backtest is scored.
- **TODO:** decide whether to also require no 311 rodent complaint at that
  BBL in the prior N days (the "prior complaint" window Ethan used).

### Rat Mitigation Zones (for the indexed holdout)
**TODO:** not found on the Open Data portal catalog. Check NYC Health
(nyc.gov/rats) for a shapefile or GeoJSON. If none exists, the zones are
Grand Concourse (Bronx), East Harlem, Chinatown/East Village/LES, and
Bushwick/Bed-Stuy. You could approximate them from community districts
(`5crt-au7u`), but say so on the slide.

---

## 2. 311 Service Requests — `erm2-nwe9` (2020→) + `76ig-c548` (2010–2019)
(TARGET for Model A; civic-engagement denominator)

| field | notes |
|---|---|
| `unique_key` | PK |
| `created_date`, `closed_date` | timestamps |
| `agency`, `complaint_type`, `descriptor` | filters |
| `bbl` | **text** here (number in rodent/PLUTO). Cast before joining |
| `latitude`, `longitude` | |
| `x_coordinate_state_plane`, `y_coordinate_state_plane` | EPSG:2263 |
| `community_board`, `incident_zip`, `borough`, `location_type` | |
| `open_data_channel_type` | PHONE / ONLINE / MOBILE … (possible bias feature, see below) |

**Rodent complaints:** `complaint_type == "Rodent"`, `descriptor` ∈
`Rat Sighting` (152k), `Condition Attracting Rodents` (45k),
`Signs of Rodents` (26k), `Mouse Sighting` (17k), `Rodent Bite - PCS Only`.
Suggest Model A uses Rat Sighting + Signs of Rodents + Condition Attracting.
Exclude Mouse Sighting.

**Civic-engagement denominator (non-rodent volume):** DSNY
`Dirty Condition`, `Missed Collection`, `Illegal Dumping`, plus noise,
street condition, and parking complaints. It measures how much a cell calls
311 in general.

**Leakage:** 311 counts may be used by Model A only. Never by Model B.
`open_data_channel_type` is a reporting-behaviour variable, so it belongs to
the bias analysis, not to either model.

---

## 3. DOHMH Restaurant Inspections — `43nn-pn8j`

| field | notes |
|---|---|
| `camis` | restaurant ID (one row per violation, so many rows per inspection) |
| `inspection_date` | `1900-01-01` = not yet inspected (**TODO** confirm, from memory) |
| `inspection_type` | e.g. `Cycle Inspection / Initial Inspection` |
| `violation_code`, `violation_description` | |
| `bbl` (text), `bin`, `latitude`, `longitude`, `nta`, `community_board` | |

- **04K** = rats (the rat signal). **04L** = mice. **08A** = harborage /
  conditions conducive to vermin.
- **Unbiased-ish slice:** `inspection_type` starting `Cycle Inspection` is
  scheduled, not complaint-driven. Filter to Cycle only if you use it as
  label-adjacent evidence.
- Restaurant density (distinct `camis` per cell) is a Model B feature.
  Filter to Cycle inspections only for 04K as a feature.
- **TODO:** decide if 04K near a cell is a *feature* for B or a secondary
  *validation* signal. It can't be both.

---

## 4. PLUTO — `64uk-42ks` (tax-lot attributes; one row per BBL)

Key fields: `bbl` (number), `borocode`, `block`, `lot`, `cd`
(community district, e.g. 303), `landuse`, `bldgclass`, `yearbuilt`,
`numfloors`, `unitsres`, `unitstotal`, `lotarea`, `bldgarea`, `retailarea`,
`comarea`, `resarea`, `latitude`, `longitude`, `xcoord`, `ycoord`,
`bct2020`, `version`.

- **Vacant lots:** `landuse == 11` (Vacant Land). **TODO** verify against
  the PLUTO data dictionary PDF.
- `yearbuilt == 0` means unknown. Treat as NaN, not as year 0.
- PLUTO is a snapshot (`version`). It's static across months, which is fine
  for a hackathon, but note it.

## 5. HPD Housing Maintenance Code Violations — `wvxf-dwi5`

Fields: `violationid`, `bbl` (text), `boroid`, `block`, `lot`, `bin`,
`class` (A/B/C = severity), `inspectiondate`, `novdescription`,
`novissueddate`, `currentstatus`, `violationstatus`, `latitude`/`longitude`
(**text**, so cast them).

- **Rodent violations:** `novdescription` contains `RATS`, `MICE`, or
  `RODENT` (~369k rows, mostly class B/C). Text match only, no clean code.
  **TODO:** find the specific § 27-2018 (vermin) order numbers for a cleaner filter.
- **Caution:** HPD violations are also triggered by tenant complaints. That
  makes them partly a complaint signal. **TODO:** decide if they are allowed
  in Model B. Strictly, the leakage rule says no, or use only the
  structural ones ("gaps/holes creating entry way").

## 6. DOB Permit Issuance — `ipu4-2q9a`

Fields: `bbl` (number), `borough`, `block`, `lot`, `job_type`, `work_type`,
`permit_type`, `permit_status`, `issuance_date` (**text**, so parse it),
`gis_latitude`/`gis_longitude` (**text**).
- Construction-displacement feature: count of `job_type` ∈ {`NB` new
  building, `DM` demolition, `A1` major alteration} issued in the last 90 days.
  **TODO** confirm code meanings.
- This dataset is legacy (BIS). Newer filings live in DOB NOW:
  `w9ak-ipjd` (Job Application Filings) and **TODO** the DOB NOW permits ID.
  Recent months may be incomplete in `ipu4-2q9a` alone.

## 7. DSNY

| dataset | id | fields | use |
|---|---|---|---|
| Monthly Tonnage | `ebb7-mvp5` | `month` (text "YYYY / MM"), `borough`, `communitydistrict`, `refusetonscollected`, … | CD-level refuse per month. Coarse, so broadcast to cells in the CD |
| Litter Basket Inventory | `8znf-7b2c` | `basketid`, `baskettype`, `latitude`, `longitude`, `district` | basket density per cell |
| Containerization rollout | **TODO** | not found | time-varying feature from the plan. Look for DSNY press or rollout data |

## 8. Physical assets / environment

| dataset | id | key fields | use |
|---|---|---|---|
| 2015 Street Tree Census | `uvpi-gqnh` | `tree_id`, `status`, `latitude`, `longitude`, `bbl`, `nta` | **node candidate assets (tree pits)**. 2015 snapshot, so some are gone |
| DEP Catch Basins | `2w2g-fk3i` | `unitid`, `latitude`, `longitude` | density feature + secondary assets |
| Parks Properties | `enfh-gkve` | `gispropnum`, `typecategory`, `acres`, `multipolygon` | park-adjacency feature |
| Community Districts | `5crt-au7u` | `boro_cd`, `the_geom` | **spatial CV folds** |
| MTA Subway Entrances 2024 | `i9wp-a4ja` (**data.ny.gov**, not NYC portal) | `entrance_latitude`, `entrance_longitude`, `station_id` | entrance density |
| DOB active sidewalk sheds | **TODO** | not found in catalog | secondary asset |

## 9. Non-portal sources

- **NOAA monthly mean temperature:** GHCN station Central Park
  `USW00094728`, GSOM monthly summaries (TAVG). **TODO** verify station ID and
  download path at ncei.noaa.gov. One value per month, citywide.
- **ACS 5-year (Census API):** median household income `B19013_001E`;
  limited-English households `C16002`. Tract-level. **TODO** verify table IDs.
  **Controls / bias quantification only, never predictors**.

---

## 10. Join keys & spatial unit

- **Unit:** H3 r9 cell × month. Assign every point-level record to a cell from
  lat/lng. For rows missing lat/lng but with BBL, take the lat/lng from PLUTO
  by `bbl`.
- **BBL** = 10 digits: borough(1) + block(5) + lot(4). Types differ by
  dataset: number in Rodent/PLUTO/DOB, **text** in 311/HPD/Restaurants.
  Normalize to a 10-char zero-padded string everywhere.
- **Tax block** = (`boro_code`, `block`). This is the key for sweep detection
  (§1). It is *not* the same as an H3 cell. One H3 r9 cell spans 2–3 blocks.
- **Community district:** Rodent/311 give `community_board` as text like
  "03 BROOKLYN" or "303" (**TODO** check format). PLUTO `cd` and
  `5crt-au7u.boro_cd` are numeric 3-digit (borocode×100 + district).
  Normalize to `boro_cd`.
- **Coordinates:** some datasets also carry State Plane (EPSG:2263). Use
  WGS84 lat/lng for H3. **TODO:** check for `0` or out-of-NYC lat/lngs and drop them.

## 10b. Downloaded to data/raw/ (2026-09-26)

pluto.csv (858k), restaurant_inspections.csv (295k), street_trees_2015.csv
(684k), dep_catch_basins.csv (154k), dsny_litter_baskets.csv (21k),
dsny_monthly_tonnage.csv (25k), mta_subway_entrances.csv (2.1k),
noaa_central_park_monthly.csv (201 months, 2010-01 → 2026-08; station
USW00094728 confirmed), community_districts.geojson (71),
parks_properties.geojson (2,061). Not downloaded: Rodent Inspection, 311
(Ethan has them), DOB permits (large).

- **CSV exports use display names, not API field names.** For example PLUTO
  has `Tax block`, `community board` instead of `block`, `cd`. Normalize the
  column names on load.
- **API pulls (filtered):** `dob_permits_nb_dm_a1.csv` (1,109,047 rows;
  job_type NB/DM/A1 only), `hpd_rodent_violations.csv` (369,335 rows;
  novdescription matches RATS/MICE/RODENT; includes mice). HPD rodent
  orders cite **§ 27-2018** (vermin), a cleaner filter than text search.
- **ACS:** `acs5_2024_nyc_tracts.csv`, 2,327 tracts, ACS 5-year 2024 (2020
  tract geography). Columns: `B01003_001E` population, `B19013_001E` median
  household income, `C16002_001E` households, `C16002_004E/007E/010E/013E`
  limited-English households (Spanish / other Indo-European / Asian-Pacific /
  other). **`-666666666` = missing** (128 tracts, e.g. Rikers). Census API
  key is personal: never commit it.
- **Tract shapes:** `census_tracts_2020.geojson` (2,325, from `63ge-mke6`).
  Join to ACS on `geoid` = state + county + tract (e.g. `36005000100`). Two
  ACS tracts have no shape (likely water-only).
- **Community districts: 71 features, but NYC has 59 real CDs.** The extra 12
  are parks/airports "joint interest areas" (boro_cd like 164, 226, 355, 480,
  595). Drop them before making spatial CV folds.

## 11. Open questions this dictionary can't answer

1. Sweep threshold, and whether it matches Ethan's 2%/67% calculation (§1).
2. What fraction of zero-complaint H3 cells got ≥1 sweep in the backtest
   window.
3. Whether HPD violations and restaurant 04K are allowed as Model B
   features under the leakage rule (§3, §5).
4. Rat Mitigation Zone boundaries source (§1).
