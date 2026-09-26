"""Step 2: physical / environmental features per cell and per cell-month.

Outputs (in data/processed/):
  features_static.parquet  one row per H3 cell (buildings, restaurants, trash,
                           drains, trees, subway, parks, ACS controls)
  panel.parquet            dense (h3, month) panel: step-1 counts + lagged
                           time-varying features. This is what step 3 trains on.

All time-varying features use only months BEFORE the row's month (no leakage).
Run: python3 model/02_features.py
"""
import duckdb
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from config import H3_RES, NYC_LAT, NYC_LNG, PROCESSED, RAW

con = duckdb.connect()
cells = pd.read_parquet(PROCESSED / "cells.parquet")


def points(sql: str) -> pd.DataFrame:
    """Run SQL returning latitude/longitude (+ extras), keep NYC points, add h3."""
    df = con.sql(sql).df()
    df = df[df.latitude.between(*NYC_LAT) & df.longitude.between(*NYC_LNG)].copy()
    df["h3"] = [h3.latlng_to_cell(a, b, H3_RES) for a, b in zip(df.latitude, df.longitude)]
    return df


def count_per_cell(sql: str, name: str) -> pd.Series:
    return points(sql).groupby("h3").size().rename(name)


# ---------------------------------------------------------------- static features
pluto = points(f"""
    select latitude, longitude, landuse, yearbuilt, numfloors, unitsres,
           bldgarea, resarea, comarea, retailarea, BBL as bbl, "community board" as cb
    from read_csv_auto('{RAW / "pluto.csv"}', sample_size = 50000)
""")
pluto["yearbuilt"] = pluto.yearbuilt.where(pluto.yearbuilt > 1800)  # 0 = unknown
g = pluto.groupby("h3")
f_pluto = pd.DataFrame({
    "n_lots": g.size(),
    "year_built_median": g.yearbuilt.median(),
    "share_pre1940": g.yearbuilt.apply(lambda s: (s < 1940).sum() / max(s.notna().sum(), 1)),
    "share_vacant": g.landuse.apply(lambda s: (s == 11).mean()),
    "share_residential": g.landuse.apply(lambda s: s.isin([1, 2, 3]).mean()),
    "share_mixed_use": g.landuse.apply(lambda s: (s == 4).mean()),
    "share_commercial": g.landuse.apply(lambda s: (s == 5).mean()),
    "share_industrial": g.landuse.apply(lambda s: (s == 6).mean()),
    "floors_mean": g.numfloors.mean(),
    "units_res": g.unitsres.sum(),
    "bldg_area": g.bldgarea.sum(),
    "retail_area": g.retailarea.sum(),
    "com_area": g.comarea.sum(),
})

f_rest = count_per_cell(f"""
    select distinct CAMIS, Latitude as latitude, Longitude as longitude
    from read_csv_auto('{RAW / "restaurant_inspections.csv"}', sample_size = 50000)
""", "n_restaurants")
f_baskets = count_per_cell(f"""select Latitude as latitude, Longitude as longitude
    from read_csv_auto('{RAW / "dsny_litter_baskets.csv"}')""", "n_litter_baskets")
f_basins = count_per_cell(f"""select LATITUDE as latitude, LONGITUDE as longitude
    from read_csv_auto('{RAW / "dep_catch_basins.csv"}')""", "n_catch_basins")
f_trees = count_per_cell(f"""select latitude, longitude
    from read_csv_auto('{RAW / "street_trees_2015.csv"}') where status = 'Alive'""", "n_trees")
f_subway = count_per_cell(f"""select "Entrance Latitude" as latitude, "Entrance Longitude" as longitude
    from read_csv_auto('{RAW / "mta_subway_entrances.csv"}')""", "n_subway_entrances")

# Park share of each cell's area (projected to NY State Plane, feet)
hexes = gpd.GeoDataFrame(
    cells[["h3"]],
    geometry=[Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells.h3],
    crs=4326,
).to_crs(2263)
parks = gpd.read_file(RAW / "parks_properties.geojson")[["geometry"]].to_crs(2263)
inter = gpd.overlay(hexes, parks, how="intersection", keep_geom_type=True)
park_area = inter.assign(a=inter.area).groupby("h3").a.sum()
f_parks = (park_area / hexes.set_index("h3").area).clip(0, 1).rename("share_park")

# ACS controls (not predictors of interest): tract of the cell centroid
acs = pd.read_csv(RAW / "acs5_2024_nyc_tracts.csv", dtype=str)
acs["geoid"] = acs.state + acs.county + acs.tract
num = ["B01003_001E", "B19013_001E", "C16002_001E", "C16002_004E",
       "C16002_007E", "C16002_010E", "C16002_013E"]
