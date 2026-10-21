"""Inspect frozen predictions without fitting, tuning or publishing a model."""
import json
from pathlib import Path


def audit(artifact):
    rows = artifact["experiment"]["forecasts"]
    errors = []
    for row in rows:
        actual = row["actual"]
        ridge = row["predictions"]["ridge_lags"]
        seasonal = row["predictions"]["seasonal_naive"]
        errors.append(dict(period=row["period"], training_end=row["training_end"],
            training_valid_count=row["training_valid_count"], actual_tonnes=actual,
            ridge_tonnes=ridge, seasonal_tonnes=seasonal,
            ridge_error_tonnes=ridge-actual,
            seasonal_error_tonnes=seasonal-actual,
            absolute_error_gain_tonnes=abs(seasonal-actual)-abs(ridge-actual)))
    summaries = {}
    start = artifact["experiment"]["config"]["holdout_start"]
    for name, subset in (("all", errors), ("later_used_for_selection", [r for r in errors if r["period"] >= start])):
        gains = [r["absolute_error_gain_tonnes"] for r in subset]
        leave_one_out = [(sum(gains)-g)/(len(gains)-1) for g in gains] if len(gains) > 1 else []
        summaries[name] = dict(n=len(gains), ridge_wins=sum(g > 0 for g in gains),
            mean_absolute_error_gain_tonnes=sum(gains)/len(gains) if gains else None,
            leave_one_out_gain_range_tonnes=[min(leave_one_out), max(leave_one_out)] if leave_one_out else None)
    return dict(dataset_version=artifact["dataset_version"], summaries=summaries,
        limitations="Descriptive sensitivity check, not an independent test or confidence interval. Publication vintages unknown.",
        errors=sorted(errors, key=lambda r: abs(r["ridge_error_tonnes"]), reverse=True))


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[3] / "data/agriculture/intelligence.json"
    print(json.dumps(audit(json.loads(path.read_text(encoding="utf-8"))), indent=2))
