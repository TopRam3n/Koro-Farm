# KoroFarm Supply Assurance Foundation

This is the initial backend foundation for the Caribbean Agricultural Supply Assurance MVP. It includes deterministic production-lot planning, committed and standby reservations, and immutable landed-cost snapshots. Agent orchestration, recovery, physical reconciliation, and trade evidence remain deliberately deferred.

## Prerequisites

Python 3.11+ and PostgreSQL are required for the application database. Copy `.env.example` to `.env` or set `DATABASE_URL` to a standard PostgreSQL URL. The application does not depend on Supabase-specific APIs.

## Run

```powershell
python -m pip install -e ".[dev]"c
$env:DATABASE_URL = "postgresql+psycopg://user:password@host:5432/korofarm"
alembic upgrade head
python -m app.infrastructure.database.seed
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the four initial endpoints.

## Current planning endpoints

- `POST /requirements/{id}/plan` creates one immutable initial plan. It reserves exactly the required committed quantity where possible, then a 20% standby target. A second initial plan request returns `409` rather than double allocating lots.
- `GET /requirements/{id}/assurance` reports committed and standby supply separately, current coverage health, source allocations, parish concentration, and the immutable committed-supply cost snapshot.

Landed cost is calculated for committed allocations only. Standby supply reserves capacity but does not yet incur operational pickup, handling, or transport cost in the buyer-plan snapshot.

## Supply risk indicators

Each finalized plan, including a recovery plan, receives an immutable `risk-v1` snapshot. It is a deterministic structural assessment, not a prediction or a farmer score. The policy is defined in `app/risk/application/calculator.py` (`RiskPolicy`): HIGH is triggered by incomplete coverage, farmer concentration above 35%, parish concentration above 70% with standby below 15%, low standby plus low replacement depth, or average confidence below 0.67. MEDIUM thresholds are 25% farmer concentration, 55% parish concentration, 20% standby, and 30% replacement depth. Percentages are on a 0–100 scale. `GET /requirements/{id}/assurance` includes the latest snapshot; `GET /requirements/{id}/risk` returns it directly.

## Test

```powershell
python -m pytest
```

Tests use an isolated SQLite database only as a fast test double; production configuration and migrations target PostgreSQL.

## Frontend integration and authentication

The Next.js frontend uses Supabase for sign-in and sends the resulting access token to the FastAPI domain API. The API validates each bearer token with Supabase before allowing access to domain routes; `/health` remains public.

Set these variables in `src/frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_REQUIREMENT_ID=<requirement UUID>
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
