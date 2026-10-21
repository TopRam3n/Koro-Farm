# Agricultural Intelligence implementation

Implementation date: October 17, 2026. Branch: `feature/agricultural-intelligence-v1`.

## Initial implementation map

The audited application uses Next.js 16.3.2, React, TypeScript, TanStack Query and Recharts, with a FastAPI/SQLAlchemy backend, PostgreSQL operational storage and Supabase sign-in. README.md and PRODUCT.md govern operational quantity distinctions. The frontend AGENTS.md/CLAUDE.md require reading the installed Next.js guides; layouts/pages and server/client component guides were consulted. No root AGENTS.md or CLAUDE.md was present.

Existing bounded planning/recovery, Scenario Lab, network, analytics and traceability were retained. There was no agricultural statistics pipeline or Intelligence Lab route. The old commented plant-health model was not reused. No marketplace route or marketplace implementation was found in this checkout; none was removed or renamed. PRODUCT.md explicitly describes the current product as supply assurance rather than a marketplace.

Baseline protection: pre-existing modified `src/frontend/next-env.d.ts` and untracked user assets/skills/video outputs were identified. An implementation branch was created without resetting the tree. Before implementation, backend tests passed 64 with 9 PostgreSQL skips; frontend tests passed 13 and lint passed. A pre-change production build was not captured; subsequent live and demo builds both passed.

## Data and execution boundaries

1. `python -m src.backend.scripts.acquire_agricultural_data` discovers the four official indexes, caches original linked PDFs by content hash, preserves versions and records failures. Existing downloads are reused; `--refresh` checks for new content. It never guesses Ministry download paths.
2. `python -m src.backend.scripts.ingest_agricultural_data` parses reviewed PDF text layers, verifies checksums, headers, units, years, quarter order, explicit iceberg aliases and numeric formats. It reconciles overlapping sources, prefers combined documents only on agreeing cells and quarantines conflicts. Annual totals are independently checked with a documented rounding tolerance. Stable natural keys prevent duplicated observations; missing values are never zero-filled. Importing does not touch operational databases.
3. `python -m src.backend.scripts.train_agricultural_forecast` runs controlled offline expanding-window evaluation, stores configuration and all fold predictions, produces a versioned artifact, and atomically updates the backend artifact and identical frontend official-data snapshot. Training never runs on a request.
4. Authenticated `GET /agricultural-intelligence` reads the artifact. Unsupported crops return 404; absent/invalid artifacts return 503. POST returns 405. Existing bearer-token authentication remains applied. No operational write is possible through this router.
5. `/intelligence-lab` uses the existing AuthGate, AppShell, apiFetch, Query provider, charts and design system. Live mode requests the backend. Explicit offline demo mode loads the same frozen official-data artifact, labelled as cached official statistics; it does not manufacture national data or silently fallback after a live error.

## UI

The page shows Jamaica/national/iceberg scope, latest observed production and farmgate price, ingestion date, historical charts, an accessible table, forecast horizon and cutoff, model identity, all-model and split-window metrics, source links, dataset and artifact hashes, quarantine evidence and limitations. Unknown production remains a chart gap and “Unavailable” in the table. Forecasts are in a separate experimental panel. Loading, API error/retry and unsupported/insufficient forecast states are explicit. Source publication dates are unknown.

The latest available cutoff is 2025 Q4. The 2026 Q1 estimate is labelled retrospective, not current as of October 17. No shortage, contractual inventory, demand, procurement or planting action is inferred from it. No interval is shown because none was calibrated.

## Reproduction (PowerShell, repository root)

```powershell
.venv\Scripts\python.exe -m pip install -e "src/backend[dev,intelligence]"
.venv\Scripts\python.exe -m src.backend.scripts.acquire_agricultural_data
.venv\Scripts\python.exe -m src.backend.scripts.ingest_agricultural_data
.venv\Scripts\python.exe -m src.backend.scripts.acquire_faostat
.venv\Scripts\python.exe -m src.backend.scripts.train_agricultural_forecast
.venv\Scripts\python.exe -m pytest src/backend/tests -q
.venv\Scripts\python.exe -m src.backend.scripts.e2e_recovery_demo
.venv\Scripts\python.exe -m src.backend.scripts.e2e_quality_recovery_demo
```

Exact numerical experiment was executed using Python 3.14.3, NumPy 2.5.3 and pdfplumber 0.11.10. For exact environment replication on Python >=3.12, install `numpy==2.5.3`; compatible NumPy versions are permitted for older application runtimes. Floating-point differences across numerical libraries should be compared with tolerance.

Live application: follow existing README database/auth setup, then run `.venv\Scripts\python.exe -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000`. In a separate terminal:

```powershell
Set-Location src/frontend
npm.cmd ci
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run test
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1
```

For a local synthetic operational demonstration with real cached national statistics, set `NEXT_PUBLIC_APP_MODE=demo` and `NEXT_PUBLIC_AUTH_MODE=demo` in the frontend process before building and starting. These process settings do not alter production auth. Open `http://127.0.0.1:3000/intelligence-lab`. With the server running, execute `npx.cmd playwright test --workers=1`. Never enable an insecure backend demo-auth bypass in production.

No database migration, production deployment, operational data rewrite or external paid AI service was introduced.

## Checkpoint 1 continuation

FAOSTAT access is now working. `agriculture/faostat_client.py` implements the current documented QCL query API plus the official client guest-token mechanism, with optional personal bearer authentication. It caches original responses and contract/metadata snapshots, normalizes annual observations separately, preserves source flags and records gaps without interpolation. The existing quarterly forecast never consumes these annual records. The authenticated `/agricultural-intelligence/faostat` endpoint and a separately labelled Intelligence Lab annual-context section expose the acquired data. See `AGRICULTURAL_CHECKPOINT_1.md` for current evidence and tests; the original handover documents the earlier state.