acs[num] = acs[num].astype(float).where(lambda d: d >= 0)  # -666666666 = missing
acs["limited_english_share"] = acs[num[3:]].sum(axis=1) / acs.C16002_001E
tracts = gpd.read_file(RAW / "census_tracts_2020.geojson")[["geoid", "geometry"]].to_crs(2263)
tracts["tract_area_km2"] = tracts.area * 0.3048 ** 2 / 1e6
tracts = tracts.merge(acs[["geoid", "B01003_001E", "B19013_001E", "limited_english_share"]], on="geoid", how="left")
tracts["pop_density"] = tracts.B01003_001E / tracts.tract_area_km2
cent = gpd.GeoDataFrame(cells[["h3"]], geometry=gpd.points_from_xy(cells.lng, cells.lat), crs=4326).to_crs(2263)
f_acs = (gpd.sjoin(cent, tracts, how="left", predicate="within")
         .drop_duplicates("h3").set_index("h3")
         .rename(columns={"B19013_001E": "median_income"})
         [["median_income", "pop_density", "limited_english_share"]])

static = (cells.set_index("h3")[["lat", "lng", "boro_cd", "real_cd"]]
          .join([f_pluto, f_rest, f_baskets, f_basins, f_trees, f_subway, f_parks, f_acs]))
count_cols = ["n_lots", "units_res", "bldg_area", "retail_area", "com_area", "n_restaurants",
              "n_litter_baskets", "n_catch_basins", "n_trees", "n_subway_entrances", "share_park"]
static[count_cols] = static[count_cols].fillna(0)
static.reset_index().to_parquet(PROCESSED / "features_static.parquet", index=False)

# ---------------------------------------------------------------- time-varying features
cell_month = pd.read_parquet(PROCESSED / "cell_month.parquet")
months = pd.period_range(cell_month.month.min(), cell_month.month.max(), freq="M").astype(str)
panel = (pd.MultiIndex.from_product([cells.h3, months], names=["h3", "month"])
         .to_frame(index=False)
         .merge(cell_month, on=["h3", "month"], how="left"))
count_like = ["n_initial", "n_rat", "n_sweep", "n_sweep_rat", "n_complaints"]
panel[count_like] = panel[count_like].fillna(0).astype(int)


def monthly_counts(df: pd.DataFrame, date_col: str, name: str) -> pd.DataFrame:
    df = df.assign(month=pd.to_datetime(df[date_col]).dt.to_period("M").astype(str))
    return df.groupby(["h3", "month"]).size().rename(name).reset_index()


# DOB mixes MM/DD/YYYY and YYYY-MM-DD, so parse both.
dob = points(f"""
    select * from (
        select gis_latitude as latitude, gis_longitude as longitude,
               coalesce(try_strptime(issuance_date, '%m/%d/%Y'),
                        try_strptime(issuance_date, '%Y-%m-%d')) as issuance_date
        from read_csv_auto('{RAW / "dob_permits_nb_dm_a1.csv"}', types = {{'issuance_date': 'VARCHAR'}}))
    where issuance_date >= '2009-01-01'""")
rest_v = points(f"""
    select Latitude as latitude, Longitude as longitude, "INSPECTION DATE" as d,
           "VIOLATION CODE" as code
    from read_csv_auto('{RAW / "restaurant_inspections.csv"}', sample_size = 50000)
    where "INSPECTION TYPE" like 'Cycle Inspection%' and "VIOLATION CODE" in ('04K', '08A')""")
hpd = points(f"""select latitude, longitude, inspectiondate
    from read_csv_auto('{RAW / "hpd_rodent_violations.csv"}') where inspectiondate >= '2009-01-01'""")

for df in [monthly_counts(dob, "issuance_date", "dob_permits"),
           monthly_counts(rest_v[rest_v.code == "04K"], "d", "rest_04k"),
           monthly_counts(rest_v[rest_v.code == "08A"], "d", "rest_08a"),
           monthly_counts(hpd, "inspectiondate", "hpd_rodent")]:
    panel = panel.merge(df, on=["h3", "month"], how="left")
raw_monthly = ["dob_permits", "rest_04k", "rest_08a", "hpd_rodent"]
panel[raw_monthly] = panel[raw_monthly].fillna(0)

# Lagged rolling sums: features for month m only see months < m.
panel = panel.sort_values(["h3", "month"]).reset_index(drop=True)
grp = panel.groupby("h3", sort=False)


