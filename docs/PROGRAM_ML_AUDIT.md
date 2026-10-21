# Program audit: ML, data and API path

Audited October 18, 2026. This first pass covers the agricultural intelligence ingestion/training/serving path and its UI boundary, with the existing full backend regression suite. It is not a completed security or performance audit of every operational module.

October 20 update: all three reproduced implementation defects below are addressed by the scoped hotfix; see `ML_RELIABILITY_HOTFIX.md` for regression evidence and provenance limits. The evaluation-independence limitation remains disclosed, not repaired through repartitioning.

No application/model code or production dataset was changed and no model was retrained. Reproductions used temporary files and process-local mocks; the training reproduction stopped before fitting.

## Findings, ordered for debugging

### 1. High: training does not verify the dataset identity it records — fixed October 18

Location: `src/backend/scripts/train_agricultural_forecast.py:15` and `:33`.

The trainer reads observations and the quality report separately. It checks report flags but does not recompute the observation hash against `quality.dataset_version` before passing data to the learner. It then copies that report's dataset version into the model artifact.

Reproduced with copies of the current files in a temporary directory: changed the first valid production value from 3,054 to the test-only value 103,054, leaving the quality report unchanged. An intercepted learner received the changed value. The probe raised before any model fit or artifact publication. This can produce a model labelled as trained on a dataset version it did not actually use after an accidental/manual observation edit.

Fix direction: validate the observation hash, natural-key uniqueness, value finiteness, units, chronology and statuses at the training boundary. Reject inconsistency before invoking any learner. First write a failing regression test for the demonstrated version mismatch.

Implemented after the user selected training-data validation. `app/agriculture/validation.py` now checks the canonical observation hash against the quality report before the trainer invokes the learner. It also validates scope, quarter dates, units, natural keys, numeric values, quarantine status, calendar continuity and quality-report counts. This verifies internal consistency; it does not independently re-extract the original PDFs or establish historical publication vintages.

The stale-version regression failed before the fix because the learner received the altered observation. After the fix, all 17 training-data validation tests pass, including corruptions with recomputed hashes. Full backend regression: **99 passed, 9 skipped**, with two existing dependency deprecation warnings. No model fitting was performed. Both saved forecast copies retain SHA-256 `35afa002842522eaffed6eac0792248719a10acfb69f3f6a72dd59ddbe8b8b00`.

Reproduce from repository root:

```powershell
.venv\Scripts\python.exe -m pytest src/backend/tests/test_training_data_validation.py -q
.venv\Scripts\python.exe -m pytest src/backend/tests -q
```

### 2. High: incomplete serving artifacts can pass as successful data — fixed October 20

Location: `src/backend/app/agriculture/api.py:47`; consumer `src/frontend/src/components/IntelligenceLab.tsx:20`.

The API checks only schema version and whether series is a list. The temporary artifact `{"schema_version":1,"series":[]}` returned HTTP 200 in a TestClient reproduction. Required experiment, forecast, quality and source fields were absent. The UI assumes these fields exist and accesses `experiment.forecast`, so the accepted payload can crash rendering rather than enter the unavailable-data state.

Fix direction: validate the complete serving contract before returning 200 and provide an explicit empty-data state. Cover incomplete-but-valid JSON and malformed nested fields, not only bad JSON or array roots. The current real artifact is complete; this is a failure-handling defect, not evidence that its displayed numbers are presently wrong.

### 3. Medium: empty history crashes the forecast workflow — fixed October 20

Location: `src/backend/app/agriculture/forecasting.py:79`.

Reproduced `backtest([])`: IndexError from `series[-1]`. The current insufficient-history test uses four rows, so it does not cover zero rows. A fully empty/filtered import cannot produce the promised graceful unavailable forecast.

Fix direction: define and test zero-row behavior, including an unknown cutoff/target, before accessing the final period. Do not invent a target quarter when no reporting period exists.

### 4. High for interpretation: later evaluation also selects the model

Location: `src/backend/app/agriculture/forecasting.py:75`.

The release gate consults both selection and later-window errors. Thus 2024–2025 is not an independent holdout. The UI now discloses this, but the workflow still needs a genuinely untouched future evaluation period before claiming prospective superiority. Historical publication/revision vintages are also unknown.

Fix direction: freeze the existing experiment as the retrospective reference. Agree on the next training/evaluation protocol before running new candidates, record each run and its dataset/configuration, and keep final evaluation out of model choice. Do not repeatedly tune on the same eight later quarters.

## What was verified

- Current backend suite: **82 passed, 9 skipped**. The nine skips require a dedicated PostgreSQL test database and concern operational concurrency/recovery, not Intelligence Lab or authentication tests.
- Fold-local scaling and prefix-only features are present. Existing future-perturbation tests pass.
- The conflicting 2016 Q3 production value remains quarantined; it is not zero-filled and seasonal calendar positions remain intact.
- FAOSTAT annual observations remain separately classified and do not enter the quarterly forecast features or target.
- Existing active agricultural candidate: ridge regression with lag/seasonal features, compared against three simple baselines. The old `app/ml/assurance-learning.py` plant-health script is commented out; it is not another trained agricultural model.
- Passing tests do not cover all findings above. The reproduced edge cases identify specific missing regression coverage.

## Proposed collaborative debugging sequence

1. Pick a finding together; recommended first issue is training-data/version validation.
2. Turn its temporary reproduction into a failing regression test.
3. Make the smallest correction and rerun that test plus affected checks.
4. Preserve the current forecast artifact as a reference.
5. Before training again, agree on the target/horizon, permitted information at each origin, selection metric, candidate configuration and untouched final evaluation period.
6. Review the worst errors together; distinguish data problems from model limitations before adding features or complexity.

The current target remains Jamaica national quarterly iceberg production, one quarter ahead. Expanding to plant health, individual farms or another crop requires a separate labelled dataset and evaluation design; the annual international category is not a substitute for quarterly iceberg observations.
