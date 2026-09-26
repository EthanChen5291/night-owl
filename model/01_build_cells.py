"""Step 1: inspections + 311 rat complaints -> H3 r9 cells x month.

Outputs (in data/processed/):
  inspections.parquet  one row per Initial inspection, with h3, is_sweep, is_rat,
                       prior-complaint flags
  complaints.parquet   one row per 311 rat complaint, with h3
  cells.parquet        one row per H3 cell: centroid + community district
  cell_month.parquet   one row per (h3, month): complaint and inspection counts

Run: python3 model/01_build_cells.py
"""
import duckdb
import geopandas as gpd
import h3
import pandas as pd

from config import (H3_RES, NYC_LAT, NYC_LNG, PROCESSED, RAT_DESCRIPTORS, RAW,
                    START_DATE, SWEEP_MIN_LOTS)

con = duckdb.connect()


def add_h3(df: pd.DataFrame) -> pd.DataFrame:
    df["h3"] = [h3.latlng_to_cell(la, lo, H3_RES) for la, lo in zip(df.latitude, df.longitude)]
    return df


in_nyc = (f"latitude between {NYC_LAT[0]} and {NYC_LAT[1]} "
          f"and longitude between {NYC_LNG[0]} and {NYC_LNG[1]}")

# ---- Inspections: Initial only (Compliance/Treatments follow a failure, not independent draws)
insp = con.sql(f"""
    select job_id,
           cast(inspection_date as date)                         as date,
           result,
           result like '%Rat Activity%'                          as is_rat,
           lpad(cast(cast(bbl as bigint) as varchar), 10, '0')   as bbl,
           boro_code, block, lot,
           boro_code * 100 + try_cast(community_board as int)    as boro_cd_reported,
           latitude, longitude
    from read_csv_auto('{RAW / "rodent_inspections.csv"}')
    where inspection_type = 'Initial'
      and inspection_date between '{START_DATE}' and current_date
      and {in_nyc}
""").df()

# Sweep = inspector walked the block: many lots on one tax block on one day.
lots = insp.groupby(["boro_code", "block", "date"]).job_id.transform("size")
insp["lots_on_block_that_day"] = lots
insp["is_sweep"] = lots >= SWEEP_MIN_LOTS
insp = add_h3(insp)

# ---- 311 rat complaints (both datasets, deduped)
files = [str(RAW / "311_rodent_2010_2019.csv"), str(RAW / "311_rodent_2020_present.csv")]
descs = ", ".join(f"'{d}'" for d in RAT_DESCRIPTORS)
comp = con.sql(f"""
    select distinct on (unique_key)
           unique_key,
           cast(created_date as date)                                  as date,
           descriptor,
           lpad(cast(try_cast(bbl as bigint) as varchar), 10, '0')     as bbl,
           latitude, longitude,
           open_data_channel_type                                      as channel
    from read_csv_auto({files}, union_by_name = true)
    where descriptor in ({descs})
      and created_date >= '{START_DATE}'
      and {in_nyc}
""").df()
comp = add_h3(comp)

# ---- Ethan's rule, for cross-checking: was there a rat complaint on the same lot before?
con.register("insp_df", insp[["job_id", "bbl", "date"]])
con.register("comp_df", comp.loc[comp.bbl.notna(), ["bbl", "date"]].rename(columns={"date": "cdate"}))
prior = con.sql("""
    select i.job_id, c.cdate as last_complaint_date
    from insp_df i asof left join comp_df c
      on i.bbl = c.bbl and c.cdate <= i.date
""").df()
insp = insp.merge(prior, on="job_id", how="left")
days = (pd.to_datetime(insp.date) - pd.to_datetime(insp.last_complaint_date)).dt.days
insp["prior_complaint_any"] = days.notna()
insp["prior_complaint_365d"] = days.le(365)

# ---- Cells: centroid + community district (by centroid-in-polygon)
cells = pd.DataFrame({"h3": pd.unique(pd.concat([insp.h3, comp.h3]))})
cells[["lat", "lng"]] = [h3.cell_to_latlng(c) for c in cells.h3]
cd = gpd.read_file(RAW / "community_districts.geojson")[["boro_cd", "geometry"]]
cd["boro_cd"] = cd.boro_cd.astype(int)
pts = gpd.GeoDataFrame(cells, geometry=gpd.points_from_xy(cells.lng, cells.lat), crs=4326)
cells = (gpd.sjoin(pts, cd.to_crs(4326), how="left", predicate="within")
         .drop(columns=["geometry", "index_right"]))
cells = cells.drop_duplicates("h3")
# 12 codes (164, 226, ...) are parks/airports, not real districts
cells["real_cd"] = cells.boro_cd.notna() & (cells.boro_cd % 100 <= 18)

# ---- Cell x month counts
insp["month"] = pd.to_datetime(insp.date).dt.to_period("M").astype(str)
comp["month"] = pd.to_datetime(comp.date).dt.to_period("M").astype(str)
insp["sweep_rat"] = insp.is_sweep & insp.is_rat
im = insp.groupby(["h3", "month"]).agg(
    n_initial=("job_id", "size"),
    n_rat=("is_rat", "sum"),
    n_sweep=("is_sweep", "sum"),
    n_sweep_rat=("sweep_rat", "sum"),
)
cm = comp.groupby(["h3", "month"]).size().rename("n_complaints")
cell_month = im.join(cm, how="outer").fillna(0).astype(int).reset_index()

# ---- Save
insp.to_parquet(PROCESSED / "inspections.parquet", index=False)
comp.to_parquet(PROCESSED / "complaints.parquet", index=False)
cells.to_parquet(PROCESSED / "cells.parquet", index=False)
cell_month.to_parquet(PROCESSED / "cell_month.parquet", index=False)

# ---- Checks to eyeball
sw, si = insp[insp.is_sweep], insp[~insp.is_sweep]
print(f"Initial inspections: {len(insp):,}   rat complaints: {len(comp):,}")
print(f"cells: {len(cells):,}   cell-months: {len(cell_month):,}   "
      f"cells without a real CD: {(~cells.real_cd).sum():,}")
print(f"sweep share of Initial inspections: {insp.is_sweep.mean():.1%}")
print(f"rat-found rate   sweeps: {sw.is_rat.mean():.1%}   single-lot/other: {si.is_rat.mean():.1%}")
print(f"prior complaint on lot (365d)   sweeps: {sw.prior_complaint_365d.mean():.1%}   "
      f"other: {si.prior_complaint_365d.mean():.1%}")
print(f"Ethan's rule (no prior complaint ever) share: {(~insp.prior_complaint_any).mean():.1%}   "
      f"agreement with sweep flag: {(insp.is_sweep == ~insp.prior_complaint_any).mean():.1%}")

# Owed query: of cells with zero complaints in the last 12 months, how many got >=1 sweep?
last = sorted(cell_month.month.unique())[-12:]
recent = cell_month[cell_month.month.isin(last)].groupby("h3")[["n_complaints", "n_sweep"]].sum()
recent = recent.reindex(cells.h3, fill_value=0)
zero = recent[recent.n_complaints == 0]
print(f"last 12 months: {len(zero):,} of {len(recent):,} cells had zero complaints; "
      f"{(zero.n_sweep > 0).mean():.1%} of those got at least one sweep")
