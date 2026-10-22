import hashlib
import json

import pytest

from app.agriculture import api
from app.agriculture.forecasting import MODELS, backtest, predict
from app.agriculture.ingestion import DATA, build_dataset, parse_row


def test_ingestion_reconciles_sources_without_duplicates_or_imputation():
    before = hashlib.sha256((DATA / "observations.json").read_bytes()).hexdigest()
    report = build_dataset()
    assert hashlib.sha256((DATA / "observations.json").read_bytes()).hexdigest() == before
    assert report["validated_counts"] == {"production":39,"area":40,"price":40}
    assert report["sanity_checks_passed"]
    assert len(report["documents"]) == 37
    assert all(d["status"] == "parsed" for d in report["documents"])
    rows = json.loads((DATA / "observations.json").read_text())
    assert len(rows) == len({r["id"] for r in rows}) == 120
    disputed = next(r for r in rows if r["year"] == 2016 and r["quarter"] == 3 and r["measurement"] == "production")
    assert disputed["value"] is None and disputed["status"] == "quarantined"
    assert {e["value"] for e in disputed["evidence"]} == {2525,2998}
    assert all(r["unit"] == "tonnes" for r in rows if r["measurement"] == "production")
    assert all(r["crop"] == "iceberg_lettuce" for r in rows)


@pytest.mark.parametrize("row", ["OTHER LETTUCE 1 2 3 4 5", "ICEBURG LETTUCE 1 2 - 4 5", "ICEBURG LETTUCE 1,23 2 3 4 5", "ICEBURG LETTUCE 1 2 3 4"])
def test_unmapped_missing_or_malformed_cells_fail_closed(row):
    with pytest.raises(ValueError):
        parse_row(row,5)


def test_backtest_has_identical_periods_and_reproducible_metrics():
    artifact = json.loads((DATA / "intelligence.json").read_text())
    result = backtest(artifact["series"])
    assert result == artifact["experiment"]
    assert result["metrics"]["all"]["seasonal_naive"]["mae_tonnes"] == pytest.approx(595.15)
    assert result["metrics"]["all"]["ridge_lags"]["mae_tonnes"] == pytest.approx(498.960586331)
    assert {m["n"] for m in result["metrics"]["all"].values()} == {20}
    assert result["forecasts"][0]["period"] == "2021 Q1"
    assert result["forecasts"][-1]["period"] == "2025 Q4"
    assert result["selected_model"] == "ridge_lags"


def test_future_changes_cannot_affect_earlier_predictions():
    series = json.loads((DATA / "intelligence.json").read_text())["series"]
    original = backtest(series)
    altered = [dict(r) for r in series]
    for row in altered:
        if row["period"] >= "2024 Q1":
            row["production_tonnes"] = 99999
    changed = backtest(altered)
    assert original["forecasts"][:12] == changed["forecasts"][:12]
    # Even the first changed target's prediction cannot change from its own value.
    assert original["forecasts"][12]["predictions"] == changed["forecasts"][12]["predictions"]


def test_missing_quarter_does_not_shift_seasonal_lag_and_short_history_unavailable():
    assert predict([100,None,300,400,500], "seasonal_naive") is None
    series = [dict(period=f"2025 Q{i+1}", year=2025,quarter=i+1,production_tonnes=v) for i,v in enumerate([100,200,300,400])]
    result = backtest(series)
    assert result["forecast"]["status"] == "unavailable"
    assert result["forecast"]["value_tonnes"] is None
    assert result["selected_model"] == "seasonal_naive"
    assert all(result["metrics"]["all"][m]["mae_tonnes"] is None for m in MODELS)


def test_candidate_that_cannot_beat_seasonality_keeps_seasonal_reference():
    # Test-only perfectly repeating seasonal process; these are not source data.
    series = [dict(period=f"{2016+i//4} Q{i%4+1}", year=2016+i//4,
                   quarter=i%4+1,production_tonnes=float([100,200,300,400][i%4]))
              for i in range(40)]
    result = backtest(series)
    assert result["metrics"]["all"]["seasonal_naive"]["mae_tonnes"] == 0
    assert result["candidate_qualifies"] is False
    assert result["selected_model"] == "seasonal_naive"
    assert result["forecast"]["model"] == "seasonal_naive"


def test_read_only_endpoint_and_unavailable_states(client, tmp_path, monkeypatch):
    response = client.get("/agricultural-intelligence")
    assert response.status_code == 200
    assert response.json()["quality"]["validated_counts"]["production"] == 39
    assert client.get("/agricultural-intelligence?crop=lettuce_chicory").status_code == 404
    assert client.post("/agricultural-intelligence", json={}).status_code == 405
    monkeypatch.setattr(api, "ARTIFACT", tmp_path / "missing.json")
    assert client.get("/agricultural-intelligence").status_code == 503
    api.ARTIFACT.write_text("{bad json")
    assert client.get("/agricultural-intelligence").status_code == 503
    api.ARTIFACT.write_text("[]")
    assert client.get("/agricultural-intelligence").status_code == 503


def test_endpoint_requires_existing_authentication(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("ALLOW_INSECURE_DEMO_AUTH", raising=False)
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get("/agricultural-intelligence").status_code == 401
        assert unauthenticated.get("/agricultural-intelligence/faostat").status_code == 401


def test_faostat_import_is_annual_unmapped_idempotent_and_missing_is_not_zero(tmp_path):
    from app.agriculture.faostat import import_annual_csv
    path = tmp_path / "test-only-faostat.csv"
    path.write_text('Area,Item Code,Item,Element,Year,Unit,Value,Flag\n'
                    'Jamaica,999,Test aggregate,Production,2020,t,123,E\n'
                    'Jamaica,999,Test aggregate,Production,2020,t,123,E\n'
                    'Jamaica,999,Test aggregate,Production,2021,t,,E\n'
                    'Elsewhere,999,Test aggregate,Production,2020,t,99,E\n')
    result = import_annual_csv(path,"https://www.fao.org/faostat/en/#data/QCL","QCL")
    assert len(result["records"]) == 1 and len(result["rejected"]) == 1
    row = result["records"][0]
    assert row["frequency"] == "annual" and row["quarter"] is None
    assert row["mapped_ministry_crop"] is None
    assert result == import_annual_csv(path,"https://www.fao.org/faostat/en/#data/QCL","QCL")
    with pytest.raises(ValueError):
        import_annual_csv(path,"https://unofficial.example/data","QCL")
