"""Building-level (tax lot) Model B.

Training rows = swept Initial inspections: the lot's own PLUTO attributes + the cell-month B
features, label = rat activity found. A cell's score = mean predicted risk over ALL its lots
(not just the ones swept), so ranking a cell never uses who DOHMH picked to inspect.

Held-out-district AUC (lot_model.py): 0.692 per building, 0.649 averaged per cell, vs 0.630 for
the cell-level model.
"""
import importlib

import duckdb
import h3
import lightgbm as lgb
import numpy as np
import pandas as pd

from config import H3_RES, NYC_LAT, NYC_LNG, PROCESSED, RAW

models = importlib.import_module("03_models")

LOT_FEATS = ["lot_year_built", "lot_floors", "lot_units_res", "lot_landuse", "lot_bldg_class",
             "lot_area", "lot_bldg_area", "lot_com_area", "lot_retail_area", "lot_is_vacant",
             "lot_has_restaurant", "lot_n_bldgs"]
FEATS = models.B_FEATS + LOT_FEATS
_LOTS = None


def lots() -> pd.DataFrame:
    """One row per PLUTO tax lot with its H3 cell and lot features (cached as parquet)."""
    global _LOTS
    if _LOTS is not None:
        return _LOTS
    path = PROCESSED / "lots.parquet"
    if not path.exists():
        con = duckdb.connect()
        df = con.sql(f"""
            select lpad(cast(BBL as varchar), 10, '0') as bbl, address, latitude, longitude,
                   nullif(yearbuilt, 0) as lot_year_built, numfloors as lot_floors,
                   unitsres as lot_units_res, landuse as lot_landuse,
                   left(bldgclass, 1) as lot_bldg_class, bldgclass, lotarea as lot_area,
                   bldgarea as lot_bldg_area, comarea as lot_com_area, retailarea as lot_retail_area,
                   cast(landuse = 11 as double) as lot_is_vacant, numbldgs as lot_n_bldgs
            from read_csv_auto('{RAW / "pluto.csv"}', sample_size = 50000)
            where BBL is not null and latitude between {NYC_LAT[0]} and {NYC_LAT[1]}
              and longitude between {NYC_LNG[0]} and {NYC_LNG[1]}""").df().drop_duplicates("bbl")
        food = con.sql(f"""select distinct lpad(cast(BBL as varchar), 10, '0') as bbl
            from read_csv_auto('{RAW / "restaurant_inspections.csv"}', sample_size = 50000)
            where BBL is not null""").df()
        df["lot_has_restaurant"] = df.bbl.isin(set(food.bbl)).astype(float)
        df["h3"] = [h3.latlng_to_cell(a, b, H3_RES) for a, b in zip(df.latitude, df.longitude)]
        df.to_parquet(path, index=False)
    _LOTS = pd.read_parquet(path)
    _LOTS["lot_bldg_class"] = _LOTS.lot_bldg_class.astype("category")
    return _LOTS


def training_rows(df: pd.DataFrame, until: str) -> pd.DataFrame:
    """Swept Initial inspections up to `until`, with cell-month + lot features."""
    insp = pd.read_parquet(PROCESSED / "inspections.parquet",
                           columns=["bbl", "h3", "month", "is_sweep", "is_rat"])
    insp = insp[insp.is_sweep & (insp.month <= until)]
    cm = df[["h3", "month", "boro_cd"] + models.B_FEATS]
    lot = lots()[["bbl"] + LOT_FEATS]
    return insp.merge(cm, on=["h3", "month"], how="inner").merge(lot, on="bbl", how="left")


def fit(rows: pd.DataFrame, seed: int = 0, weight=None):
    m = lgb.LGBMClassifier(random_state=seed, **models.PARAMS)
    return m.fit(rows[FEATS], rows.is_rat.astype(int), sample_weight=weight)


def predict_lots(model, cell_month: pd.DataFrame) -> pd.DataFrame:
    """Predict every lot in the given cells, using each cell's row in `cell_month`."""
    x = lots()[lots().h3.isin(cell_month.h3)].merge(cell_month[["h3"] + models.B_FEATS], on="h3")
    return x.assign(risk=model.predict_proba(x[FEATS])[:, 1])


def cell_scores(model, cell_month: pd.DataFrame) -> pd.Series:
    """Mean lot risk per cell (index h3). Cells with no lots are missing."""
    return predict_lots(model, cell_month).groupby("h3").risk.mean()
