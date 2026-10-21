# Agricultural Intelligence: Checkpoint 1 completion

Implemented and verified October 17, 2026, on `feature/agricultural-intelligence-v1`. No production deployment or operational database rewrite was performed. The October 19 stability target and October 20 founder meeting remain unchanged.

## Verified acquired datasets

| Source | Reporting coverage | Crop/category | Persisted observations | Validated / usable |
|---|---|---|---:|---:|
| Jamaica Ministry, 37 original PDFs | 2016 Q1-2025 Q4 | Iceberg lettuce | 40 production | 39; 2016 Q3 quarantined |
| Same Ministry sources | 2016 Q1-2025 Q4 | Iceberg lettuce | 40 area | 40 |
| Same Ministry sources | 2016 Q1-2025 Q4 | Iceberg lettuce | 40 farmgate price | 40 |
| FAOSTAT QCL, original authenticated API response | 2016-2024 annual; requested through 2025 | 105 original item categories, including crops, livestock products and aggregates | 1,496 | 1,496 structurally validated; source classifications retained |

Ministry totals: 212 extracted overlapping quarterly cells become 120 natural-key records, 119 validated. The one production dispute is 2,525 versus 2,998 tonnes for 2016 Q3; no choice or imputation was manufactured. All six 2025 production/price sanity checks pass. Units are tonnes, hectares and JMD/kg, and reporting quarter boundaries and original PDF page/row provenance are preserved.

FAOSTAT totals: 929 production records in tonnes, 9 production records in thousands of units, and 558 area records in hectares. The non-tonnage records are never converted to tonnes. Annual reporting intervals run January 1-December 31, quarter=null. No annual value is interpolated into quarters or used as a Ministry iceberg observation. Lettuce and chicory, FAO item 372, has 18 annual production/area records and is explicitly a broader, unmapped category.

Source flags: A=949 official values; E=195 estimated; I=338 imputed by a receiving agency; X=14 values from external organizations. An import passing validation does not change a source estimate or imputation into an independently verified measurement. No values are invented by KoroFarm. Aggregate and component items coexist and must not be summed as a total.

## Successful FAOSTAT access evidence

The earlier 403 blocker was transient and has been resolved. The official Developer Portal and its referenced current OpenAPI specification were inspected:

- https://www.fao.org/faostat/en/#developer-portal
- https://www.fao.org/faostat/en/docs/faostat_openapi.yaml
- https://www.fao.org/faostat/en/src/js/FAOSTATAPIClient.js

The OpenAPI specification documents production server `https://faostatservices.fao.org/api/v1`, dimension code discovery and filtered data requests. The official browser client documents GET `/auth/guest`; this public handshake succeeded and its in-memory bearer token successfully authenticated the code, bulk metadata and data reads. No user credentials were needed for this acquisition. Tokens are never stored in manifests, raw observations or frontend data. `FAOSTAT_ACCESS_TOKEN` supports a personal bearer token for ongoing server ingestion. Authentication failure surfaces its status and requests a valid token; there is no guessed endpoint fallback.

Jamaica code 109 was verified against area metadata. Query measurement codes were resolved from official labels (2312 Area harvested, 2510 Production Quantity); response codes 5312/5510/5513 and original labels/units were preserved. The response includes no 2025 rows, fewer item-series observations in 2024, and some earlier series gaps. Global and per-item/measurement/unit gaps are stored rather than filled.

Exact successful query:

`https://faostatservices.fao.org/api/v1/en/data/QCL?area=109&element=2312%2C2510&year=2016%2C2017%2C2018%2C2019%2C2020%2C2021%2C2022%2C2023%2C2024%2C2025&output_type=objects`

Original response: `data/agriculture/faostat/raw/qcl-jamaica-2016-2025-716934145a9c.json`, SHA-256 `716934145a9c0a0bd28a84ffb596979fabc3dd2c760c26542f880938292d77b0`.

Original-response receipt: `data/agriculture/faostat/qcl-jamaica-2016-2025-source.json`. It links all original metadata and reviewed documentation snapshots and hashes. Annual normalization/validation: `data/agriculture/faostat/qcl-jamaica-2016-2025.json`. Ministry originals and complete source URLs/local paths: `data/agriculture/raw/`, `sources.json`, and `docs/AGRICULTURAL_DATA_SOURCES.md`.

## Actual code and integration changes

New in this continuation:

- `src/backend/app/agriculture/faostat_client.py`: official API adapter, metadata-based discovery, guest/personal bearer support, bounded transient retries, immutable raw/contract caches, scope/unit/flag validation and annual gap reporting.
- `src/backend/scripts/acquire_faostat.py`: reproducible, cached-by-default acquisition CLI; `--refresh` explicitly accesses the network.
- `src/backend/scripts/validate_agricultural_checkpoint.py`: offline validator checking original Ministry hashes, validated/quarantined keys, annual/quarterly classification, artifact versions and backend/demo parity; persists `data/agriculture/checkpoint-1.json`.
- `src/backend/tests/test_faostat_acquisition.py`: six automated tests using original cached responses and test-only transport fixtures.

Extended:

- `agriculture/faostat.py`: shared API/CSV normalization, reporting intervals, original source flags/classifications, normalized units, missing-value rejection and conflict-safe natural keys.
- `agriculture/api.py`: authenticated read-only GET `/agricultural-intelligence/faostat?item_code=372`; unsupported item 404, missing/invalid annual artifact 503, POST 405.
- `scripts/train_agricultural_forecast.py`: includes a separate annual context in the offline serving artifact, without passing annual data into model features or targets.
- `IntelligenceLab.tsx` and `agriculturalIntelligence.ts`: separate annual national context with count/coverage, source link, original-unit/flag table, category warning, dataset version and retrieval metadata.
- Backend auth tests, frontend component tests and desktop/mobile browser checks cover the new annual path and category separation.
- Existing source/architecture/handover/evaluation documents and official-data snapshots were updated. The existing Ministry pipeline, chronological modelling, operational routes and quantity logic were reused.

