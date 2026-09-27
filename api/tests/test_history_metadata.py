"""History period labels disclose the ZIP annual boundary and frozen export format."""
import importlib.util
import json
from pathlib import Path

from dashboard_data import catalog


REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fetch_history", REPO / "data" / "fetch_history.py")
fetch_history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_history)


class HistoryStore:
    def __init__(self, history):
        self.data = history

    def history(self):
        return self.data, REPO / "model" / "out" / "history.json"


def test_catalog_describes_zip_calendar_year_periods_for_frozen_export():
    history = json.loads((REPO / "model" / "out" / "history.json").read_text())
    history.pop("zip_periods", None)  # exercise exports written before this field existed

    result = catalog(HistoryStore(history))
    assert result["history"]["periods"]["COVID"] == "2020-03 to 2021-12"
    assert result["history"]["zip_periods"]["COVID"] == "2020 to 2021 (includes January–February 2020)"
    assert result["history"]["zip_periods"]["after COVID"] == "2022 to 2026 (2026 partial through 2026-08)"
    assert "March 2020 boundary" in " ".join(result["datasets"]["zip_years"]["notes"])


def test_builder_adds_zip_period_metadata_without_network(monkeypatch):
    def complaints(select_time, extra_group, last_month):
        if "incident_zip" in extra_group:
            return [{"t": 2020, "incident_zip": "10001", "borough": "Manhattan", "descriptor": "Rat Sighting", "n": 60}]
        return [{"t": "2020-01-01T00:00:00", "borough": "Manhattan", "descriptor": "Rat Sighting", "n": 60}]

    def census(geo_ids):
        return {geo: (100000, 10000, "ACS test release") for geo in geo_ids}

    monkeypatch.setattr(fetch_history, "complaint_rows", complaints)
    monkeypatch.setattr(fetch_history, "inspection_rows", lambda *_args: [])
    monkeypatch.setattr(fetch_history, "census", census)
    monkeypatch.setattr(fetch_history, "neighborhoods", lambda: {})

    result = fetch_history.build("2026-08")
    assert result["zip_periods"]["COVID"] == "2020 to 2021 (includes January–February 2020)"
    assert result["zip_periods"]["after COVID"] == "2022 to 2026 (2026 partial through 2026-08)"
    assert next(row for row in result["zip_years"] if row["year"] == 2020)["period"] == "COVID"
    assert catalog(HistoryStore(result))["history"]["zip_periods"] == result["zip_periods"]
