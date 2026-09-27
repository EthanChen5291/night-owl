"""Dashboard data comes from the same Store as the map and never invents units or dates."""
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from dashboard_data import run_query
from main import create_app

REPO = Path(__file__).resolve().parents[2]


def query(dataset, metrics, aggregation, **extra):
    return {"dataset": dataset, "metrics": metrics, "aggregation": aggregation, **extra}


def test_catalog_and_borough_means(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        catalog = client.get("/dashboards/catalog").json()
        assert catalog["datasets"]["cells"]["metrics"]["score_b"]["unit"] == "probability"
        assert "score_b" not in catalog["datasets"]["cells"]["sum_metrics"]
        result = client.post("/dashboards/query", json=query("cells", ["score_b"], "mean", group_by="borough")).json()
        rows = {row["borough"]: row["score_b"] for row in result["rows"]}
        assert result["source"]["as_of"] == "2026-09"
        assert result["total_rows"] == 5
        assert abs(rows["Bronx"] - 0.042144) < 1e-6
        assert abs(rows["Manhattan"] - 0.062184) < 1e-6
        assert result["columns"][1]["unit"] == "probability"


def test_invalid_metric_sum_group_and_date_are_rejected(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        bad = [query("cells", ["score_b"], "sum"),
               query("cells", ["score_b"], "mean", group_by="month"),
               query("cells", ["score_b"], "mean", start="2025-01"),
               query("backtest", ["precision_silent"], "mean", borough="Bronx"),
               query("backtest", ["precision_silent"], "mean", start="2026-13"),
               query("events", ["records"], "count", start="2026-09-28", end="2026-09-27"),
               query("cells", ["score_b"], "mean", limit=True),
               query([], ["score_b"], "mean"),
               query("cells", ["score_b"], "mean", sort_by=[])]
        for item in bad:
            response = client.post("/dashboards/query", json=item)
            assert response.status_code == 400, item


def test_event_query_omits_crops_and_reports_retained_window(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        h3 = client.get("/cells").json()["cells"][0]["h3"]
        event = {"node_id": "dash-test", "h3": h3, "ts": "2026-09-27T12:00:00.000Z", "class": "rat",
                 "conf": 0.95, "n_hits": 3, "bbox": [0.1, 0.2, 0.3, 0.4], "crop_b64": "SECRET_IMAGE", "fw": "test"}
        assert client.post("/event", json=event).status_code == 200
        result = client.post("/dashboards/query", json=query("events", ["conf", "n_hits"], "raw", group_by="day",
                                                              start="2026-09-27", end="2026-09-27")).json()
        assert result["rows"] == [{"day": "2026-09-27", "conf": 0.95, "n_hits": 3}]
        assert "SECRET_IMAGE" not in str(result)
        assert "not an all-time total" in result["source"]["notes"][-1]
        empty = client.post("/dashboards/query", json=query("events", ["records"], "count",
                                                             start="2026-09-28")).json()
        assert empty["rows"] == [{"scope": "All rows", "records": 0}]
        assert "group_by" not in empty["query"]


def test_nonfinite_model_values_become_null(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        store = client.app.state.store
        original = store.cells

        def cells_with_nonfinite(month=None):
            data, path = original(month)
            data["cells"] = [{**data["cells"][0], "score_b": float("nan"), "borough": "Bronx"}]
            return data, path

        monkeypatch.setattr(store, "cells", cells_with_nonfinite)
        raw = run_query(store, query("cells", ["score_b"], "raw", group_by="borough"))
        mean = run_query(store, query("cells", ["score_b"], "mean", group_by="borough"))
        assert raw["rows"] == [{"borough": "Bronx", "score_b": None}]
        assert mean["rows"] == [{"borough": "Bronx", "score_b": None}]


def test_render_validates_chart_fields_units_and_empty_metric(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        base = {"title": "Borough risk", "description": "Current snapshot", "cards": [{
            "id": "risk", "title": "Mean risk", "kind": "bar",
            "query": query("cells", ["score_b"], "mean", group_by="borough"),
            "x": "borough", "y": ["score_b"]}]}
        artifact = client.post("/dashboards/render", json={"spec": base, "version": 2}).json()
        assert artifact["version"] == 2
        assert artifact["results"]["risk"]["total_rows"] == 5
        bad_x = {**base, "cards": [{**base["cards"][0], "x": "month"}]}
        assert client.post("/dashboards/render", json={"spec": bad_x}).status_code == 400
        bad_units = {**base, "cards": [{**base["cards"][0], "query": query("cells", ["score_b", "n_inspections"], "mean", group_by="borough"),
                                         "y": ["score_b", "n_inspections"]}]}
        assert client.post("/dashboards/render", json={"spec": bad_units}).status_code == 400
        empty_metric = {**base, "cards": [{**base["cards"][0], "kind": "metric",
                                            "query": query("events", ["records"], "count", group_by="day"),
                                            "x": "day", "y": ["records"]}]}
        assert client.post("/dashboards/render", json={"spec": empty_metric}).status_code == 400


@pytest.mark.parametrize("x,y", [([], ["score_b"]), ("borough", [{}]), ("borough", [[]])])
def test_render_reports_malformed_card_columns_as_client_error(tmp_path, x, y):
    spec = {"title": "Borough risk", "description": "Current snapshot", "cards": [{
        "id": "risk", "title": "Mean risk", "kind": "bar",
        "query": query("cells", ["score_b"], "mean", group_by="borough"),
        "x": x, "y": y}]}
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        response = client.post("/dashboards/render", json={"spec": spec})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "card 'risk'" in detail
    assert "returned borough, score_b" in detail


def test_history_datasets_filter_pivot_and_rank(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        catalog = client.get("/dashboards/catalog").json()
        assert catalog["datasets"]["borough_months"]["date_format"] == "YYYY-MM"
        assert catalog["datasets"]["zip_years"]["date_format"] == "YYYY"
        assert catalog["history"]["periods"]["COVID"] == "2020-03 to 2021-12"
        assert len(catalog["history"]["income_bands"]) == 5
        # Two boroughs on one chart: split_by pivots the metric into one column per borough.
        pivot = client.post("/dashboards/query", json=query("borough_months", ["complaints_per_100k"], "mean", group_by="year",
                                                             split_by="borough", filters={"borough": ["bronx", "Manhattan"]},
                                                             start="2019-01", end="2021-12")).json()
        assert [column["key"] for column in pivot["columns"]] == ["year", "Bronx", "Manhattan"]
        assert [row["year"] for row in pivot["rows"]] == [2019, 2020, 2021]
        assert all(row["Bronx"] > 0 and row["Manhattan"] > 0 for row in pivot["rows"])
        assert pivot["source"]["kind"] == "history" and pivot["source"]["as_of"] >= "2026-08"
        # COVID periods: monthly means per period for one borough, via the legacy borough field.
        periods = client.post("/dashboards/query", json=query("borough_months", ["n_complaints"], "mean", group_by="period", borough="Bronx")).json()
        assert {row["period"] for row in periods["rows"]} == {"before COVID", "COVID", "after COVID"}
        # Rankings: the ten highest-income ZIP code areas with complaints before and after COVID.
        richest = client.post("/dashboards/query", json=query("zips", ["median_income", "complaints_per_year_pre", "complaints_per_year_post"], "raw",
                                                               group_by="neighborhood", sort_by="median_income", direction="desc", limit=10)).json()
        assert len(richest["rows"]) == 10 and richest["total_rows"] > 100
        assert richest["rows"][0]["median_income"] >= richest["rows"][-1]["median_income"]
        # Income bands over years, with year strings and numbers both accepted as filter values.
        band = client.post("/dashboards/query", json=query("zip_years", ["active_rate"], "mean", group_by="year",
                                                            filters={"income_band": "Q5 highest income", "year": ["2019", 2023]})).json()
        assert [row["year"] for row in band["rows"]] == [2019, 2023]
        spec = {"title": "COVID", "description": "Complaint history", "cards": [
            {"id": "trend", "title": "Bronx vs Manhattan", "kind": "line", "x": "month", "y": ["Bronx", "Manhattan"],
             "query": query("borough_months", ["complaints_per_100k"], "mean", group_by="month", split_by="borough",
                            filters={"borough": ["Bronx", "Manhattan"]}, start="2018-01")},
            {"id": "rich", "title": "Richest areas", "kind": "bar", "x": "neighborhood", "y": ["complaints_per_year_pre", "complaints_per_year_post"],
             "query": richest["query"]}]}
        artifact = client.post("/dashboards/render", json={"spec": spec}).json()
        assert artifact["results"]["trend"]["columns"][1]["key"] == "Bronx"
        assert artifact["results"]["rich"]["total_rows"] > 100 and len(artifact["results"]["rich"]["rows"]) == 10


def test_history_query_rejections(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        bad = [query("zips", ["median_income"], "raw", filters={"month": "2020-01"}),
               query("zip_years", ["n_complaints"], "sum", start="2019-01"),
               query("borough_months", ["n_complaints"], "sum", start="2019"),
               query("borough_months", ["n_complaints"], "sum", group_by="borough", split_by="borough"),
               query("borough_months", ["n_complaints", "n_active"], "sum", group_by="month", split_by="borough"),
               query("borough_months", ["n_complaints"], "raw", group_by="month", split_by="borough"),
               query("zip_years", ["n_complaints"], "sum", group_by="year", split_by="zip"),
               query("borough_months", ["n_complaints"], "sum", filters={"borough": [True]}),
               query("borough_months", ["n_complaints"], "sum", filters={"borough": ["Bronx"] * 21}),
               query("zips", ["median_income"], "sum"),
               query("backtest", ["precision_silent"], "mean", filters={"borough": "Bronx"})]
        for item in bad:
            response = client.post("/dashboards/query", json=item)
            assert response.status_code == 400, item


def test_inspection_history_query_exposes_exact_chart_columns(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        result = client.post("/dashboards/query", json=query(
            "borough_months", ["n_inspections", "n_active"], "sum", group_by="month",
            start="2025-01", end="2025-03")).json()
        assert [column["key"] for column in result["columns"]] == ["month", "n_inspections", "n_active"]
        assert result["chart_schema"]["suggested_x"] == "month"
        assert result["chart_schema"]["numeric_y"] == ["n_inspections", "n_active"]
        assert len(result["rows"]) == 3


def test_sort_rejection_keeps_requested_measure_out_of_result(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / "events.jsonl")) as client:
        response = client.post("/dashboards/query", json=query(
            "zips", ["complaints_per_year_post"], "raw", group_by="neighborhood",
            sort_by="median_income", direction="desc", limit=10))
        assert response.status_code == 400
        assert "add the field to metrics" in response.json()["detail"]
        fixed = client.post("/dashboards/query", json=query(
            "zips", ["complaints_per_year_post", "median_income"], "raw", group_by="neighborhood",
            sort_by="median_income", direction="desc", limit=10)).json()
        assert fixed["chart_schema"]["numeric_y"] == ["complaints_per_year_post", "median_income"]
