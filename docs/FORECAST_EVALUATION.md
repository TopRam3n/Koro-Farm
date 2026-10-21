# Forecast evaluation

October 18 clarification: the 2024–2025 window was used in final release selection and is **not an untouched independent holdout**. Parameters and saved forecasts were not changed. See `FINAL_INTEGRATION_VERIFICATION.md` and `data/agriculture/model-audit.json` for exact prefixes, sensitivity checks and point-in-time limitations.

Experiment version: `iceberg-expanding-v1`. Target: Jamaica national quarterly iceberg lettuce production in tonnes, one quarter ahead.

## Data and design

40 calendar slots from 2016 Q1 through 2025 Q4; 39 validated production observations. The disputed 2016 Q3 slot remains null, so seasonal lags keep their calendar meaning. Missing lag rows are excluded from ridge training; no value is imputed. Prices and area are displayed historically but are not used as model features.

The first training prefix is 2016 Q1–2020 Q4, with 19 valid production observations. The 20 common evaluation targets are 2021 Q1–2025 Q4. Each fold refits only on the preceding prefix. Ridge standardization is learned only from that fold. The target quarter value is never passed to the predictor. All models use identical scored targets. No random split is used.

Methods: previous-quarter naive; same-quarter-last-year seasonal naive; expanding same-quarter historical mean; fixed ridge regression (alpha=10) using lag-1, lag-4 and sine/cosine quarter effects. No search or deep learning was used. Ridge estimates are clipped at zero to respect the non-negative production target.

Release gate: the fixed candidate must lower MAE against seasonal naive in both the 2021–2023 selection window and the later 2024–2025 window, otherwise use seasonal naive. The candidate qualifies in this experiment. This release gate consults both windows; it does not make the final selected model an independently prospectively validated system.

## Measured results

MAE = mean absolute forecast error, WAPE = total absolute error / total observed production * 100, bias = mean(forecast - observed). Negative bias means underprediction. Errors use unrounded predictions.

### 2021–2025: 20 common targets

| Model | N | MAE (tonnes) | WAPE | Bias (tonnes) |
|---|---:|---:|---:|---:|
| previous_quarter | 20 | 621.10 | 16.02% | 15.20 |
| seasonal_naive | 20 | 595.15 | 15.35% | -192.65 |
| seasonal_average | 20 | 722.02 | 18.62% | -645.27 |
| ridge_lags | 20 | 498.96 | 12.87% | -232.71 |

### 2021–2023: 12 selection targets

| Model | N | MAE (tonnes) | WAPE | Bias (tonnes) |
|---|---:|---:|---:|---:|
| previous_quarter | 12 | 514.08 | 13.29% | -67.42 |
| seasonal_naive | 12 | 518.67 | 13.41% | -199.67 |
| seasonal_average | 12 | 722.36 | 18.68% | -722.36 |
| ridge_lags | 12 | 462.41 | 11.96% | -317.30 |

### 2024–2025: 8 later targets

| Model | N | MAE (tonnes) | WAPE | Bias (tonnes) |
|---|---:|---:|---:|---:|
| previous_quarter | 8 | 781.62 | 20.08% | 139.12 |
| seasonal_naive | 8 | 709.88 | 18.23% | -182.12 |
| seasonal_average | 8 | 721.50 | 18.53% | -529.63 |
| ridge_lags | 8 | 553.78 | 14.22% | -105.81 |

Ridge lowers MAE by 96.19 tonnes (16.16%) across all 20 targets. This is a descriptive measured result on a small retrospective sample, not proof of future superiority or statistical significance. No significance claim is made.

## Historical-cutoff estimate

Selected model: `ridge_lags`. At the 2025 Q4 historical data cutoff, its one-step estimate for 2026 Q1 is **4069.00 tonnes**. Generated October 17, 2026. This is a historical-cutoff estimate, not a current-quarter forecast and not evidence of a shortage. No verified 2026 actual was available on the inspected Ministry indexes.

## Material limits

- Latest retrieved source vintages are used. We cannot establish which revisions or completed-quarter figures were available at historical forecast dates.
- Each simulated origin assumes all validated observations through the preceding quarter are available. Actual publication lag may make this optimistic. Truly as-of performance is not established.
- Only one crop and 20 evaluation targets are covered. Weather, hurricane impacts, imports, demand and usable stock are not modelled.
- 2016 Q3 production is quarantined; this reduces training history without shifting calendar slots.
- No calibrated prediction interval or empirical coverage is available. Fixed percentage bands were deliberately not added.
- The release gate and later-window comparisons are exploratory and should be followed by timestamped prospective forecasts and an untouched future evaluation period.

## Reproducibility

Run acquisition, ingestion and training commands from `docs/AGRICULTURAL_INTELLIGENCE_ARCHITECTURE.md`. `data/agriculture/intelligence.json` contains every fold, its training end and count, unrounded predictions, actual, all metrics, model configuration, assumptions and dataset/artifact hashes. Original-source records and extract text rows are separately preserved. Tests check common periods, future perturbation invariance, missing-quarter semantics, idempotency, metrics and unsupported states.

Dataset version: `d7134d44ec36dc9bd83e260bbcb210612df5db88358b19a1aec0e70b9b2802ec`.
Artifact version: `6266e42a52c6beff2211929cdcc52726f7d4a8b52c59a591512c21e897ec5121`.
