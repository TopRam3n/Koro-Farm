# Final integration and verification — October 18, 2026

Branch: `feature/agricultural-intelligence-v1`. Stability target October 19; Lily meeting October 20. No production deployment or operational database rewrite was performed.

## Changes in this verification pass

- Added `src/backend/scripts/audit_agricultural_forecast.py` and `data/agriculture/model-audit.json`. The audit reads saved predictions without fitting, tuning or replacing the model artifact.
- Updated `IntelligenceLab.tsx`: the visible warning now says the later evaluation was used in release selection and is not an untouched holdout. The introduction uses the requested full agricultural-intelligence/coordination positioning. Homepage My Work already has that wording. Procurement/supply assurance and the labelled planned Value Pathways concept remain intact.
- Hardened `agriculture/api.py`: an invalid JSON array now returns unavailable-artifact 503 rather than an unexpected attribute error. Extended the existing backend error test and frontend caveat assertion.
- Added `e2e-live/intelligence.spec.ts` and `playwright.intelligence-live.config.ts` for actual frontend-to-FastAPI checks. Those two checks were **not executed**, because automatic approval review blocked starting the live frontend verification process. They are not counted as passing tests.
- Added a rehearsable five-minute walkthrough in `LILY_MEETING_FIVE_MINUTES.md` and reviewed desktop/mobile screenshots.

## Exact training, selection and later evaluation periods

Initial training: **2016 Q1–2020 Q4**, 19 validated production observations in 20 calendar slots, yielding 15 usable ridge rows after lag requirements. Selection targets: **2021 Q1–Q4, 2022 Q1–Q4, 2023 Q1–Q4**, 12 expanding-window predictions. Each prefix starts in 2016 Q1 and ends in the preceding quarter. The final historical-cutoff model uses all 39 validated observations through 2025 Q4.

| Later target | Training start | Training end | Valid production history | Usable ridge rows | Seasonal absolute error (t) | Ridge absolute error (t) |
|---|---|---|---:|---:|---:|---:|
| 2024 Q1 | 2016 Q1 | 2023 Q4 | 31 | 27 | 941.00 | 706.91 |
| 2024 Q2 | 2016 Q1 | 2024 Q1 | 32 | 28 | 772.00 | 879.53 |
| 2024 Q3 | 2016 Q1 | 2024 Q2 | 33 | 29 | 226.00 | 33.76 |
| 2024 Q4 | 2016 Q1 | 2024 Q3 | 34 | 30 | 405.00 | 1.56 |
| 2025 Q1 | 2016 Q1 | 2024 Q4 | 35 | 31 | 381.00 | 970.92 |
| 2025 Q2 | 2016 Q1 | 2025 Q1 | 36 | 32 | 1612.00 | 931.81 |
| 2025 Q3 | 2016 Q1 | 2025 Q2 | 37 | 33 | 634.00 | 27.18 |
| 2025 Q4 | 2016 Q1 | 2025 Q3 | 38 | 34 | 708.00 | 878.59 |

**Was the holdout untouched? No.** The existing release-selection gate compares both 2021–2023 and 2024–2025 MAE to choose the displayed model. Thus the later eight quarters were consulted for final selection. Fixed alpha=10 and fixed lag/seasonal features do not prove independent holdout validation; there is no timestamped preregistration proving the full design history. Earlier later-window actuals enter subsequent rolling prefixes: these are sequential one-step predictions, not eight forecasts frozen from a December 2023 model. No retuning was performed in this pass. Confirm on an untouched future period rather than tuning again against these quarters.

**Were inputs historically available? Not fully established.** Production lag-1/lag-4 and quarter sine/cosine features use preceding values only, with fold-local scaling and training. Future-perturbation tests pass. However, latest retrieved revisions are used and all preceding-quarter statistics are assumed available at each origin. Release delay and revision leakage cannot be ruled out. This is a latest-vintage retrospective simulation, not measured point-in-time prospective performance. Prices, area and annual FAOSTAT are not model features.

**2016 Q3:** the production source says 2,525 tonnes and the combined source says 2,998. Its normalized value remains null. No source value is silently selected, no missing target is scored, and regression rows requiring the missing lag are excluded. Calendar slots remain intact, preserving seasonal lag alignment.

| Eight later forecasts, 2024 Q1–2025 Q4 | MAE (t) | WAPE | Bias (t) |
|---|---:|---:|---:|
| Seasonal naive | 709.88 | 18.23% | −182.13 |
| Fixed ridge | 553.78 | 14.22% | −105.81 |

MAE is 156.09 tonnes (21.99%) lower. Ridge wins 5 quarters and loses 3. It has lower yearly MAE in 2024 (405.44 vs 586.00) and 2025 (702.12 vs 833.75). Omitting any one later quarter leaves a positive mean improvement, 81.22–262.67 tonnes. This is descriptive sensitivity, **not a confidence interval or significance test**. Eight correlated targets, three losses, selection use and unknown vintages limit the result to **preliminary retrospective evidence**. The unchanged 20-target MAE comparison is 498.96 vs 595.15 tonnes (16.16% lower).

