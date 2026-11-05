"""Forecasting baselines, features, backtesting and evidence-grounded answers (R1 WP5 preparation).

Synthetic series and a fake provider client only: no model provider is called and no statistic is real.
"""
import json
from datetime import date

import pytest

from src.backend.app.agriculture import evidence as ev
from src.backend.app.agriculture.forecasting import BASELINES, Drift, LastValue, MovingAverage, SeasonalLastValue, backtest, build_features

SEASONAL = [10, 20, 30, 40, 12, 22, 32, 42, 14, 24, 34, 44, 16, 26, 36, 46]  # synthetic quarterly pattern with growth


def test_baselines_are_deterministic_non_negative_and_their_intervals_contain_the_point() -> None:
    for name, model in BASELINES.items():
        first = model().fit(SEASONAL).predict(4)
        second = model().fit(SEASONAL).predict(4)
        assert first == second, name
        for point in first:
            assert point.point >= 0
            assert point.lower is None or point.lower <= point.point <= point.upper
    assert [p.point for p in LastValue().fit([5, 7]).predict(2)] == [7, 7]
    assert [p.point for p in SeasonalLastValue(season=4).fit(SEASONAL).predict(4)] == [16, 26, 36, 46]
    assert MovingAverage(window=2).fit([2, 4, 6]).predict(1)[0].point == 5
    assert Drift().fit([1, 2, 3]).predict(2)[1].point == 5
    assert Drift().fit([30, 20, 10]).predict(3)[2].point == 0  # never forecast a negative quantity
    with pytest.raises(ValueError):
        LastValue().fit([])


def test_features_use_only_earlier_periods() -> None:
    periods = [date(2020 + i, 1, 1) for i in range(5)]
    rows = build_features(periods, [10, 20, 30, 40, 50])
    assert rows[0]["lag_1"] is None and rows[0]["rolling_mean_3"] is None
    assert rows[3]["lag_1"] == 30 and rows[3]["lag_3"] == 10 and rows[3]["rolling_mean_3"] == 20
    assert rows[2]["change_from_previous"] == 1.0  # (20 - 10) / 10, both before the period
    assert [row["lag_1"] for row in rows] == [None, 10, 20, 30, 40]  # each lag is the previous period, never the target itself
    with pytest.raises(ValueError):
        build_features(periods, [1, 2])


def test_rolling_origin_backtest_prefers_the_seasonal_baseline_on_seasonal_data() -> None:
    models = {"last_value": LastValue(), "seasonal": SeasonalLastValue(season=4), "moving_average": MovingAverage(window=4)}
    result = backtest(SEASONAL, models, min_train=8, horizon=1)
    assert result["best_by_mae"] == "seasonal"
    assert result["models"]["seasonal"]["mase"] < result["models"]["last_value"]["mase"]
    assert result["models"]["seasonal"]["mae"] == 2.0  # each quarter is exactly 2 above the same quarter a year earlier
    assert result["models"]["seasonal"]["forecasts"] == len(SEASONAL) - 8
    with pytest.raises(ValueError, match="need at least"):
        backtest(SEASONAL[:5], models, min_train=8)


def _evidence(status="APPROVED"):
    return [ev.Evidence("E1", "Ginger, Jamaica: PRODUCTION for year starting 2022-01-01 was 124.5 TONNE (final, revision 1)", "124.5", "TONNE",
                        {"source": "FAOSTAT", "licence_review_status": status}),
            ev.Evidence("E2", "Ginger, Jamaica: PRODUCTION for year starting 2023-01-01 was 130 TONNE (final, revision 1)", "130", "TONNE",
                        {"source": "FAOSTAT", "licence_review_status": status})]


ENABLED = {"APP_ENV": "development", "AGENT_MODEL_PROVIDER": "nebius", "AGRI_LLM_ENABLED": "true"}


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def complete(self, system, user, schema):
        self.calls.append((system, user, schema))
        return type("Completion", (), {"text": json.dumps(self.answer)})()


def test_answers_are_used_only_when_every_figure_matches_cited_evidence() -> None:
    good = {"answer": "Production rose from 124.5 tonnes in 2022 to 130 tonnes in 2023.", "citations": ["E1", "E2"],
            "figures": [{"value": "124.5", "evidence_id": "E1"}, {"value": "130", "evidence_id": "E2"}], "insufficient_evidence": False}
    client = FakeClient(good)
    result = ev.answer("How did ginger production change?", _evidence(), client, ENABLED)
    assert result.used_model and result.citations == ["E1", "E2"]
    system, user, schema = client.calls[0]
    assert "only the numbered evidence" in system and schema == ev.ANSWER_SCHEMA and "E2" in user

    invented = {**good, "answer": "Production will reach 150 tonnes in 2024.", "figures": [{"value": "150", "evidence_id": "E2"}]}
    rejected = ev.answer("Forecast?", _evidence(), FakeClient(invented), ENABLED)
    assert not rejected.used_model and "does not match evidence" in rejected.reason and "[E1]" in rejected.answer
    unknown = {**good, "citations": ["E9"]}
    assert "unknown evidence" in ev.answer("q", _evidence(), FakeClient(unknown), ENABLED).reason
    uncited_number = {**good, "answer": "About 200 tonnes.", "figures": []}
    assert "without a matching cited figure" in ev.answer("q", _evidence(), FakeClient(uncited_number), ENABLED).reason


def test_nothing_reaches_a_provider_unless_every_gate_allows_it() -> None:
    client = FakeClient({})
    cases = [
        ({**ENABLED, "APP_ENV": "production"}, _evidence(), "not enabled"),
        ({**ENABLED, "APP_ENV": "staging"}, _evidence(), "not enabled"),          # staging needs a recorded approval
        ({**ENABLED, "AGRI_LLM_ENABLED": "false"}, _evidence(), "AGRI_LLM_ENABLED"),
        (ENABLED, _evidence("PERMISSION_REQUIRED"), "licence"),
        (ENABLED, [], "no evidence"),
        ({**ENABLED, "AGRI_LLM_MAX_INPUT_TOKENS": "10"}, _evidence(), "budget"),
    ]
    for env, items, reason in cases:
        result = ev.answer("q", items, client, env)
        assert not result.used_model and reason in result.reason, (env, reason, result.reason)
    operational = [ev.Evidence("E1", "Buyer X ordered 100 kg", "100", "KG", {"licence_review_status": "APPROVED"}, classification="OPERATIONAL")]
    assert "only public statistics" in ev.answer("q", operational, client, ENABLED).reason
    assert client.calls == []


def test_only_catalogue_queries_with_checked_parameters_run() -> None:
    with pytest.raises(ev.EvidenceError, match="unknown query"):
        ev._check_params("drop_everything", {})
    with pytest.raises(ev.EvidenceError, match="code"):
        ev._check_params("series", {"crop": "GINGER'; drop table x;--", "measure": "PRODUCTION", "area": "JM", "from_year": 2010, "to_year": 2020})
    with pytest.raises(ev.EvidenceError, match="year"):
        ev._check_params("series", {"crop": "GINGER", "measure": "PRODUCTION", "area": "JM", "from_year": "2010", "to_year": 2020})
    for spec in ev.QUERY_CATALOGUE.values():  # statistics only: no operational table is ever read
        tables = {word for word in spec["sql"].replace("\n", " ").split() if "." in word and not word.startswith(("o.", "c.", "g.", "d.", "s.", "p.", "f.", "r."))}
        assert all(t.startswith("agri.") for t in tables if t[0].isalpha()), tables
