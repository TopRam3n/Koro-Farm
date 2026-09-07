# KoroFarm Supply Assurance Foundation

This is the Supply Assurance MVP for Jamaican institutional ginger procurement. It includes deterministic production-lot planning, committed and standby reservations, immutable landed-cost and risk snapshots, auditable dropout recovery, and received-sublot grading with traceability. A quality rejection triggers the same reserve-first recovery path as a farmer dropout; solicitations never count as committed supply until the farmer explicitly accepts.

## Prerequisites

Python 3.11+ and PostgreSQL are required for the application database. Copy `.env.example` to `.env` or set `DATABASE_URL` to a standard PostgreSQL URL. The application does not depend on Supabase-specific APIs.

## Run

```powershell
python -m pip install -e "src/backend[dev]"
$env:DATABASE_URL = "postgresql+psycopg://user:password@host:5432/korofarm"
Set-Location src/backend
alembic upgrade head
python -m app.infrastructure.database.seed
Set-Location ../..
python -m uvicorn src.backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the complete API contract.

## Current planning endpoints

- `POST /requirements/{id}/plan` creates one immutable initial plan. It reserves exactly the required committed quantity where possible, then a 20% standby target. A second initial plan request returns `409` rather than double allocating lots.
- `GET /requirements/{id}/assurance` reports committed and standby supply separately, current coverage health, source allocations, parish concentration, and the immutable committed-supply cost snapshot.

Landed cost is calculated for committed allocations only. Standby supply reserves capacity but does not yet incur operational pickup, handling, or transport cost in the buyer-plan snapshot.

## Supply risk indicators

Each finalized plan, including a recovery plan, receives an immutable `risk-v1` snapshot. It is a deterministic structural assessment, not a prediction or a farmer score. The policy is defined in `app/risk/application/calculator.py` (`RiskPolicy`): HIGH is triggered by incomplete coverage, farmer concentration above 35%, parish concentration above 70% with standby below 15%, low standby plus low replacement depth, or average confidence below 0.67. MEDIUM thresholds are 25% farmer concentration, 55% parish concentration, 20% standby, and 30% replacement depth. Percentages are on a 0–100 scale. `GET /requirements/{id}/assurance` includes the latest snapshot; `GET /requirements/{id}/risk` returns it directly.

## Test

```powershell
python -m pytest src/backend/tests
```

Fast tests use an isolated SQLite database. The PostgreSQL integration suite is
enabled by setting `POSTGRES_TEST_DATABASE_URL` and validates the real locking
and transaction behavior used in production:

```powershell
$env:POSTGRES_TEST_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/korofarm_test"
python -m pytest src/backend/tests
```

The competition demo database can be reset only when both the application mode
and database name are safe. The command refuses production-like targets:

```powershell
$env:APP_ENV = "demo"
$env:DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/korofarm_demo"
python -m src.backend.scripts.reset_demo
```

## Demo the physical quality-recovery flow

From the repository root, run:

```powershell
python -m src.backend.scripts.e2e_recovery_demo
python -m src.backend.scripts.e2e_quality_recovery_demo
```

The second demo receives a 100kg farmer sublot, records 70kg accepted and 30kg rejected at inspection, activates exactly 30kg of authorised standby supply, and reports the resulting 500kg effective Grade-A coverage.

## Frontend integration and authentication

The Next.js frontend uses Supabase for sign-in and sends the resulting access token to the FastAPI domain API. The API validates each bearer token with Supabase before allowing access to domain routes; `/health` remains public.

Copy `src/frontend/.env.example` to `src/frontend/.env.local`. Live mode uses
the real API and demo mode is an explicit, deterministic offline fallback:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_REQUIREMENT_ID=00000000-0000-0000-0000-000000000500
NEXT_PUBLIC_APP_MODE=live
NEXT_PUBLIC_AUTH_MODE=supabase
```

Set these variables for the backend process:

```powershell
$env:SUPABASE_URL = "https://your-project.supabase.co"
$env:SUPABASE_PUBLISHABLE_KEY = "your-publishable-key"
```

Run the services in separate terminals:

```powershell
python -m uvicorn src.backend.app.main:app --reload --port 8000
Set-Location src/frontend
npm run dev
```

Sign in at `http://localhost:3000/login`. The API client in `src/frontend/src/lib/api.ts` reads the active Supabase session and adds `Authorization: Bearer <access-token>` to each request. To obtain a requirement UUID, create one through `POST /requirements` or inspect the database, then place it in `NEXT_PUBLIC_REQUIREMENT_ID` and restart Next.js.

For an isolated competition test/demo environment only, set backend
`APP_ENV=demo` and `ALLOW_INSECURE_DEMO_AUTH=true`, with frontend
`NEXT_PUBLIC_AUTH_MODE=demo`. This bypass cannot be enabled in production mode.
Use `NEXT_PUBLIC_APP_MODE=demo` for a deliberate zero-backend presentation; the
UI clearly labels the mode and never switches automatically after an API error.

## Frontend verification

```powershell
Set-Location src/frontend
npm ci
npm run lint
npm run test
npm run build
npm run test:e2e
```

The Playwright suite exercises the production frontend against PostgreSQL and
captures the five competition-flow screenshots. CI runs migrations, backend
tests, frontend checks, and that full-stack browser gate with local services.