## Why the output still targets 2026 Q1

The generator advances one quarter from the latest validated target, 2025 Q4, rather than today's date. Its 4,069-tonne estimate is historical as of October 18. All four Ministry indexes were fetched successfully again on October 18 and still link no 2026 crop tables. An official June 30, 2026 news article describes aggregate Q1 2026 domestic production, but provides no compatible iceberg quantity. Aggregate totals or vegetable-growth percentages cannot substitute for an iceberg actual. This does not prove no newer records exist elsewhere; Ministry confirmation remains needed.

Receipts: `tmp/agriculture/availability-2026-10-18.json` and `2026-national-context.html`. Official context: https://www.moa.gov.jm/content/agricultural-sector-rebounds .

The UI explicitly shows retrospective labelling, one-quarter horizon, 2025 Q4 cutoff, and no calibrated uncertainty interval. The saved interval is null. No arbitrary bands, confidence scores, shortage probabilities or purchasing actions are shown.

## FAOSTAT concrete evidence

Adapter: `src/backend/app/agriculture/faostat_client.py`; shared annual normalizer `faostat.py`; command `scripts/acquire_faostat.py`. Official portal: https://www.fao.org/faostat/en/#developer-portal . OpenAPI: https://www.fao.org/faostat/en/docs/faostat_openapi.yaml . Production base: `https://faostatservices.fao.org/api/v1/`.

The successful public guest-token handshake follows the official FAOSTATAPIClient.js; a personal `FAOSTAT_ACCESS_TOKEN` is also supported. Tokens are retained in memory, not source receipts or frontend bundles. The full request uses documented `/en/data/QCL` with area 109, discovered query elements 2312/2510 and years 2016–2025. Exact URL, metadata, original response and hashes are in `data/agriculture/faostat/qcl-jamaica-2016-2025-source.json`.

- Dataset: **Crops and livestock products, QCL**. Country: **Jamaica, FAO area 109**.
- Acquired subset: **1,496 annual records**, **2016–2024**, **105 source item categories including livestock products and aggregates**. No 2025 rows returned.
- Units: **558 ha records**, **929 production records in t**, **9 production records in 1000 No**. No non-tonnage record is treated as tonnes.
- Item **372 = Lettuce and chicory**, 18 annual production/area records. It is broader than Ministry iceberg and is neither mapped nor interpolated into quarterly model data.
- Source flags A/E/I/X remain explicit. Import validation does not transform source estimates or imputations into independently measured facts.
- Normalized storage: `data/agriculture/faostat/qcl-jamaica-2016-2025.json`. Original response: `data/agriculture/faostat/raw/qcl-jamaica-2016-2025-716934145a9c.json`. Contract/metadata snapshots remain under the same `raw/` directory.

On October 18 a fresh request to `/en/data/QCL?area=109&item=372&element=2510&year=2024&output_type=objects` succeeded, returning Jamaica/item 372/year 2024 production **17,053 t**, flag A. The response uses legacy element 5510 while the discovered query code is 2510; the adapter preserves their proper roles. Evidence: `tmp/agriculture/faostat-live-verification-2026-10-18.json`.

```powershell
.venv\Scripts\python.exe -m src.backend.scripts.acquire_faostat
# Explicit network refresh, preserving original versions:
.venv\Scripts\python.exe -m src.backend.scripts.acquire_faostat --refresh
.venv\Scripts\python.exe -m src.backend.scripts.validate_agricultural_checkpoint
```

Cached imports remain idempotent, with zero duplicate/rejected annual rows. No manual source file or credential is currently needed for cached reproduction.

## Working application routes and boundaries

`/intelligence-lab` uses existing AuthGate, AppShell, apiFetch, Query and Recharts. Verified: production and farmgate charts, accessible observation table, experimental panel, model/baseline comparisons, horizon/cutoff, original Ministry URLs/page evidence, separate annual FAOSTAT context, dataset versions, loading, error/retry and unavailable states. National estimates, synthetic operations and forecasts remain distinct.

`GET /agricultural-intelligence` is authenticated and read-only: unsupported crop 404, missing/invalid artifact 503, POST 405. A real local HTTP request returned 200 with the unchanged artifact, 39 production observations and 1,496 annual records. `GET /agricultural-intelligence/faostat?item_code=372` separately serves annual context. Evidence: `tmp/agriculture/final-http-api-evidence.json`. That loopback verification used existing explicit local demo auth; its process was stopped afterwards. It does not certify real Supabase login.

Live mode calls FastAPI. Explicit demo mode reads the byte-identical official snapshot `/agriculture/intelligence.json`; it is not an automatic fallback after live errors. Demo browser tests and a real HTTP backend check succeeded separately. A complete real-login browser-to-backend session remains unverified.

Existing `/`, `/requirements/00000000-0000-0000-0000-000000000500`, `/scenario-lab`, `/supply`, `/network`, `/traceability`, `/trade-evidence` and the remaining enterprise route map were preserved. This checkout contains no marketplace route; none was removed.

