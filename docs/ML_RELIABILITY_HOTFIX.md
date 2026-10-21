# Pre-meeting reliability hotfix — October 20, 2026

Scope: training-input integrity, serving-schema validation, empty-history behavior and offline demonstration regression. No new algorithm, data migration, model tuning, production deployment or saved-artifact replacement. Existing forecasting regression tests calculate predictions in memory; the training/publishing command was not run.

## Reproductions and corrections

1. **Training identity.** The original temporary-copy reproduction changed production 3,054 to 103,054 while retaining the old quality-report version; the pre-fix trainer passed it to the intercepted learner. The regression originally failed before the previous correction. This hotfix adds single-observation fixtures for value, period, unit and source-identity changes. It also reproduced harmless record reordering being rejected. Canonicalization now sorts records by `(year, quarter, measurement)`, sorts JSON keys, rejects non-finite values, encodes UTF-8 and hashes with SHA-256. This retains the preserved ingestion hash while making record order irrelevant. The entire normalized snapshot, including source/extraction evidence, is fingerprinted, rather than only target values.
2. **Incomplete serving artifact.** Before this hotfix, `{"schema_version":1,"series":[]}` returned 200. Tests for that and four missing required sections failed. Strict Pydantic models now validate the required response, nested metrics, forecast availability, finite values, annual context and source fields before returning the original payload. Missing fields are not supplied with defaults. Invalid input returns the existing controlled 503. The frontend independently validates both authenticated responses and cached offline responses with existing Zod, showing an informative unavailable state and retry instead of crashing. The valid saved response is preserved.
3. **Empty history.** `backtest([])` raised `IndexError` before this hotfix. It now returns unavailable, null value, null target period and null cutoff, with zero-target metrics. One observation and insufficient seasonal histories are tested. Omitted calendar quarters fail closed in forecasting and artifact serving; explicitly represented null quarters retain their calendar positions. The frontend handles empty/unavailable data without manufacturing a zero forecast.

The first new hotfix run had **7 expected failures**: ordering, incomplete artifact, empty history and four missing sections. They pass after the corrections. Source-manifest linkage and actual PDF hashes are now checked before a training call can reach the learner. Tests intercept the learner to verify valid input reaches the boundary without publishing, and corrupted raw-source bytes fail before fitting.

New artifacts produced by an explicitly invoked future training command will include `training_manifest.content_hash`, canonicalization version, observation count, training cutoff and model configuration. The legacy artifact is not rewritten to pretend this metadata existed at creation.

## Preserved provenance

Read-only verification confirms 37 local source PDFs match their manifest SHA-256 hashes; all 120 normalized records link to those sources; the 40-slot saved series matches the normalized values/quarantine; dataset and artifact fingerprints match; backend and frontend snapshots are byte-identical. This covers 39 validated production observations, 40 area and 40 price observations for 2016 Q1–2025 Q4. No historical data changed.

- Dataset content hash: `d7134d44ec36dc9bd83e260bbcb210612df5db88358b19a1aec0e70b9b2802ec`.
- Saved forecast file SHA-256, both copies: `35afa002842522eaffed6eac0792248719a10acfb69f3f6a72dd59ddbe8b8b00`.
- Normalized observation file SHA-256: `f9d20421450c26feacdf7a146c16861cc1b3c545e3bcedcf83c589e61288bd51`.
- Recorded configuration: ridge alpha 10; one-quarter horizon; training cutoff 2025 Q4. Recorded estimate: 2026 Q1, 4,068.9983 tonnes.

**Limit:** this is snapshot-consistency verification, not retrospective certification of the original training execution. The legacy artifact has no contemporaneous signed input manifest, captured code/environment or serialized fitted coefficients. Historical publication/revision vintages are unknown. Nothing in this hotfix certifies when those observations were available in the past.

## Evaluation interpretation

2024–2025 was used in release selection. The existing wire keys `holdout` and `holdout_start` remain for compatibility, not as an independence claim. The later-window MAE comparison remains 553.78 versus 709.88 tonnes: approximately **21.99% lower**, preliminary retrospective evidence. All 20 targets remain 498.96 versus 595.15 tonnes. No retuning or repartitioning was performed.

The UI and meeting walkthrough already disclose this limitation. The proposed future protocol in `ML_NEXT_EXPERIMENT.md` now avoids predesignating 2026 Q1 as untouched. Freeze the selection procedure before inspecting new outcomes, document prior exposure, register consecutive targets and scoring, record release/retrieval vintages, and keep final outcomes out of selection. Prospective evaluation requires predictions frozen before actual outcomes become available.

