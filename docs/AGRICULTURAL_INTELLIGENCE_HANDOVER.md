# Agricultural Intelligence Sprint handover

Implemented locally on October 17, 2026, on branch `feature/agricultural-intelligence-v1`. No production deployment was performed. The implementation target remains October 19 and the founder meeting October 20.

## Checkpoint 1 continuation update

The FAOSTAT 403 blocker described in this initial handover has since been resolved. A genuine 1,496-observation Jamaica QCL annual dataset was acquired through the official current API and integrated as separate annual context. See `AGRICULTURAL_CHECKPOINT_1.md` and the updated source inventory for the current implementation and verification evidence. The original test counts below describe the initial sprint run.

## Delivered

- Reproducible official-source discovery and caching: **37 original Ministry PDFs** for 2016–2025, with original URLs, checksums, reporting periods, retrieval timestamps, HTTP modification metadata and extraction provenance.
- Strict extraction of **212 overlapping quarterly cells**, reconciled into **120 distinct country/crop/measurement/quarter records**. Validated: **39 production, 40 area, 40 price** observations. All six 2025 sanity checks pass. All 61 source iceberg rows were rendered and visually inspected.
- One quarantined cell: **2016 Q3 production** differs between two official documents (2,525 vs 2,998 tonnes). Neither is silently selected. Annual/quarter rounding differences are reported, with original values preserved.
- Offline previous-quarter, seasonal naive and seasonal-average baselines, plus a fixed regularized lag regression candidate. Chronological expanding-window evaluation on **20 identical targets**, 2021 Q1–2025 Q4. Later split-window results and every fold prediction are preserved.
- Authenticated read-only backend endpoint and integrated `/intelligence-lab` page. Historical charts/table, farmgate prices, source links, version identifiers, quarantine evidence, forecast horizon/cutoff, measured errors and limitations are visible. Explicit demo mode serves the same cached official statistics; live errors do not silently switch modes.
- Restrained homepage copy, browser metadata and navigation changes, plus one labelled Value Pathways concept. Existing operational routes and data remain separate.
- Annual FAOSTAT normalized-CSV importer with item/category/flag provenance and explicit no-mapping/no-quarterly-interpolation boundaries. No real FAOSTAT rows have been imported; automatic API integration remains blocked by documentation-resource access.

## Forecast findings

| Method | Test forecasts | MAE, tonnes | WAPE | Bias, tonnes |
|---|---:|---:|---:|---:|
| Previous quarter | 20 | 621.10 | 16.02% | +15.20 |
| Same quarter last year | 20 | 595.15 | 15.35% | −192.65 |
| Historical seasonal average | 20 | 722.02 | 18.62% | −645.27 |
| Ridge with lag/seasonal features | 20 | 498.96 | 12.87% | −232.71 |

Ridge reduced MAE by **16.16%** against seasonal naive across these targets and also lowered MAE in both the 2021–2023 selection window and 2024–2025 later evaluation window. Ridge is therefore displayed as the experimental reference. The fixed candidate was not tuned against these errors.

The generated **2026 Q1** estimate is **4,069 tonnes**, using data through **2025 Q4**. It is explicitly retrospective, not a current forecast as of October 17, 2026. Latest-vintage historical data and assumed preceding-quarter availability are used; actual publication dates and revision histories are unknown. These results do not establish real-time as-of performance. No calibrated interval, significance, shortage, demand, procurement or economic-benefit claim is made.

## Verification actually executed

| Check | Actual outcome |
|---|---|
| Pre-change backend baseline | 64 passed, 9 PostgreSQL tests skipped |
| Pre-change frontend baseline | 13 tests passed; lint passed |
| Final backend unit/API/integration suite | **76 passed, 9 skipped**, two existing Starlette/httpx deprecation warnings |
| Final frontend component suite | **15 passed** |
| TypeScript | `npx.cmd tsc --noEmit` passed |
| Lint | `npm.cmd run lint` passed |
| Production build | `npm.cmd run build` passed in live and explicit demo configurations |
| Browser regression and new UI suite | **12 passed**, Chromium, production frontend in explicit demo mode |
| New UI viewports | 1440 px desktop and 390 px mobile, no page overflow or console errors in successful-data tests |
| Existing responsive dashboard checks | 1920, 1440, 1366, 1280 and 1024 px passed |
| Source extraction/idempotency | Same observation bytes on re-import; 37 parsed documents, one explicit conflict; no duplicate keys |
| Model leakage/reproduction | Future-value perturbations leave earlier forecasts unchanged; metrics reproduced exactly in tested environment |
| Missing data/error handling | Source conflict remains null; unsupported crop 404, invalid/missing artifact 503, unauthorized API 401, POST 405; UI failure/retry works |
| Ginger dropout demo | 500 kg committed/100 kg standby → 420 kg after loss → 500 kg after 80 kg reserve activation |
| Ginger quality demo | 100 kg received, 70 accepted/30 rejected; 30 kg reserve activated; 500 kg effective coverage restored |
| Serving/snapshot consistency | Backend and frontend cached artifacts are byte-identical |

