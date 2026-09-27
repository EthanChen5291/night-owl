"""Historical averages identify their observation unit without changing the calculation."""
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard_data import run_query
from main import create_app

REPO = Path(__file__).resolve().parents[2]


def test_mean_rates_are_not_presented_as_pooled_inspection_shares(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / 'events.jsonl')) as client:
        store = client.app.state.store
        history = {'window': ['2025-01', '2025-12'], 'zip_years': [
            {'zip': '10001', 'year': 2025, 'income_band': 'Q5 highest income',
             'active_rate': 1.0, 'n_active': 1, 'n_inspections': 1},
            {'zip': '10002', 'year': 2025, 'income_band': 'Q5 highest income',
             'active_rate': 0.0, 'n_active': 0, 'n_inspections': 99}]}
        monkeypatch.setattr(store, 'history', lambda: (history, Path('history.json')))
        query = {'dataset': 'zip_years', 'metrics': ['active_rate'], 'aggregation': 'mean', 'group_by': 'year'}
        result = run_query(store, query)
        assert result['rows'] == [{'year': 2025, 'active_rate': 0.5}]
        assert result['columns'][1]['label'] == 'Mean inspection-positive share per ZIP-year'
        assert 'not the pooled share of inspections' in result['source']['notes'][-1]
        pivot = run_query(store, {**query, 'split_by': 'income_band'})
        assert pivot['rows'] == [{'year': 2025, 'Q5 highest income': 0.5}]
        assert pivot['columns'][1]['label'] == 'Q5 highest income'
        assert 'each ZIP-year' in pivot['source']['notes'][-1]
        raw = run_query(store, {**query, 'aggregation': 'raw'})
        assert raw['columns'][1]['label'] == 'Share of inspections finding rat activity'
        assert all('Means give' not in note for note in raw['source']['notes'])


def test_mean_income_and_eligible_zip_coverage_are_disclosed(tmp_path):
    with TestClient(create_app(data_dir=REPO, events_file=tmp_path / 'events.jsonl')) as client:
        result = client.post('/dashboards/query', json={
            'dataset': 'zips', 'metrics': ['median_income'], 'aggregation': 'mean', 'group_by': 'borough'}).json()
        assert result['columns'][1]['label'] == 'Mean area median household income (ACS) per ZIP area'
        assert any('at least 1,000 ACS residents' in note and '50 rodent complaints' in note
                   for note in result['source']['notes'])
