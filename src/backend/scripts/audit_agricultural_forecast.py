"""Audit saved predictions without fitting, tuning or replacing any model."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/agriculture"


def audit():
    artifact_path = DATA / "intelligence.json"
    original = artifact_path.read_bytes()
    artifact = json.loads(original)
    experiment = artifact["experiment"]
    folds = experiment["forecasts"]
    later = [r for r in folds if r["period"] >= "2024 Q1"]
    selection = [r for r in folds if r["period"] <= "2023 Q4"]
    values = artifact["series"]
    def usable_rows(period):
        history = [r["production_tonnes"] for r in values if r["period"] <= period]
        return sum(history[i] is not None and history[i-1] is not None and history[i-4] is not None for i in range(4,len(history)))
    paired = []
    for row in later:
        baseline = abs(row["predictions"]["seasonal_naive"] - row["actual"])
        candidate = abs(row["predictions"]["ridge_lags"] - row["actual"])
        paired.append(dict(period=row["period"], training_start=values[0]["period"],
            training_end=row["training_end"], valid_training_observations=row["training_valid_count"],
            usable_ridge_training_rows=usable_rows(row["training_end"]),
            ridge_absolute_error_tonnes=candidate, seasonal_absolute_error_tonnes=baseline,
            improvement_tonnes=baseline-candidate))
    differences = [r["improvement_tonnes"] for r in paired]
    yearly = {}
    for year in sorted({r["period"][:4] for r in later}):
        subset = [r for r in later if r["period"].startswith(year)]
        yearly[year] = {m:sum(abs(r["predictions"][m]-r["actual"]) for r in subset)/len(subset)
                        for m in ("ridge_lags","seasonal_naive")}
    result = dict(artifact_version=artifact["artifact_version"],
        artifact_sha256=hashlib.sha256(original).hexdigest(),
        model_source_sha256=hashlib.sha256((ROOT/"src/backend/app/agriculture/forecasting.py").read_bytes()).hexdigest(),
        initial_training_start=values[0]["period"], initial_training_end=folds[0]["training_end"],
        initial_valid_training_observations=folds[0]["training_valid_count"],
        initial_usable_ridge_training_rows=usable_rows(folds[0]["training_end"]),
        selection_periods=[r["period"] for r in selection], later_evaluation_periods=[r["period"] for r in later],
        final_model_training_end=experiment["forecast"]["data_cutoff"],
        final_valid_training_observations=sum(r["production_tonnes"] is not None for r in values),
        untouched_holdout=False,
        holdout_note="2024-2025 was used in the final release-selection gate. It is a later retrospective evaluation window, not an untouched independent holdout. Earlier later-window actuals enter subsequent expanding-window training prefixes.",
        tuning_note="The saved implementation fixes alpha=10 and lag/seasonal features; no model was tuned or refitted by this audit. No timestamped preregistration proves the full historical design process.",
        availability_note=experiment["availability_assumption"],
        quarantine_note="2016 Q3 is null and excluded from targets and any regression rows needing it as a lag; calendar positions are preserved.",
        paired_errors=paired, yearly_mae_tonnes=yearly,
        later_metrics=experiment["metrics"]["holdout"],
        wins=sum(d>0 for d in differences), losses=sum(d<0 for d in differences), ties=sum(d==0 for d in differences),
        mean_paired_improvement_tonnes=sum(differences)/len(differences),
        drop_one_improvement_range_tonnes=[min((sum(differences)-d)/(len(differences)-1) for d in differences),
                                          max((sum(differences)-d)/(len(differences)-1) for d in differences)],
        interpretation="Preliminary descriptive retrospective evidence: lower mean error in both years and all leave-one-quarter-out summaries, but only eight correlated targets, 5 wins/3 losses, release selection used this window, and publication vintages are unknown. No statistical-significance or prospective-performance claim.")
    if artifact_path.read_bytes() != original:
        raise ValueError("Saved model artifact changed during audit")
    (DATA / "model-audit.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return result


if __name__ == "__main__":
    result = audit()
    print(json.dumps({k:result[k] for k in ["initial_training_start","initial_training_end","selection_periods",
        "later_evaluation_periods","untouched_holdout","wins","losses","mean_paired_improvement_tonnes",
        "drop_one_improvement_range_tonnes","interpretation"]},indent=2))