def lagged_sum(col: str, window: int) -> pd.Series:
    return grp[col].transform(lambda s: s.shift(1).rolling(window, min_periods=1).sum()).fillna(0)


panel["dob_permits_3m"] = lagged_sum("dob_permits", 3)
panel["rest_04k_12m"] = lagged_sum("rest_04k", 12)
panel["rest_08a_12m"] = lagged_sum("rest_08a", 12)
panel["hpd_rodent_12m"] = lagged_sum("hpd_rodent", 12)          # Model A only (complaint-triggered)
panel["complaints_1m"] = lagged_sum("n_complaints", 1)          # Model A only
panel["complaints_12m"] = lagged_sum("n_complaints", 12)        # Model A only
panel = panel.drop(columns=raw_monthly)

# Binning (DSNY containerization): share of a cell's lots that must put trash in lidded
# bins by that month. Each lot's start date comes from its type; a lot counts from the
# earliest rule that covers it. Sources: DSNY "Trash Revolution" announcements.
#   2023-08  food businesses (lots with a DOHMH-inspected restaurant)
#   2024-03  all businesses (mixed-use / commercial land use, or commercial floor area)
#   2024-11  homes with 1-9 units (rule effective 2024-11-12)
#   2025-06  10+ unit buildings in Manhattan CD 9 (West Harlem Empire Bins, 100% by June 2025)
# (2026-06 / 2026-09-08: official NYC Bin required / enforced for 1-9 units: same lots, no new coverage.)
BIN_RULES = ["2023-08", "2024-03", "2024-11", "2025-06"]
food_bbls = set(con.sql(f"""select distinct BBL from read_csv_auto('{RAW / "restaurant_inspections.csv"}',
    sample_size = 50000) where BBL is not null""").df().BBL.astype("int64"))
rules = pd.DataFrame({
    "2023-08": pluto.bbl.isin(food_bbls),
    "2024-03": pluto.landuse.isin([4, 5]) | (pluto.comarea > 0),
    "2024-11": pluto.unitsres.between(1, 9),
    "2025-06": (pluto.cb == 109) & (pluto.unitsres >= 10),
})
first = rules.idxmax(axis=1).where(rules.any(axis=1))      # earliest rule covering the lot
starts = pd.crosstab(pluto.h3, first).reindex(columns=BIN_RULES, fill_value=0)
starts = starts.div(pluto.groupby("h3").size(), axis=0)    # share of the cell's lots per start date
panel = panel.merge(starts.add_prefix("bin_").reset_index(), on="h3", how="left")
panel["share_binned"] = sum(np.where(panel.month >= d, panel[f"bin_{d}"].fillna(0), 0.0) for d in BIN_RULES)
panel["share_small_homes"] = panel["bin_2024-11"].fillna(0)  # for the before/after test
panel = panel.drop(columns=[f"bin_{d}" for d in BIN_RULES])

# Weather (citywide) and trash tonnage (community district)
noaa = pd.read_csv(RAW / "noaa_central_park_monthly.csv").rename(columns={"DATE": "month", "TAVG": "temp_c"})
panel = panel.merge(noaa[["month", "temp_c"]], on="month", how="left")
panel["month_of_year"] = panel.month.str[5:7].astype(int)

tons = pd.read_csv(RAW / "dsny_monthly_tonnage.csv")
tons["month"] = tons.MONTH.str.replace(" / ", "-")
tons["boro_cd"] = tons.BOROUGH_ID * 100 + pd.to_numeric(tons.COMMUNITYDISTRICT, errors="coerce")
tons = tons.groupby(["boro_cd", "month"]).REFUSETONSCOLLECTED.sum().rename("refuse_tons_cd").reset_index()
panel = panel.merge(static.reset_index()[["h3", "boro_cd"]], on="h3", how="left")
panel = panel.merge(tons, on=["boro_cd", "month"], how="left").drop(columns="boro_cd")

panel.to_parquet(PROCESSED / "panel.parquet", index=False)

# ---------------------------------------------------------------- checks
print(f"static: {static.shape[0]:,} cells x {static.shape[1]} cols")
print(static.describe().T[["count", "mean", "50%", "max"]].round(2).to_string())
print(f"\npanel: {len(panel):,} rows ({panel.month.min()} → {panel.month.max()})")
print(panel[["dob_permits_3m", "rest_04k_12m", "rest_08a_12m", "hpd_rodent_12m",
             "complaints_12m", "temp_c", "refuse_tons_cd"]].describe().T[["count", "mean", "max"]].round(2).to_string())
