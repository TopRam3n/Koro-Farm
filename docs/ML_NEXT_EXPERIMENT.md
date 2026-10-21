# Collaborative ML review — October 20, 2026

The existing artifact remains frozen. No new model fitting or tuning was performed for this review.

## Current error review

The expanding training prefixes start at 2016 Q1. The first evaluated target is 2021 Q1, trained through 2020 Q4 with 19 valid observations. The last target is 2025 Q4, trained through 2025 Q3 with 38 valid observations. The disputed 2016 Q3 production remains missing.

Selection targets are 2021 Q1–2023 Q4 (12). Later targets are 2024 Q1–2025 Q4 (8); these also influence the release gate and are not an independent holdout.

| Target | Actual tonnes | Ridge tonnes | Seasonal naive tonnes | Ridge error tonnes |
|---|---:|---:|---:|---:|
| 2021 Q1 | 4300 | 3261.65 | 3787 | -1038.35 |
| 2025 Q1 | 5089 | 4118.08 | 4708 | -970.92 |
| 2025 Q2 | 4616 | 3684.19 | 3004 | -931.81 |
| 2024 Q2 | 3004 | 3883.53 | 3776 | +879.53 |
| 2025 Q4 | 3110 | 3988.59 | 3818 | +878.59 |

Ridge wins 11/20 comparisons overall and 5/8 later comparisons. Overall MAE is 498.96 tonnes versus seasonal 595.15; later MAE is 553.78 versus 709.88. Removing any single target preserves a positive mean absolute-error advantage: 65.45–132.30 tonnes overall and 81.22–262.67 later. This descriptive sensitivity check is not a confidence interval, significance test or independent validation.

The large misses are consistent with difficulty tracking sharp level changes. Do not attribute them to weather, demand or reporting errors without further source evidence. First inspect the corresponding official production tables and any revisions. Contemporaneous area/price are descriptive context, not permitted predictors unless availability at each origin can be established.

## Proposed protocol before another training run

1. Keep the current experiment as the retrospective reference. Existing 2016–2025 observations are development data; none can now be declared unseen.
2. Retain the one-quarter-ahead national iceberg production target, fixed ridge alpha 10 and lag-1/lag-4/seasonal features. Compare with previous-quarter and seasonal naive on identical eligible targets. Do not add features or tune against the eight later quarters.
3. Before inspecting newly acquired target values, register an evaluation block and freeze the model-selection procedure. Do not designate 2026 Q1 or any other already-inspected outcome as independent. Choose consecutive newly available targets only after documenting prior exposure; use genuinely future targets for prospective evaluation. Predefine a target count and reporting cadence; a small block does not guarantee statistical power.
4. For already published targets, describe evaluation as retrospective. A genuinely prospective test starts only with targets whose outcomes have not yet been released, after recording the actual information available at forecast time.
5. Record source hashes, retrieval/publication timestamps where available, dataset version, configuration and code revision. Fit on expanding prefixes; fit scaling inside each prefix. Exclude observations not released by the forecast origin. When release dates are unknown, label the simulation as assuming immediate prior-quarter availability.
6. Freeze each prediction before adding its actual outcome. Score MAE as primary, WAPE and signed bias as secondary, with target count and paired errors. Do not use final-block results to change the evaluated candidate. Keep seasonal naive as the operational reference pending review.
7. If candidate configurations change, start a separately registered experiment and reserve later unseen targets. Do not recycle this evaluation block as a fresh holdout.

This protocol is proposed for joint review, not a claim that a new untouched evaluation has already been established. The immediate next joint task is checking the five large-error quarters against source tables before deciding whether any correction is warranted.

Reproduce the read-only error review from the repository root:

```powershell
.venv\Scripts\python.exe -m src.backend.scripts.audit_forecast_errors
```
