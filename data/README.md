# data/

`bake_open_data.py` turns `data/raw/open/*.csv` into `data/parquet/*.parquet` with DuckDB. `SCHEMA.md` has every source, column, key and gotcha.

1. `./data/bake_open_data.py --download` fetches the Socrata CSVs that have a dataset id; the ones marked "verify id" in `SCHEMA.md` §1 you place by hand under the filename it prints.
2. `./data/bake_open_data.py --acs` pulls ACS 2023 5-yr tract income/population/poverty (`CENSUS_DATA_KEY` in `.env`).
3. `./data/bake_open_data.py` bakes every table whose CSV exists and prints row counts; `--only pluto,rmz` for a subset.
4. `./data/bake_open_data.py --p0` builds `initial_inspections_linked.parquet` and prints the P0 summary (share of Initial inspections with no prior complaint, active-rate by `l60`).

`fetch_history.py` is separate and much lighter: it asks NYC Open Data for monthly and yearly aggregates of 311 rodent complaints (`76ig-c548`, `erm2-nwe9`) and DOHMH initial inspections (`p937-wjvj`), joins ACS 5-year median income and population from censusreporter.org (no key) and DOHMH ZIP neighborhood names, and writes `model/out/history.json` for the dashboard assistant. Standard library only, about a minute, no raw download; rerun it monthly with `./data/fetch_history.py`. That file is committed.

No `duckdb` CLI here: the shebang runs the script through `uv run --with duckdb --with h3 --with requests`, so `uv` is the only prerequisite. Runs are idempotent (parquet is rewritten). `raw/` and `parquet/` are gitignored; never commit data.
