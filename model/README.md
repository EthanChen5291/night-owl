# Barn Owl model pipeline (`model/`)

Two LightGBM models per H3 r9 cell x month, the Silence Score, a rolling-origin backtest on real
proactive inspections, and the scored files the API serves. Everything here was written and run on
2026-09-26 (event day) against the Parquet bake in `~/divMap/data/parquet/`; nothing is copied from
the working repos.

## Run

```
./model/run.sh                      # features -> train -> backtest -> score, all NYC, ~11 min on the M-series Mac
./model/run.sh --scope manhattan    # Manhattan cells only (features.py flag; the other steps follow the table)
BARNOWL_PARQUET=/path/to/parquet ./model/run.sh
```

Each script also runs on its own (`./model/features.py`, `./model/train.py`, ...); the shebang is
`uv run --with duckdb --with lightgbm --with h3 --with shap --with scikit-learn --with pandas --with pyarrow --with numpy --with matplotlib python`.
LightGBM needs `libomp` (`brew install libomp`). Optional env: `BARNOWL_RAW` (raw dir with `rmz.geojson`),
`BARNOWL_TREES` (renderer `trees.json`), `BARNOWL_THREADS` (default 10), `BARNOWL_REFIT` (backtest refit
cadence in months, default 6).

## Outputs (`model/out/`)

| File | Committed | What |
|---|---|---|
| `features.parquet` | no | 916,720 rows = 6,548 cells x 140 months (2015-01 .. 2026-08), 60 columns |
| `cells_static.parquet` | no | cell -> lat/lon, cd, rmz, borough, tract |
| `model_a.txt`, `model_b.txt`, `propensity.txt`, `model_b_boot_{0..4}.txt` | no | LightGBM boosters |
| `model_b_calibration.json` | no | isotonic calibration breakpoints for Model B (from the CV out-of-fold predictions) |
| `metrics.json` | yes | CV / holdout / ablation metrics, feature lists, params, backtest extra series means |
| `backtest.json`, `backtest.png` | yes | rolling-origin backtest in the frozen shape, and the one chart |
| `backtest_detail.json` | no | the same series plus B-alone, 311 trailing-3-month, hit-rate-given-inspected variants |
| `cells_2026-08.json`, `cells.json` | yes | `GET /cells?month=2026-08` in the frozen contract shape (`city/cells.fixture.json`) |
| `plan.json` | yes | `GET /plan?month=2026-08&k=8` |

## What each step does

**`features.py`** (22 s). Cell universe = every r9 cell containing a PLUTO lot with building area or
residential units, all five boroughs (6,548 cells). Point tables are hashed to cells from lat/lon with
the `h3` package; RMZ (`raw/open/rmz.geojson`), census tracts and parks are rasterised with
`h3.geo_to_cells` (parks at r11, so `park_share` is the share of a cell's 49 r11 children inside a
park). `cd` is the modal PLUTO community district of the cell's lots. Every trailing-window feature
(`*_3m`, `*_6m`, `*_12m`, `*_lag*`) covers the months strictly before the row's month.
Targets: `complaints` (311 rodent complaints in the cell that month), `n_initial_l60_0` and
`n_active_l60_0` (Initial inspections with no complaint on the lot in the prior 60 days, and how many
found active rat signs). Model B features (40): PLUTO (lots, units, areas, FAR, median building age,
pre-1940 / vacant / 1-2 family / mixed-use shares, floors), restaurant count and vermin-code visits
(04K/04L/08A) in the prior 3 and 12 months, DOB NB/DM permits in the prior 6 and 12 months, litter
baskets (cell and ring-1), catch basins, park share/adjacency, ACS 2023 tract income, population and
poverty with the CDBG `lomod_pct` fallback (`low_income_share`), NOAA monthly temperature (current,
3-month lag, same month last year), month-of-year, year, COVID dummy (2020-03..2021-06), RMZ flag and
zone id. Model A additionally gets complaints in the prior 1/3/12 months, ring-1 complaints (prior 3
months), the CB-month all-complaint count (2020 on), Initial inspections and active rate in the prior
12 months, months since the last inspection. `common.check_leakage` greps the B list for
`complaint|insp|cb_all|active|l60|silence|score` before every train.

**`train.py`** (~5 min). Model A: LightGBM Poisson on `complaints` with offset `log1p(res_units)`,
rows from 2016-01 (full lag history). Propensity: LightGBM binary P(cell-month gets an l60=0 Initial
inspection) on the B features + community district, out-of-fold by CD; weight = marginal rate / clip(p, 0.02, 1),
then clipped at its 1st/99th percentile. Model B: LightGBM binary on `active` for the 1.36 M l60=0
Initial inspections (each joined to its cell-month feature row), IPW weights, B features only.
Spatial CV = GroupKFold(5) by community district for everything. Holdout = every l60=0 Initial
inspection inside an RMZ in the last 12 months (2025-09..2026-08), trained on the complement.
Ablations: B without RMZ, B without ACS, B unweighted, and the leakage row (A's features on B's target).
Calibration: isotonic on the B out-of-fold predictions. CI: 5 bootstrap-resampled B models.

**`backtest.py`** (~3.5 min). Origins = every month 2016-01..2026-07. Expanding window, models refit
every 6 months (23 refits; between refits the last models are reused but the features at the origin
month are always the true lagged features). At each origin, cells are ranked by Silence Score
(`pct_b - pct_a`) and by the 311 baseline (`pct_a`, Model A's predicted-complaint percentile);
precision@50 = share of the top 50 that have at least one active l60=0 Initial inspection in that
month. `backtest.json` has exactly `{window, k, series[{month, precision_silent, precision_311,
n_positives}], summary{mean_precision_silent, mean_precision_311, lift}, synthetic: false}`.

**`score.py`** (~10 s). Scores 2026-08: `score_a`, calibrated `score_b`, percentiles across all
6,548 cells, `silence`, `ci_b` = min/max of the 5 bootstrap models (widened to include the point
estimate), Beta-Binomial prior `alpha = 10 * score_b`, `beta = 10 * (1 - score_b)`, `n_events = 0`,
SHAP TreeExplainer top-3 features on Model B, `n_inspections` = l60=0 Initial inspections in the cell
over 2015-01..2026-08, `last_event_at = null`. Planner: Manhattan cells with `silence > 0`, greedy on
`expected_gain = 100 * Var[Beta(alpha, beta)] * score_b` (posterior variance x P(active)), each pick
snapped to the nearest tree pit in the cell with a 100 m exclusion around previous picks; cells with
no pit are skipped.