## Actual checks, skips and blocked work

| Check on October 18 | Actual outcome |
|---|---|
| Backend unit/API/SQLite integration | **82 passed, 9 skipped**, two existing Starlette/httpx deprecation warnings |
| Frontend unit/component tests | **15 passed** |
| Lint and TypeScript | passed |
| Production build | passed in demo and live API configurations; final preview restored to explicit demo |
| Existing Chromium demo browser suite | **12 passed**, including responsive layouts, enterprise routes, recovery, Scenario Lab and Intelligence Lab error/retry |
| New actual-API browser suite | **Not run: startup blocked by automatic approval review** |
| Persisted-data checkpoint validator | passed |
| Fresh official FAOSTAT request | successful |
| Real local FastAPI HTTP request | 200, existing local demo auth only |
| Ginger dropout backend demonstration | 500 committed / 100 standby → 420 after loss → 500 after 80 reserve activation |
| Ginger quality-rejection backend demonstration | 70 accepted / 30 rejected from 100 received; 30 reserve restores 500 effective coverage |

All nine skips are in `test_postgres_integration.py`, gated by missing `POSTGRES_TEST_DATABASE_URL`. They cover concurrent lot reservation, reserve activation, replacement acceptance, dropout/idempotency, in-progress duplicate commands, receipt quantity, shipment consumption, availability/reservation changes, and recovery versus a new requirement. **They concern operational persistence and recovery under concurrency; none skips an Intelligence Lab or authentication test.** Passing SQLite checks do not certify PostgreSQL row locks/isolation or deployed tenant isolation. The fixture recreates tables, so only a dedicated authorized test database may be supplied; no live database was selected or altered.

Automatic approval review rejected starting the live frontend verification process with **“blocked by policy”** and no more detailed reason. That rejected configuration was not started through another mechanism. The tested, safer explicit offline demo was rebuilt and restarted instead; it makes no operational backend/database calls. The two prepared live browser checks are not counted as passing. Real Supabase-account login and deployed tenant-isolation certification remain outstanding.

Screenshots reviewed: `src/frontend/artifacts/screenshots/final-intelligence-{1440,390}.png`, `final-intelligence-viewport-{1440,390}.png`, and `final-forecast-{1440,390}.png`.

## Exact startup and verification

Use `LILY_MEETING_FIVE_MINUTES.md` for meeting startup and rehearsal. Current preview: http://127.0.0.1:3000/intelligence-lab in explicit offline demo mode. Artifacts are present; do not retrain merely to demonstrate them.

Normal authenticated live application requires the existing authorized Supabase project and operational database. Replace placeholders locally; do not paste private credentials into source or chat. Terminal 1, repository root:

```powershell
$env:APP_ENV='development'
$env:ALLOW_INSECURE_DEMO_AUTH='false'
$env:SUPABASE_URL='https://YOUR_PROJECT.supabase.co'
$env:SUPABASE_PUBLISHABLE_KEY='YOUR_PROJECT_PUBLIC_PUBLISHABLE_KEY'
# Set DATABASE_URL to the existing authorized database for operational routes.
.venv\Scripts\python.exe -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, after stopping the demo frontend:

```powershell
Set-Location src/frontend
$env:NEXT_PUBLIC_APP_MODE='live'
$env:NEXT_PUBLIC_AUTH_MODE='supabase'
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8000'
$env:NEXT_PUBLIC_SUPABASE_URL='https://YOUR_PROJECT.supabase.co'
$env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY='YOUR_PROJECT_PUBLIC_PUBLISHABLE_KEY'
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1
```

Sign in with the existing project account. Do not seed/reset live operational data. These are normal startup instructions, not a claim that a real Supabase-account browser session was exercised here.

Verification without replacing the saved model:

```powershell
.venv\Scripts\python.exe -m src.backend.scripts.audit_agricultural_forecast
.venv\Scripts\python.exe -m src.backend.scripts.validate_agricultural_checkpoint
.venv\Scripts\python.exe -m pytest src/backend/tests -q -rs
.venv\Scripts\python.exe -m src.backend.scripts.e2e_recovery_demo
.venv\Scripts\python.exe -m src.backend.scripts.e2e_quality_recovery_demo
Set-Location src/frontend
npm.cmd run lint
npx.cmd --no-install tsc --noEmit
npm.cmd run test
# With explicit-demo production frontend running:
npx.cmd --no-install playwright test --workers=1
```

Additional prepared command: `npx.cmd --no-install playwright test --config playwright.intelligence-live.config.ts`. Its expected local live-API test setup is described in the source; startup was blocked here, so no passing result is claimed.

## Remaining blockers

Obtain Ministry publication/revision vintages, clarify 2016 Q3, and obtain newer compatible crop-level quarters before claiming point-in-time or current forecasting skill. Confirm on an untouched future period rather than retuning the eight later quarters. Complete real authenticated browser integration and PostgreSQL/tenant-isolation certification before production/pilot claims. No production deployment was authorized or performed; agro-processing remains planned.
