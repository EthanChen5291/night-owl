"""Shared paths, month grid, feature lists and small helpers for the Barn Owl model pipeline."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
PARQUET = Path(os.environ.get("BARNOWL_PARQUET", "~/divMap/data/parquet")).expanduser()
RAW = Path(os.environ.get("BARNOWL_RAW", str(PARQUET.parent / "raw" / "open"))).expanduser()
TREES_JSON = Path(os.environ.get("BARNOWL_TREES", "~/divMap/public/city/trees.json")).expanduser()

FIRST_MONTH, LAST_MONTH = "2015-01", "2026-08"
MONTHS = [str(p) for p in pd.period_range(FIRST_MONTH, LAST_MONTH, freq="M")]
MONTH_IDX = {m: i for i, m in enumerate(MONTHS)}
COVID = ("2020-03", "2021-06")  # shaded in the backtest chart, dummy in the features
H3_RES = 9
N_THREADS = int(os.environ.get("BARNOWL_THREADS", "10"))

# Model B ("what's there") may only see physical / environmental features. Nothing here is
# derived from 311 or from inspections; FORBIDDEN is grepped against this list before every train.
B_FEATURES = [
    # PLUTO (static)
    "pluto_lots", "pluto_res_units", "pluto_units_total", "pluto_bldg_area", "pluto_lot_area", "pluto_far",
    "pluto_bldg_age_median", "pluto_share_pre1940", "pluto_vacant_share", "pluto_com_area_share",
    "pluto_share_1_2fam", "pluto_mixed_share", "pluto_median_floors", "pluto_numbldgs",
    # restaurants (lagged, trailing windows exclude the current month)
    "rest_count", "rest_vermin_3m", "rest_vermin_12m", "rest_visits_12m",
    # DOB permits (lagged)
    "dob_nb_6m", "dob_dm_6m", "dob_nb_12m", "dob_dm_12m",
    # street furniture (static)
    "litter_baskets", "litter_baskets_ring1", "catch_basins",
    # parks (static)
    "park_share", "park_adjacent",
    # ACS tract with the CDBG fallback (static)
    "acs_median_income", "acs_population", "acs_poverty_rate", "cdbg_lomod_pct", "low_income_share",
    # weather
    "tavg_f", "tavg_lag3", "tavg_prev_year",
    # calendar
    "month_of_year", "year", "covid",
    # RMZ (policy flag, kept in B for v1; ablated in train.py)
    "rmz_flag", "rmz_id",
]
A_ONLY_FEATURES = [
    "complaints_lag1", "complaints_lag3", "complaints_lag12", "complaints_ring1_lag3",
    "cb_all_complaints_lag1",
    "insp_lag12", "insp_active_rate_lag12", "months_since_last_insp",
]
A_FEATURES = B_FEATURES + A_ONLY_FEATURES
FORBIDDEN = ("complaint", "insp", "cb_all", "active", "l60", "silence", "score")
RMZ_ABLATION = [f for f in B_FEATURES if f.startswith("rmz")]
ACS_ABLATION = [f for f in B_FEATURES if f.startswith("acs_") or f.startswith("cdbg_") or f == "low_income_share"]
TARGETS = ["complaints", "n_initial_l60_0", "n_active_l60_0"]


def check_leakage(features: list[str]) -> None:
    bad = [f for f in features if any(s in f for s in FORBIDDEN)]
    if bad:
        raise SystemExit(f"leakage: forbidden columns in the Model B feature list: {bad}")


def load_features(scope: str | None = None) -> pd.DataFrame:
    df = pd.read_parquet(OUT / "features.parquet")
    if scope == "manhattan":
        df = df[df["borough"] == "MN"].reset_index(drop=True)
    return df


def percentile_rank(x: np.ndarray) -> np.ndarray:
    """0..100 percentile of each value among all values (average rank on ties)."""
    from scipy.stats import rankdata

    x = np.asarray(x, dtype=float)
    return 100.0 * rankdata(x, method="average") / len(x)


def lgb_params(objective: str, seed: int = 0, **kw) -> dict:
    p = dict(
        objective=objective, learning_rate=0.06, num_leaves=31, min_data_in_leaf=100,
        feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
        verbose=-1, num_threads=N_THREADS, seed=seed, deterministic=False,
    )
    p.update(kw)
    return p


def dump_json(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=1, allow_nan=False))


class Timer:
    def __init__(self, label: str):
        self.label, self.t0 = label, time.time()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        print(f"[{self.label}] {time.time() - self.t0:.1f}s", flush=True)