The first browser run exposed a test that sampled demo mode before hydration and a stale Assurance route heading expectation. Both test issues were corrected and the complete suite rerun successfully. The new error-state test initially used a non-unique alert locator (Next also has a route announcer); its locator was corrected and the final full run passed. Two original demo launch scripts lacked Programme/Organization FK-target imports; adding those imports made both standalone commands run. No allocation/recovery formula changed.

Browser regression covered Supply Network, Scenario Lab, Network, Traceability, Trade Evidence and the other existing workspace routes. This checkout contains no marketplace route; no marketplace was removed or invented. Browser regression used the existing explicit demo mode, not a certified deployed PostgreSQL/Supabase multi-tenant environment. The new backend endpoint was separately verified through authenticated/unauthenticated API tests.

## Remaining limitations and blocked work

1. **Publication vintages and newer quarters:** Ministry historical release dates/revision history are unknown and no 2026 observations were linked on inspected indexes. The missing as-of evidence blocks claims of prospective performance or a genuinely current forecast, not the functioning retrospective experiment.
2. **Source conflict:** Ministry clarification is required before using 2016 Q3 production. The rest of the dataset is usable with the explicit gap.
3. **PostgreSQL certification:** no dedicated `POSTGRES_TEST_DATABASE_URL` is configured, so nine concurrency/database-specific tests remain skipped. Existing tenant-isolation certification limits from PRODUCT.md remain unchanged; no real customer/farmer data was introduced.
4. **FAOSTAT automatic acquisition:** official landing HTML and `main.js` are accessible with a browser User-Agent, but the referenced API client and routes JavaScript return HTTP 403. Current documented API access could not be verified. No guessed API calls or invented international observations were substituted. The supported fallback is an official normalized CSV export; exact manual-file instructions and importer command are in the source inventory.
5. **Uncertainty/expansion:** calibrated intervals, ginger forecasting, climate features and an agro-processing optimizer are deferred. Value Pathways is conceptual only.

## Where to review and reproduce

- `data/agriculture/sources.json` and `data/agriculture/raw/`: source URLs and original local files.
- `data/agriculture/observations.json`, `quality-report.json`: normalized data, gaps, extraction and reconciliation evidence.
- `data/agriculture/intelligence.json`, `artifacts/`: versioned model configuration, all folds, forecast and limitations.
- `docs/AGRICULTURAL_INTELLIGENCE_ARCHITECTURE.md`: exact acquisition, ingestion, training, application and test commands.
- `docs/AGRICULTURAL_DATA_SOURCES.md`: complete original-source URL/local-file inventory and FAOSTAT access details.
- `docs/FORECAST_EVALUATION.md`: all/split-window metrics, selection rule, formulas and leakage assumptions.
- `docs/KOROFARM_2_PRODUCT_DIRECTION.md`: restrained positioning and deferred direction.
- `docs/LILY_MEETING_DEMO.md`: six-minute walkthrough.
- `src/frontend/artifacts/screenshots/intelligence-{1440,390}.png`: desktop/mobile full-page evidence.
- `src/frontend/artifacts/screenshots/intelligence-viewport-{1440,390}.png`: initial viewport evidence.
- `tmp/agriculture/browser-report-final.html`: final 12-test browser report; pre-existing generated reports/screenshots were preserved separately from new evidence.

Next milestone: obtain Ministry publication/revision metadata, resolve the conflicting cell, acquire updated quarters, and begin timestamped prospective forecasts with an untouched future evaluation window. Complete PostgreSQL and tenant-isolation certification separately before introducing private operational pilot data.
