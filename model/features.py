#!/usr/bin/env -S uv run --with duckdb --with lightgbm --with h3 --with shap --with scikit-learn --with pandas --with pyarrow --with numpy --with matplotlib python
"""features.py: one row per H3 r9 cell x month (2015-01 .. 2026-08) -> model/out/features.parquet.

Cell universe = every r9 cell that contains at least one PLUTO lot with building area or residential
units (all five boroughs by default; --scope manhattan restricts to lots with PLUTO borough MN).
Point tables are assigned to cells from their lat/lon with the h3 package; polygon sources (RMZ,
census tracts, parks) are rasterised with h3.geo_to_cells. Every trailing-window feature covers the
months strictly before the row's month, so nothing in the row leaks the month it describes.
"""
from __future__ import annotations

import argparse
import json
import re
import time

import duckdb
import h3
import numpy as np
import pandas as pd

from common import (COVID, H3_RES, MONTHS, MONTH_IDX, OUT, PARQUET, RAW, A_FEATURES, B_FEATURES, TARGETS,
                    Timer, check_leakage)

M = len(MONTHS)
BORO_DIGIT = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}


def T(name: str) -> str:
    return f"read_parquet('{PARQUET / (name + '.parquet')}')"


def to_h3(lat: np.ndarray, lon: np.ndarray) -> list:
    out = []
    for a, b in zip(lat, lon):
        out.append(h3.latlng_to_cell(a, b, H3_RES) if (a == a and b == b and 40.4 < a < 41.0 and -74.4 < b < -73.6) else None)
    return out


def month_str(ts: pd.Series) -> pd.Series:
    return ts.dt.strftime("%Y-%m")


def wkt_to_geojson(wkt: str) -> dict:
    """Minimal WKT POLYGON / MULTIPOLYGON parser -> GeoJSON-like dict (lon, lat order)."""
    multi = wkt.lstrip().upper().startswith("MULTI")
    s = wkt[wkt.index("("):]
    base = 1 if multi else 0
    polys, cur, depth, ring_start = [], None, 0, 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
            if depth == base + 1:
                cur = []
            if depth == base + 2:
                ring_start = i + 1
        elif ch == ")":
            if depth == base + 2:
                pts = [p.split() for p in s[ring_start:i].split(",")]
                cur.append([[float(x), float(y)] for x, y, *_ in pts])
            if depth == base + 1:
                polys.append(cur)
            depth -= 1
    return {"type": "MultiPolygon", "coordinates": polys}


def trailing(X: np.ndarray, k: int) -> np.ndarray:
    """out[:, t] = sum X[:, t-k .. t-1] (the k months strictly before t)."""
    cs = np.concatenate([np.zeros((X.shape[0], 1)), np.cumsum(X, axis=1)], axis=1)
    idx = np.arange(X.shape[1])
    return cs[:, idx] - cs[:, np.maximum(idx - k, 0)]


