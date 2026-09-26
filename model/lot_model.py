"""Experiment: Model B at the building (tax lot) level instead of the cell level.

Rows = every swept Initial inspection. Features = the lot's own PLUTO attributes (age, height,
units, land use, building class, areas, vacant, has a restaurant) + the cell-month B features.
Evaluated with the same spatial CV (hold out whole community districts). The cell-level
Model B's AUC is directly comparable: it is the lot-level AUC with every lot in a cell-month
given the same score.

Run: python3 model/lot_model.py   -> prints both AUCs, writes out/lot_model_metrics.json
"""
import importlib
import json
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from config import PROCESSED, RAW

models = importlib.import_module("03_models")
OUT = Path(__file__).resolve().parent / "out"

LOT_FEATS = ["lot_year_built", "lot_floors", "lot_units_res", "lot_landuse", "lot_bldg_class",
             "lot_area", "lot_bldg_area", "lot_com_area", "lot_retail_area", "lot_is_vacant",
             "lot_has_restaurant", "lot_n_bldgs"]


def lot_table() -> pd.DataFrame:
    con = duckdb.connect()
    pluto = con.sql(f"""
        select lpad(cast(BBL as varchar), 10, '0') as bbl,
               nullif(yearbuilt, 0) as lot_year_built, numfloors as lot_floors,
               unitsres as lot_units_res, landuse as lot_landuse,
               left(bldgclass, 1) as lot_bldg_class, lotarea as lot_area,
               bldgarea as lot_bldg_area, comarea as lot_com_area, retailarea as lot_retail_area,
               (landuse = 11) as lot_is_vacant, numbldgs as lot_n_bldgs
        from read_csv_auto('{RAW / "pluto.csv"}', sample_size = 50000) where BBL is not null""").df()
    food = con.sql(f"""select distinct lpad(cast(BBL as varchar), 10, '0') as bbl
        from read_csv_auto('{RAW / "restaurant_inspections.csv"}', sample_size = 50000)
        where BBL is not null""").df()
    pluto["lot_has_restaurant"] = pluto.bbl.isin(set(food.bbl))
    pluto["lot_bldg_class"] = pluto.lot_bldg_class.astype("category")
    return pluto.drop_duplicates("bbl")


def main() -> None:
    insp = pd.read_parquet(PROCESSED / "inspections.parquet",
                           columns=["bbl", "h3", "month", "is_sweep", "is_rat"])
    insp = insp[insp.is_sweep]
    df = models.load()
    feats_cm = df[["h3", "month", "boro_cd", "real_cd"] + models.B_FEATS]
    rows = (insp.merge(feats_cm, on=["h3", "month"], how="inner")
                .merge(lot_table(), on="bbl", how="left"))
    rows = rows[rows.real_cd & (rows.month <= "2026-08")].reset_index(drop=True)
    for c in ["lot_has_restaurant", "lot_is_vacant"]:  # bools become object after the left join
        rows[c] = rows[c].astype("float")
    y = rows.is_rat.astype(int).to_numpy()
    print(f"swept lots: {len(rows):,}, matched to PLUTO: {rows.lot_floors.notna().mean():.1%}, rat rate {y.mean():.3f}")

    X_lot = rows[models.B_FEATS + LOT_FEATS]
    gkf = GroupKFold(n_splits=5)
    p_lot = np.zeros(len(rows))
    for tr, te in gkf.split(rows, groups=rows.boro_cd):
        m = lgb.LGBMClassifier(random_state=0, **models.PARAMS)
        m.fit(X_lot.iloc[tr], y[tr])
        p_lot[te] = m.predict_proba(X_lot.iloc[te])[:, 1]

    # Cell-level Model B, evaluated at the lot level (same score for every lot in a cell-month)
    cm = df[(df.n_sweep > 0) & df.real_cd & (df.month <= "2026-08")].reset_index(drop=True)
    p_cell = pd.Series(np.nan, index=cm.index)
    for tr, te in gkf.split(cm, groups=cm.boro_cd):
        p_cell.iloc[te] = models.fit_b(cm.iloc[tr]).predict(cm.iloc[te][models.B_FEATS])
    cell_score = cm.assign(p=p_cell)[["h3", "month", "p"]]
    p_cellwise = rows[["h3", "month"]].merge(cell_score, on=["h3", "month"], how="left").p.to_numpy()

    # Does it also rank CELLS better? Average the lot predictions per cell-month (over the lots
    # swept that month) and give every lot that cell-month average.
    p_lot_as_cell = rows.assign(p=p_lot).groupby(["h3", "month"]).p.transform("mean").to_numpy()
    res = {"n_swept_lots": int(len(rows)),
           "auc_cell_model": round(roc_auc_score(y, p_cellwise), 4),
           "auc_lot_model": round(roc_auc_score(y, p_lot), 4),
           "auc_lot_model_averaged_per_cell": round(roc_auc_score(y, p_lot_as_cell), 4)}
    imp = pd.Series(m.booster_.feature_importance("gain"), index=X_lot.columns)
    res["top_features_lot_model"] = (imp / imp.sum() * 100).sort_values(ascending=False).head(10).round(1).to_dict()
    print(json.dumps(res, indent=2))
    OUT.mkdir(exist_ok=True)
    (OUT / "lot_model_metrics.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
