"""Forecasting interfaces, transparent baselines, feature generation and backtesting (R1 WP5 preparation).

Scope: the shape every forecasting model must have, the baselines any later model must beat, and the evaluation that
decides it. No model is trained on paid infrastructure and no external provider is called. Nothing here touches
operational trade data or the deterministic recovery engine; forecasts are advisory analytics, never inputs that move
stock, commit suppliers or bypass approval.

* `Forecaster`: fit on one series (ordered, equally spaced periods) and predict `horizon` steps with a point value
  and an empirical interval.
* Baselines: last value, seasonal last value, moving average and drift. Deterministic and explainable.
* `build_features`: lags, rolling statistics and period-over-period change, computed only from earlier periods
  (no look-ahead), for later statistical or machine-learning models.
* `backtest`: rolling-origin evaluation (train on everything before each origin, forecast ahead, compare), with
  MAE, RMSE, sMAPE, MASE against the last-value baseline, and interval coverage.
* `record_model_run`: stores a run, its forecasts and evaluations in `agri` with the data snapshot it used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import mean, pstdev
from typing import Protocol, Sequence

INTERVAL_LEVEL = 0.8


@dataclass(frozen=True)
class ForecastPoint:
    step: int
    point: float
    lower: float | None
    upper: float | None


class Forecaster(Protocol):
    code: str
    version: str

    def fit(self, values: Sequence[float]) -> "Forecaster": ...

    def predict(self, horizon: int) -> list[ForecastPoint]: ...


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


@dataclass
class _Baseline:
    code: str = "baseline"
    version: str = "1"
    history: list[float] = field(default_factory=list)
    residuals: list[float] = field(default_factory=list)

    def _one_step(self, history: list[float]) -> float | None:  # forecast of the next value from `history`
        raise NotImplementedError

    def _ahead(self, history: list[float], step: int) -> float:
        extended = list(history)
        for _ in range(step):
            extended.append(self._one_step(extended))
        return extended[-1]

    def fit(self, values: Sequence[float]):
        self.history = [float(v) for v in values]
        if not self.history:
            raise ValueError("cannot fit on an empty series")
        self.residuals = [self.history[i] - predicted for i in range(1, len(self.history))
                          if (predicted := self._one_step(self.history[:i])) is not None]
        return self

    def predict(self, horizon: int) -> list[ForecastPoint]:
        if horizon < 1:
            raise ValueError("horizon must be at least 1")
        alpha = (1 - INTERVAL_LEVEL) / 2
        low_q, high_q = _quantile(self.residuals, alpha), _quantile(self.residuals, 1 - alpha)
        points = []
        for step in range(1, horizon + 1):
            point = max(self._ahead(self.history, step), 0.0)  # these statistics cannot be negative
            widen = math.sqrt(step)  # uncertainty grows with distance; a simple, stated assumption
            lower = max(point + low_q * widen, 0.0) if self.residuals else None
            upper = point + high_q * widen if self.residuals else None
            if lower is not None and lower > point:
                lower = point
            if upper is not None and upper < point:
                upper = point
            points.append(ForecastPoint(step, point, lower, upper))
        return points


@dataclass
class LastValue(_Baseline):
    code: str = "last_value"

    def _one_step(self, history):
        return history[-1] if history else None


@dataclass
class SeasonalLastValue(_Baseline):
    season: int = 4  # quarters
    code: str = "seasonal_last_value"

    def _one_step(self, history):
        if len(history) >= self.season:
            return history[-self.season]
        return history[-1] if history else None


@dataclass
class MovingAverage(_Baseline):
    window: int = 3
    code: str = "moving_average"

    def _one_step(self, history):
        return mean(history[-self.window:]) if history else None


@dataclass
class Drift(_Baseline):
    code: str = "drift"

    def _one_step(self, history):
        if len(history) < 2:
            return history[-1] if history else None
        return history[-1] + (history[-1] - history[0]) / (len(history) - 1)


BASELINES = {"last_value": LastValue, "seasonal_last_value": SeasonalLastValue, "moving_average": MovingAverage, "drift": Drift}


def build_features(periods: Sequence[date], values: Sequence[float], lags: Sequence[int] = (1, 2, 3), window: int = 3) -> list[dict]:
    """One feature row per period from earlier periods only. Missing history gives None, never a guess."""
    if len(periods) != len(values):
        raise ValueError("periods and values must have the same length")
    rows = []
    for i, (period, value) in enumerate(zip(periods, values)):
        past = [float(v) for v in values[:i]]
        row: dict = {"period_start": period.isoformat(), "target": float(value), "index": i}
        for lag in lags:
            row[f"lag_{lag}"] = past[-lag] if len(past) >= lag else None
        recent = past[-window:]
        row[f"rolling_mean_{window}"] = mean(recent) if len(recent) == window else None
        row[f"rolling_std_{window}"] = pstdev(recent) if len(recent) == window else None
        row["change_from_previous"] = (past[-1] - past[-2]) / past[-2] if len(past) >= 2 and past[-2] else None
        rows.append(row)
    return rows


def _metrics(actuals: list[float], predictions: list[float], naive_errors: list[float], covered: list[bool]) -> dict:
    errors = [a - p for a, p in zip(actuals, predictions)]
    mae = mean(abs(e) for e in errors)
    smape_terms = [abs(a - p) / ((abs(a) + abs(p)) / 2) for a, p in zip(actuals, predictions) if abs(a) + abs(p) > 0]
    naive_mae = mean(abs(e) for e in naive_errors) if naive_errors else None
    return {
        "mae": mae,
        "rmse": math.sqrt(mean(e * e for e in errors)),
        "smape": mean(smape_terms) if smape_terms else None,
        "mase": mae / naive_mae if naive_mae else None,
        "interval_coverage": sum(covered) / len(covered) if covered else None,
        "forecasts": len(errors),
    }


def backtest(values: Sequence[float], models: dict[str, Forecaster], *, min_train: int = 5, horizon: int = 1) -> dict:
    """Rolling-origin evaluation. For each origin t (from min_train), fit on values[:t] and score the forecast of
    values[t + horizon - 1]. MASE compares with the in-sample one-step last-value error, so MASE < 1 beats it."""
    series = [float(v) for v in values]
    if len(series) < min_train + horizon:
        raise ValueError(f"need at least {min_train + horizon} periods for this backtest, have {len(series)}")
    naive_errors = [series[i] - series[i - 1] for i in range(1, min_train)]
    results = {}
    for name, model in models.items():
        actuals, predictions, covered = [], [], []
        for origin in range(min_train, len(series) - horizon + 1):
            forecast = model.fit(series[:origin]).predict(horizon)[-1]
            actual = series[origin + horizon - 1]
            actuals.append(actual)
            predictions.append(forecast.point)
            if forecast.lower is not None and forecast.upper is not None:
                covered.append(forecast.lower <= actual <= forecast.upper)
        results[name] = _metrics(actuals, predictions, naive_errors, covered)
    best = min(results, key=lambda k: results[k]["mae"])
    return {"min_train": min_train, "horizon": horizon, "interval_level": INTERVAL_LEVEL, "models": results, "best_by_mae": best}


def record_model_run(session, *, model: Forecaster, purpose: str, measure_code: str, crop_id, geo_area_id, period_type: str,
                     target_periods: Sequence[date], forecasts: Sequence[ForecastPoint], unit_code: str, created_by: str,
                     training: tuple[date, date] | None = None, evaluation: dict | None = None,
                     data_snapshot: Sequence[str] = (), parameters: dict | None = None):
    """Store a model run with its forecasts and metrics (agri schema, PostgreSQL)."""
    from datetime import datetime, timezone
    from src.backend.app.agriculture.domain.models import Forecast, ModelEvaluation, ModelRun

    run = ModelRun(model_code=model.code, model_version=model.version, purpose=purpose, parameters=parameters or {},
                   training_start=training[0] if training else None, training_end=training[1] if training else None,
                   data_snapshot=list(data_snapshot), status="SUCCEEDED", created_by=created_by,
                   finished_at=datetime.now(timezone.utc))
    session.add(run)
    session.flush()
    for target, point in zip(target_periods, forecasts):
        session.add(Forecast(model_run_id=run.id, measure_code=measure_code, crop_id=crop_id, geo_area_id=geo_area_id,
                             period_type=period_type, target_period_start=target, horizon=point.step,
                             point=Decimal(str(round(point.point, 6))),
                             lower=Decimal(str(round(point.lower, 6))) if point.lower is not None else None,
                             upper=Decimal(str(round(point.upper, 6))) if point.upper is not None else None,
                             interval_level=Decimal(str(INTERVAL_LEVEL)), unit_code=unit_code))
    for metric, value in (evaluation or {}).items():
        if isinstance(value, (int, float)) and value is not None and not isinstance(value, bool):
            session.add(ModelEvaluation(model_run_id=run.id, metric_code=metric, value=Decimal(str(round(float(value), 10))),
                                        baseline_model_code="last_value"))
    session.flush()
    return run