class Panel:
    def __init__(self, cells: list[str]):
        self.cells = cells
        self.idx = {c: i for i, c in enumerate(cells)}
        self.n = len(cells)

    def matrix(self, h3s, months, values=None) -> np.ndarray:
        """Dense (n_cells x n_months) sum of `values` (default 1) per (cell, month)."""
        X = np.zeros((self.n, M))
        ci = np.array([self.idx.get(c, -1) for c in h3s])
        mi = np.array([MONTH_IDX.get(m, -1) for m in months])
        ok = (ci >= 0) & (mi >= 0)
        v = np.ones(ok.sum()) if values is None else np.asarray(values)[ok]
        np.add.at(X, (ci[ok], mi[ok]), v)
        return X

    def counts(self, h3s) -> np.ndarray:
        X = np.zeros(self.n)
        ci = np.array([self.idx.get(c, -1) for c in h3s])
        np.add.at(X, ci[ci >= 0], 1)
        return X

    def ring1_sum(self, v: np.ndarray, include_self: bool = False) -> np.ndarray:
        out = np.zeros(self.n)
        for i, c in enumerate(self.cells):
            s = 0.0
            for nb in h3.grid_ring(c, 1):
                j = self.idx.get(nb)
                if j is not None:
                    s += v[j]
            out[i] = s + (v[i] if include_self else 0.0)
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["nyc", "manhattan"], default="nyc")
    args = ap.parse_args()
    t_all = time.time()
    con = duckdb.connect()

    # ---------------------------------------------------------------- PLUTO -> cell universe
    with Timer("pluto"):
        pl = con.execute(f"""
            select cast(bbl as bigint) bbl, borough, cd, landuse, lotarea, bldgarea, comarea, resarea, numbldgs,
                   numfloors, unitsres, unitstotal, yearbuilt, latitude, longitude
            from {T('pluto')} where latitude is not null and longitude is not null""").df()
        pl["h3"] = to_h3(pl.latitude.values, pl.longitude.values)
        pl = pl.dropna(subset=["h3"])
        for c in ("landuse", "lotarea", "bldgarea", "comarea", "resarea", "numbldgs", "numfloors", "unitsres",
                  "unitstotal", "yearbuilt", "cd"):
            pl[c] = pd.to_numeric(pl[c], errors="coerce").astype(float)
        yb = pl.yearbuilt.where(pl.yearbuilt > 0)
        pl["yb"] = yb
        pl["pre1940"] = ((yb > 0) & (yb < 1940)).astype(float)
        pl["vacant"] = (pl.landuse == 11).astype(float)
        pl["fam12"] = (pl.landuse == 1).astype(float)
        pl["mixed"] = (pl.landuse == 4).astype(float)
        g = pl.groupby("h3")
        cells_df = pd.DataFrame({
            "pluto_lots": g.size(),
            "pluto_res_units": g.unitsres.sum(),
            "pluto_units_total": g.unitstotal.sum(),
            "pluto_bldg_area": g.bldgarea.sum(),
            "pluto_lot_area": g.lotarea.sum(),
            "pluto_bldg_age_median": 2026 - g.yb.median(),
            "pluto_share_pre1940": g.pre1940.mean(),
            "pluto_vacant_share": g.vacant.mean(),
            "pluto_com_area_share": g.comarea.sum() / g.bldgarea.sum().replace(0, np.nan),
            "pluto_share_1_2fam": g.fam12.mean(),
            "pluto_mixed_share": g.mixed.mean(),
            "pluto_median_floors": g.numfloors.median(),
            "pluto_numbldgs": g.numbldgs.sum(),
            "cd": g.cd.agg(lambda s: s.mode().iloc[0] if s.notna().any() else np.nan),
            "borough": g.borough.agg(lambda s: s.mode().iloc[0]),
        })
        cells_df["pluto_far"] = cells_df.pluto_bldg_area / cells_df.pluto_lot_area.replace(0, np.nan)
        cells_df = cells_df[(cells_df.pluto_bldg_area > 0) | (cells_df.pluto_res_units > 0)]
        if args.scope == "manhattan":
            cells_df = cells_df[cells_df.borough == "MN"]
        cells_df = cells_df.sort_index()
        cells_df["cd"] = cells_df.cd.map(lambda v: f"{int(v):03d}" if v == v else None)
        P = Panel(list(cells_df.index))
        ll = np.array([h3.cell_to_latlng(c) for c in P.cells])
        cells_df["lat"], cells_df["lon"] = ll[:, 0], ll[:, 1]
        print(f"universe: {P.n} cells ({args.scope}), {pl.shape[0]} lots")

    # ---------------------------------------------------------------- RMZ (polygons -> cells)
    with Timer("rmz"):
        rmz_of = {}
        gj = RAW / "rmz.geojson"
        if gj.exists():
            for f in json.loads(gj.read_text())["features"]:
                for c in h3.geo_to_cells(f["geometry"], H3_RES):
                    rmz_of[c] = f["properties"]["Label"]
            src = "rmz.geojson"
        else:  # fallback: zone label carried by the inspections that fall in the cell
            z = con.execute(f"select latitude, longitude, zone from {T('initial_inspections_linked')} where zone is not null and latitude is not null").df()
            z["h3"] = to_h3(z.latitude.values, z.longitude.values)
            rmz_of = z.groupby("h3").zone.agg(lambda s: s.mode().iloc[0]).to_dict()
            src = "inspection zone labels (rmz.geojson absent)"
        cells_df["rmz"] = [rmz_of.get(c) for c in P.cells]
        rmz_names = sorted(set(v for v in rmz_of.values()))
        cells_df["rmz_id"] = cells_df.rmz.map({n: i + 1 for i, n in enumerate(rmz_names)}).fillna(0).astype(int)
        cells_df["rmz_flag"] = (cells_df.rmz_id > 0).astype(int)
        print(f"rmz from {src}: {int(cells_df.rmz_flag.sum())} cells in zone, zones={rmz_names}")

    # ---------------------------------------------------------------- census tracts -> ACS / CDBG
    with Timer("acs"):
        tr = con.execute(f"select the_geom, boroct2020 from {T('census_tracts_2020')}").df()
        tract_of, cents = {}, []
        for wkt, boroct in zip(tr.the_geom, tr.boroct2020):
            geo = wkt_to_geojson(wkt)
            for c in h3.geo_to_cells(geo, H3_RES):
                tract_of[c] = boroct
            ring = np.array(geo["coordinates"][0][0])
            cents.append((ring[:, 1].mean(), ring[:, 0].mean()))
        cents = np.array(cents)
        missing = [i for i, c in enumerate(P.cells) if c not in tract_of]
        for i in missing:  # cells whose centroid falls in no tract polygon: nearest tract centroid
            d = (cents[:, 0] - ll[i, 0]) ** 2 + ((cents[:, 1] - ll[i, 1]) * 0.76) ** 2
            tract_of[P.cells[i]] = tr.boroct2020.iloc[int(np.argmin(d))]
        cells_df["boroct"] = [int(tract_of[c]) for c in P.cells]
        acs = con.execute(f"select cast(boroct as bigint) boroct, median_hh_income, population, poverty_rate from {T('acs_tract_2023')}").df()
        cdbg = con.execute(f"select boroct, lomod_pct from {T('cdbg_tract_income')}").df()
        cells_df = cells_df.merge(acs, on="boroct", how="left").merge(cdbg, on="boroct", how="left")
        cells_df.index = P.cells
        cells_df = cells_df.rename(columns={"median_hh_income": "acs_median_income", "population": "acs_population",
                                            "poverty_rate": "acs_poverty_rate", "lomod_pct": "cdbg_lomod_pct"})
        cells_df["low_income_share"] = cells_df.acs_poverty_rate.where(cells_df.acs_poverty_rate.notna(), cells_df.cdbg_lomod_pct / 100.0)
        print(f"tracts: {len(missing)} cells matched by nearest centroid; ACS income null in "
              f"{int(cells_df.acs_median_income.isna().sum())} cells, lomod fallback null in {int(cells_df.cdbg_lomod_pct.isna().sum())}")

    # ---------------------------------------------------------------- parks (r11 raster -> share of cell)
    with Timer("parks"):
        pk = con.execute(f"select multipolygon from {T('parks_properties')} where multipolygon is not null").df()
        park_r11 = set()
        for wkt in pk.multipolygon:
            try:
                park_r11.update(h3.geo_to_cells(wkt_to_geojson(wkt), 11))
            except Exception:
                pass
        share_cache = {}

        def park_share(c):
            if c not in share_cache:
                kids = h3.cell_to_children(c, 11)
                share_cache[c] = sum(1 for k in kids if k in park_r11) / len(kids)
            return share_cache[c]

        cells_df["park_share"] = [park_share(c) for c in P.cells]
        cells_df["park_adjacent"] = [int(park_share(c) > 0 or any(park_share(n) > 0 for n in h3.grid_ring(c, 1))) for c in P.cells]

    # ---------------------------------------------------------------- street furniture
    with Timer("baskets+basins"):
        lb = con.execute(f"select latitude, longitude from {T('litter_baskets')} where latitude is not null").df()
        cb = con.execute(f"select latitude, longitude from {T('catch_basins')} where latitude is not null").df()
        cells_df["litter_baskets"] = P.counts(to_h3(lb.latitude.values, lb.longitude.values))
        cells_df["litter_baskets_ring1"] = P.ring1_sum(cells_df.litter_baskets.values)
        cells_df["catch_basins"] = P.counts(to_h3(cb.latitude.values, cb.longitude.values))

    # ---------------------------------------------------------------- monthly event matrices
    with Timer("restaurants"):
        rs = con.execute(f"""
            select camis, inspection_date, latitude, longitude,
                   max(case when violation_code in ('04K','04L','08A') then 1 else 0 end) vermin
            from {T('restaurant_inspections')}
            where inspection_date >= '2010-01-01' and latitude is not null
            group by 1,2,3,4""").df()
        rs["h3"] = to_h3(rs.latitude.values, rs.longitude.values)
        rs["m"] = month_str(rs.inspection_date)
        REST_V = P.matrix(rs.h3, rs.m, rs.vermin.values.astype(float))
        REST_I = P.matrix(rs.h3, rs.m)
        rest_count = rs.dropna(subset=["h3"]).groupby("h3").camis.nunique()
        cells_df["rest_count"] = rest_count.reindex(P.cells).fillna(0).values

    with Timer("dob"):
        db = con.execute(f"""select permit_type, issuance_date, try_cast(latitude as double) lat, try_cast(longitude as double) lon
                             from {T('dob_permits')} where issuance_date is not null""").df()
        db["h3"] = to_h3(db.lat.values, db.lon.values)
        db["m"] = month_str(db.issuance_date)
        NB = P.matrix(db.h3[db.permit_type == "NB"], db.m[db.permit_type == "NB"])
        DM = P.matrix(db.h3[db.permit_type == "DM"], db.m[db.permit_type == "DM"])

    with Timer("complaints"):
        cp = con.execute(f"select created_date, latitude, longitude from {T('complaints_rodent')} where latitude is not null").df()
        cp["h3"] = to_h3(cp.latitude.values, cp.longitude.values)
        cp["m"] = month_str(cp.created_date)
        C = P.matrix(cp.h3, cp.m)
        cbm = con.execute(f"select community_board, ym, n from {T('complaints_cb_month')} where not is_rodent").df()
        cbm = cbm[cbm.community_board.str.match(r"^\d\d ")]
        cbm["cd"] = cbm.community_board.map(lambda s: BORO_DIGIT.get(s[3:].strip(), "?") + s[:2])
        cbm["m"] = month_str(cbm.ym)
        cb_all = {(r.cd, r.m): float(r.n) for r in cbm.itertuples()}
        CB = np.full((P.n, M), np.nan)
        for i, cd in enumerate(cells_df.cd.values):
            for t, m in enumerate(MONTHS):
                v = cb_all.get((cd, m))
                if v is not None:
                    CB[i, t] = v

    with Timer("inspections"):
        ins = con.execute(f"""select inspection_date, latitude, longitude, active, l60 from {T('initial_inspections_linked')}
                              where latitude is not null""").df()
        ins["h3"] = to_h3(ins.latitude.values, ins.longitude.values)
        ins["m"] = month_str(ins.inspection_date)
        N_ALL = P.matrix(ins.h3, ins.m)
        A_ALL = P.matrix(ins.h3, ins.m, ins.active.values.astype(float))
        z = ins.l60 == 0
        N0 = P.matrix(ins.h3[z], ins.m[z])
        A0 = P.matrix(ins.h3[z], ins.m[z], ins.active.values[z].astype(float))
        msl = np.full((P.n, M), np.nan)
        last = np.full(P.n, -1.0)
        for t in range(M):
            msl[:, t] = np.where(last >= 0, t - last, np.nan)
            last = np.where(N_ALL[:, t] > 0, t, last)

    with Timer("noaa"):
        nz = con.execute(f"select month, tavg_f from {T('noaa_tavg')}").df()
        tav = dict(zip(month_str(nz.month), nz.tavg_f))
        allm = [str(p) for p in pd.period_range("2010-01", MONTHS[-1], freq="M")]
        series = np.array([tav.get(m, np.nan) for m in allm])
        off = allm.index(MONTHS[0])
        tavg = series[off:off + M]
        tavg_lag3 = np.array([np.nanmean(series[off + t - 3: off + t]) for t in range(M)])
        tavg_py = series[off - 12: off - 12 + M]

    # ---------------------------------------------------------------- assemble the long table
    with Timer("assemble"):
        insp12 = trailing(N_ALL, 12)
        act12 = trailing(A_ALL, 12)
        lag3 = trailing(C, 3)
        ring_lag3 = np.column_stack([P.ring1_sum(lag3[:, t]) for t in range(M)])
        mi = np.array([int(m[5:]) for m in MONTHS])
        yr = np.array([int(m[:4]) for m in MONTHS])
        covid = np.array([1 if COVID[0] <= m <= COVID[1] else 0 for m in MONTHS])
        rows = {
            "h3": np.repeat(P.cells, M),
            "month": np.tile(MONTHS, P.n),
            "cd": np.repeat(cells_df.cd.values, M),
            "rmz": np.repeat(cells_df.rmz.values, M),
            "borough": np.repeat(cells_df.borough.values, M),
            "lat": np.repeat(cells_df.lat.values, M),
            "lon": np.repeat(cells_df.lon.values, M),
            "complaints": C.ravel(),
            "n_initial_l60_0": N0.ravel(),
            "n_active_l60_0": A0.ravel(),
            "n_initial_all": N_ALL.ravel(),
            "n_active_all": A_ALL.ravel(),
        }
        static = [f for f in B_FEATURES if f in cells_df.columns]
        for f in static:
            rows[f] = np.repeat(cells_df[f].values.astype(float), M)
        dyn = {
            "rest_vermin_3m": trailing(REST_V, 3), "rest_vermin_12m": trailing(REST_V, 12), "rest_visits_12m": trailing(REST_I, 12),
            "dob_nb_6m": trailing(NB, 6), "dob_dm_6m": trailing(DM, 6), "dob_nb_12m": trailing(NB, 12), "dob_dm_12m": trailing(DM, 12),
            "tavg_f": np.tile(tavg, (P.n, 1)), "tavg_lag3": np.tile(tavg_lag3, (P.n, 1)), "tavg_prev_year": np.tile(tavg_py, (P.n, 1)),
            "month_of_year": np.tile(mi, (P.n, 1)), "year": np.tile(yr, (P.n, 1)), "covid": np.tile(covid, (P.n, 1)),
            "complaints_lag1": trailing(C, 1), "complaints_lag3": lag3, "complaints_lag12": trailing(C, 12),
            "complaints_ring1_lag3": ring_lag3,
            "cb_all_complaints_lag1": np.concatenate([np.full((P.n, 1), np.nan), CB[:, :-1]], axis=1),
            "insp_lag12": insp12,
            "insp_active_rate_lag12": np.where(insp12 > 0, act12 / np.maximum(insp12, 1), np.nan),
            "months_since_last_insp": np.minimum(msl, 60),
        }
        for k, v in dyn.items():
            rows[k] = v.astype(float).ravel()
        df = pd.DataFrame(rows)
        missing = [f for f in A_FEATURES if f not in df.columns]
        assert not missing, f"features not built: {missing}"
        check_leakage(B_FEATURES)
        df.to_parquet(OUT / "features.parquet", index=False)
        cells_df[["lat", "lon", "cd", "rmz", "borough", "boroct"]].rename_axis("h3").reset_index().to_parquet(OUT / "cells_static.parquet", index=False)

    print(f"\nfeatures.parquet: {df.shape[0]} rows x {df.shape[1]} cols, {P.n} cells x {M} months, scope={args.scope}")
    print("targets: complaints sum=%d, l60=0 initial inspections=%d, active among them=%d" %
          (df.complaints.sum(), df.n_initial_l60_0.sum(), df.n_active_l60_0.sum()))
    nulls = df[A_FEATURES + TARGETS].isna().mean().sort_values(ascending=False)
    print("null rates (non-zero only):")
    for k, v in nulls[nulls > 0].items():
        print(f"  {k:28s} {v:.3f}")
    print("means:")
    print(df[A_FEATURES].mean().round(3).to_string())
    print(f"[features total] {time.time() - t_all:.1f}s")


if __name__ == "__main__":
    main()