## Validation and tests actually run

- Checkpoint validator: **passed**, with machine-readable evidence in `data/agriculture/checkpoint-1.json`.
- Ministry: 37 documents parsed, six sanity checks passed, 119 validated cells, one explicit conflict. Checksums match preserved originals. Re-running acquisition reused the 37 cached source versions with zero download errors.
- FAOSTAT: 1,496 original rows, 1,496 unique annual normalized records, **zero duplicate or rejected rows**. Scope, year, element/unit, finite/non-negative values, separate classification, original source/contract checksums and cache idempotency passed. Repeated cached imports produced identical annual JSON bytes.
- Backend suite: **82 passed, 9 skipped**, with two existing Starlette/httpx deprecation warnings. The nine skipped tests require an explicitly configured dedicated PostgreSQL test database.
- Frontend: **15 tests passed**; lint and `tsc --noEmit` passed; production build passed.
- Chromium production-frontend browser suite: **12 passed**, including the 500 kg ginger dropout/recovery, existing enterprise routes, Scenario Lab, desktop/mobile annual and quarterly Intelligence Lab, page-overflow checks and API-failure/retry state.
- Standalone ginger demos: dropout recovers 420 kg to 500 kg using 80 kg reserve; quality rejection activates 30 kg reserve and restores 500 kg effective coverage. No recovery formulas were changed.

Frontend tooling initially needed restoration: the dependency bin commands were absent. `npm ci` first hit a DLL held by the previous local preview; stopping that specific KoroFarm preview process allowed install to finish. A test query incorrectly used Playwright's `exact` option in Testing Library; correcting its locator made typecheck/build pass. The install audit reported 17 dependency advisories (5 moderate, 9 high, 3 critical); no automatic dependency-major upgrades or broad security changes were applied within this data checkpoint. These are existing locked dependency risks to review separately.

Browser verification uses the existing explicit offline operational demo mode with genuine cached public statistics. Backend endpoint auth and failure states are separately tested. A deployed Supabase/PostgreSQL tenant-isolation certification was not performed.

## Reproduce from repository root (PowerShell)

```powershell
.venv\Scripts\python.exe -m pip install -e "src/backend[dev,intelligence]"
.venv\Scripts\python.exe -m src.backend.scripts.acquire_agricultural_data
.venv\Scripts\python.exe -m src.backend.scripts.ingest_agricultural_data
.venv\Scripts\python.exe -m src.backend.scripts.acquire_faostat
.venv\Scripts\python.exe -m src.backend.scripts.train_agricultural_forecast
.venv\Scripts\python.exe -m src.backend.scripts.validate_agricultural_checkpoint
.venv\Scripts\python.exe -m pytest src/backend/tests -q
.venv\Scripts\python.exe -m src.backend.scripts.e2e_recovery_demo
.venv\Scripts\python.exe -m src.backend.scripts.e2e_quality_recovery_demo
```

Use `acquire_faostat --refresh` for a deliberate new official API request; omit it to verify/reimport the preserved response offline. Existing CSV fallback imports remain available. No manual source files or credentials are currently needed to reproduce from cache.

```powershell
Set-Location src/frontend
npm.cmd ci
npm.cmd run lint
npx.cmd --no-install tsc --noEmit
npm.cmd run test
$env:NEXT_PUBLIC_APP_MODE='demo'
$env:NEXT_PUBLIC_AUTH_MODE='demo'
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1
# In another frontend terminal, with the local server running:
npx.cmd --no-install playwright test --workers=1
```

Live backend/application/auth instructions remain in `AGRICULTURAL_INTELLIGENCE_ARCHITECTURE.md` and README.md. No insecure production auth bypass is introduced.

## Continuation into Checkpoint 2

The chronological expanding-window experiment was rerun after successful data integration. All four methods share 20 quarterly targets (2021 Q1-2025 Q4). The model metrics remain unchanged because FAOSTAT annual records stay out of this quarterly experiment:

| Method | MAE, tonnes | WAPE | Bias, tonnes |
|---|---:|---:|---:|
| Previous quarter | 621.10 | 16.02% | +15.20 |
| Seasonal naive | 595.15 | 15.35% | -192.65 |
| Seasonal average | 722.02 | 18.62% | -645.27 |
| Fixed ridge candidate | 498.96 | 12.87% | -232.71 |

The measured ridge MAE reduction is 16.16% versus seasonal naive. Both later and selection windows favor ridge under the existing release gate; the test suite also verifies seasonal fallback when a candidate cannot beat it. Model configuration, every fold, historical cutoff and limitations remain persisted and displayed. The 2026 Q1 estimate of 4,069 tonnes is explicitly retrospective from the 2025 Q4 cutoff, not current or a shortage prediction. No calibrated interval is invented.

Remaining impediments: publication/revision vintages are unknown, 2016 Q3 needs Ministry clarification, 2025 FAOSTAT data was not returned, and no 2026 Ministry quarters were linked on the inspected indexes. These prevent claims of real-time prospective performance/current-quarter forecasting, but do not prevent the completed retrospective experiment. Nine PostgreSQL concurrency checks and deployed tenant isolation remain unverified. No production deployment, private operational-data import or agro-processing optimizer was added.
