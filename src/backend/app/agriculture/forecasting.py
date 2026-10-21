"""Small-sample one-step experiment. Never imported by the serving route.

Configuration is fixed: ridge alpha=10; lag-1, lag-4, sin/cos seasonality;
fold-local standardization. Missing observations remain missing calendar slots.
"""
import math
import numpy as np

MODELS = ("previous_quarter", "seasonal_naive", "seasonal_average", "ridge_lags")
CONFIG = dict(version="iceberg-expanding-v1", ridge_alpha=10.0,
              first_test_period="2021 Q1", selection_end="2023 Q4",
              holdout_start="2024 Q1", min_valid_history=16, min_ridge_rows=8)


def features(values, index):
    if index < 4 or values[index-1] is None or values[index-4] is None:
        return None
    return [values[index-1], values[index-4], math.sin(2*math.pi*(index % 4)/4), math.cos(2*math.pi*(index % 4)/4)]


def predict(history, model):
    """Only a prefix is accepted; the target value is never passed here."""
    n = len(history)
    if model == "previous_quarter":
        return history[-1] if n else None
    if model == "seasonal_naive":
        return history[-4] if n >= 4 else None
    if model == "seasonal_average":
        same = [v for i, v in enumerate(history) if i % 4 == n % 4 and v is not None]
        return float(np.mean(same)) if same else None
    if model != "ridge_lags":
        raise ValueError("Unsupported model")
    target = features(history, n)
    rows = [(features(history, i), y) for i, y in enumerate(history) if y is not None and features(history, i) is not None]
    if target is None or len(rows) < CONFIG["min_ridge_rows"]:
        return None
    x = np.asarray([r[0] for r in rows], dtype=float)
    y = np.asarray([r[1] for r in rows], dtype=float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    x = (x - mean) / scale
    y_mean = y.mean()
    coef = np.linalg.solve(x.T @ x + CONFIG["ridge_alpha"] * np.eye(x.shape[1]), x.T @ (y-y_mean))
    return max(0.0, float(y_mean + ((np.asarray(target)-mean)/scale) @ coef))


def metrics(rows, model):
    if not rows:
        return dict(n=0, mae_tonnes=None, wape_pct=None, bias_tonnes=None)
    errors = [r["predictions"][model] - r["actual"] for r in rows]
    total = sum(abs(r["actual"]) for r in rows)
    return dict(n=len(rows), mae_tonnes=float(np.mean(np.abs(errors))),
                wape_pct=100*sum(abs(e) for e in errors)/total if total else None,
                bias_tonnes=float(np.mean(errors)))


def backtest(series):
    # Missing calendar slots must be explicit; otherwise lag-4 changes meaning.
    if any((b['year']*4+b['quarter']) - (a['year']*4+a['quarter']) != 1 for a,b in zip(series,series[1:])):
        raise ValueError('Missing calendar quarters must be represented explicitly')
    values = [s["production_tonnes"] for s in series]
    rows, skipped = [], []
    for i, actual in enumerate(values):
        if series[i]["period"] < CONFIG["first_test_period"]:
            continue
        history = values[:i]
        predictions = {m:predict(history, m) for m in MODELS}
        if actual is None or sum(v is not None for v in history) < CONFIG["min_valid_history"] or any(v is None for v in predictions.values()):
            skipped.append(series[i]["period"])
            continue
        rows.append(dict(period=series[i]["period"], training_end=series[i-1]["period"],
            training_valid_count=sum(v is not None for v in history), actual=actual, predictions=predictions))
    selection = [r for r in rows if r["period"] <= CONFIG["selection_end"]]
    holdout = [r for r in rows if r["period"] >= CONFIG["holdout_start"]]
    results = {scope:{m:metrics(rs,m) for m in MODELS} for scope,rs in [("all",rows),("selection",selection),("holdout",holdout)]}
    # Conservative release gate: no candidate claim without improvement on both
    # development and later holdout. All comparisons use identical target rows.
    qualifies = bool(selection and holdout) and all(results[s]["ridge_lags"]["mae_tonnes"] < results[s]["seasonal_naive"]["mae_tonnes"] for s in ("selection", "holdout"))
    selected = "ridge_lags" if qualifies else "seasonal_naive"
    enough = len(rows) >= 8 and sum(v is not None for v in values) >= CONFIG["min_valid_history"]
    forecast = predict(values, selected) if enough else None
    last = series[-1] if series else None
    next_q = last["quarter"] % 4 + 1 if last else None
    next_year = last["year"] + (last["quarter"] == 4) if last else None
    return dict(config=CONFIG, method="Chronological expanding-window, one quarter ahead",
        availability_assumption="At each simulated origin, all validated observations through the preceding quarter are assumed available. Actual publication delays and historical revisions are unknown.",
        evaluation_status="retrospective_latest_vintage", metrics=results, forecasts=rows, skipped_test_periods=skipped,
        selected_model=selected, candidate_qualifies=qualifies,
        selection_rule="Fixed ridge candidate must lower MAE versus seasonal naive in both 2021–2023 and 2024–2025; otherwise retain seasonal naive. Release selection is exploratory, not independent prospective validation.",
        forecast=dict(status="available" if forecast is not None else "unavailable", value_tonnes=forecast,
            period=f"{next_year} Q{next_q}" if last else None, horizon_quarters=1, data_cutoff=last["period"] if last else None,
            model=selected, interval=None,
            label="Retrospective estimate from the latest historical cutoff; not a current-quarter forecast.",
            unavailable_reason=None if forecast is not None else "Forecast unavailable — insufficient validated historical data"))
