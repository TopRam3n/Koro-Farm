import json

import pytest

from src.backend.app.agriculture import api
from src.backend.app.agriculture.forecasting import backtest
from src.backend.app.agriculture.validation import training_content_hash, validate_training_data
from src.backend.scripts.train_agricultural_forecast import DATA


def test_reordered_training_records_preserve_identity():
    rows = json.loads((DATA / 'observations.json').read_text())
    quality = json.loads((DATA / 'quality-report.json').read_text())
    validate_training_data(list(reversed(rows)), quality)


def test_incomplete_valid_json_artifact_is_503(client, tmp_path, monkeypatch):
    path = tmp_path / 'incomplete.json'
    path.write_text('{"schema_version":1,"series":[]}')
    monkeypatch.setattr(api, 'ARTIFACT', path)
    assert client.get('/agricultural-intelligence').status_code == 503


def test_empty_history_is_explicitly_unavailable():
    result = backtest([])
    assert result['forecast']['status'] == 'unavailable'
    assert result['forecast']['value_tonnes'] is None
    assert result['forecast']['period'] is None
    assert result['forecast']['data_cutoff'] is None
    assert result['forecasts'] == []


@pytest.mark.parametrize('field', ['experiment', 'quality', 'sources', 'annual_context'])
def test_missing_required_sections_are_503(client, tmp_path, monkeypatch, field):
    data = json.loads(api.ARTIFACT.read_text())
    del data[field]
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(data))
    monkeypatch.setattr(api, 'ARTIFACT', path)
    assert client.get('/agricultural-intelligence').status_code == 503


@pytest.mark.parametrize('field,value', [('value', 999), ('period', '2020 Q2'), ('unit', 'kg')])
def test_single_observation_stale_manifest_rejected(field, value):
    rows = [json.loads((DATA / 'observations.json').read_text())[0]]
    quality = json.loads((DATA / 'quality-report.json').read_text())
    quality['dataset_version'] = training_content_hash(rows)
    rows[0][field] = value
    with pytest.raises(ValueError, match='Dataset version mismatch'):
        validate_training_data(rows, quality)


def test_source_identity_change_invalidates_fingerprint():
    rows = [json.loads((DATA / 'observations.json').read_text())[0]]
    expected = training_content_hash(rows)
    rows[0]['evidence'][0]['source_sha256'] = 'a' * 64
    assert training_content_hash(rows) != expected
    quality = json.loads((DATA / 'quality-report.json').read_text())
    quality['dataset_version'] = expected
    with pytest.raises(ValueError, match='Dataset version mismatch'):
        validate_training_data(rows, quality)


def test_missing_source_metadata_rejected_even_with_matching_hash():
    rows = json.loads((DATA / 'observations.json').read_text())
    quality = json.loads((DATA / 'quality-report.json').read_text())
    del rows[0]['evidence']
    quality['dataset_version'] = training_content_hash(rows)
    with pytest.raises(ValueError, match='Missing source identity'):
        validate_training_data(rows, quality)


@pytest.mark.parametrize('length', [1, 3, 4])
def test_short_histories_are_unavailable(length):
    series = json.loads((DATA / 'intelligence.json').read_text())['series'][:length]
    result = backtest(series)
    assert result['forecast']['status'] == 'unavailable'
    assert result['forecast']['value_tonnes'] is None
    assert result['forecast']['data_cutoff'] == series[-1]['period']


def test_omitted_quarter_fails_closed():
    series = json.loads((DATA / 'intelligence.json').read_text())['series'][:5]
    del series[2]
    with pytest.raises(ValueError, match='Missing calendar quarters'):
        backtest(series)


@pytest.mark.parametrize('path,value', [
    (('experiment','forecast','value_tonnes'), None),
    (('experiment','metrics','all','ridge_lags','mae_tonnes'), 'unknown'),
    (('experiment','metrics','all','ridge_lags','bias_tonnes'), float('nan')),
    (('annual_context','validation','items'), None),
    (('quality','conflicts'), {}),
])
def test_malformed_nested_artifact_is_503(client, tmp_path, monkeypatch, path, value):
    data = json.loads(api.ARTIFACT.read_text())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    file = tmp_path / 'invalid.json'
    file.write_text(json.dumps(data))
    monkeypatch.setattr(api, 'ARTIFACT', file)
    assert client.get('/agricultural-intelligence').status_code == 503


def test_empty_history_artifact_serves_explicit_unavailable_forecast(client, tmp_path, monkeypatch):
    data = json.loads(api.ARTIFACT.read_text())
    data['series'] = []
    data['experiment'] = backtest([])
    path = tmp_path / 'empty.json'
    path.write_text(json.dumps(data))
    monkeypatch.setattr(api, 'ARTIFACT', path)
    response = client.get('/agricultural-intelligence')
    assert response.status_code == 200
    assert response.json()['experiment']['forecast']['status'] == 'unavailable'


def test_preserved_snapshot_provenance_verification_is_read_only():
    from src.backend.scripts.verify_saved_agricultural_provenance import verify
    before = (DATA / 'intelligence.json').read_bytes()
    result = verify()
    assert result['status'] == 'snapshot_consistency_verified'
    assert result['source_pdfs'] == 37
    assert (DATA / 'intelligence.json').read_bytes() == before


def test_omitted_artifact_quarter_is_503(client, tmp_path, monkeypatch):
    data = json.loads(api.ARTIFACT.read_text())
    del data['series'][2]
    path = tmp_path / 'gap.json'
    path.write_text(json.dumps(data))
    monkeypatch.setattr(api, 'ARTIFACT', path)
    assert client.get('/agricultural-intelligence').status_code == 503