## Changed code and tests in this hotfix

- Backend: `app/agriculture/validation.py`, `schema.py`, `api.py`, `forecasting.py`.
- Scripts: `scripts/train_agricultural_forecast.py` and new `scripts/verify_saved_agricultural_provenance.py`.
- Backend tests: `tests/test_training_data_validation.py`, new `tests/test_ml_reliability_hotfix.py`.
- Frontend: new `src/lib/intelligenceValidation.ts`, `src/lib/agriculturalIntelligence.ts`, `src/components/IntelligenceLab.tsx`.
- Frontend tests: `src/test/intelligenceLab.test.tsx`, `e2e/intelligence.spec.ts`.
- Documentation: this report, `ML_NEXT_EXPERIMENT.md`, `PROGRAM_ML_AUDIT.md` and rehearsal note in `LILY_MEETING_FIVE_MINUTES.md`.
- Browser tests refresh screenshots and Playwright reports under `src/frontend/artifacts/`; these are test evidence, not production assets.

## Reproduction and startup

Final checks on the frozen hotfix:

| Check | Actual result |
|---|---|
| Backend suite | 126 passed, 9 skipped; 2 existing dependency deprecation warnings |
| Frontend unit suite | 18 passed across 4 files |
| ESLint | Passed, exit 0 |
| TypeScript `tsc --noEmit` | Passed, exit 0 |
| Next production build, explicit demo mode | Passed; 33 static pages generated |
| Chromium offline browser suite, rebuilt preview | 13 passed |
| Both standalone recovery demonstrations | Passed, exit 0 |
| Read-only saved provenance verification | Passed; both forecast hashes unchanged |
| `git diff --check` | Passed; existing CRLF normalization warnings only |

The nine skips are the whole `tests/test_postgres_integration.py` module: `POSTGRES_TEST_DATABASE_URL` is absent. These cover real PostgreSQL concurrency/locking and recovery behavior, so that database-specific behavior remains unverified here. They are not hidden Intelligence Lab or authentication failures, and passing SQLite/offline checks do not certify production PostgreSQL persistence. Browser execution emitted a Node color-environment warning; no browser test failed. No remaining failing checks were observed in this pass.

From repository root, with the existing environment/dependencies:

```powershell
.venv\Scripts\python.exe -m pytest src/backend/tests -q
.venv\Scripts\python.exe -m src.backend.scripts.verify_saved_agricultural_provenance
.venv\Scripts\python.exe -m src.backend.scripts.e2e_recovery_demo
.venv\Scripts\python.exe -m src.backend.scripts.e2e_quality_recovery_demo
Set-Location src/frontend
npm.cmd test
npm.cmd run lint
$env:NEXT_PUBLIC_APP_MODE='demo'
$env:NEXT_PUBLIC_AUTH_MODE='demo'
npm.cmd run build
npx.cmd tsc --noEmit
npm.cmd run start -- --hostname 127.0.0.1
```

In a second terminal at `src/frontend`, while the preview is running:

```powershell
npm.cmd run test:e2e -- --workers=1
```

PowerShell's execution policy blocks the `npm.ps1` wrapper here; the installed `npm.cmd` works. No policy changes were made. The standalone backend demos reset their dedicated `.demo-*.sqlite` synthetic databases; they do not operate on production records.

## Offline rehearsal

Use `http://127.0.0.1:3000/`, then `/intelligence-lab`, then `/requirements/00000000-0000-0000-0000-000000000500`. Follow `LILY_MEETING_FIVE_MINUTES.md`. Browser coverage verifies cached official charts, 39 production records, the disputed-quarter gap, the unchanged 4,069-tonne historical estimate, the separate 1,496-record FAOSTAT annual context, missing/incomplete snapshot states and retry, the synthetic 500 kg commitment / 80 kg dropout / recovery, route navigation and Scenario Lab isolation. Screenshots: `artifacts/screenshots/intelligence-1440.png`, `intelligence-390.png`, `01-initial.png`, `02-dropout.png`, `05-restored.png`.

Standalone backend demos also passed: 500 kg committed, 80 kg dropout, 80 kg standby restoration; and a separate inspection rejecting 30 kg, reducing Grade-A coverage to 470 kg, followed by restoration to 500 kg. The offline UI and isolated backend demos are separate configurations; this is not a claim of deployed persistence or multi-tenant readiness.
