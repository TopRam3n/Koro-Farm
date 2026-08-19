# KoroFarm Supply Assurance Foundation

This is the initial backend foundation for the Caribbean Agricultural Supply Assurance MVP. It includes deterministic production-lot planning, committed and standby reservations, and immutable landed-cost snapshots. Agent orchestration, recovery, physical reconciliation, and trade evidence remain deliberately deferred.

## Prerequisites

Python 3.11+ and PostgreSQL are required for the application database. Copy `.env.example` to `.env` or set `DATABASE_URL` to a standard PostgreSQL URL. The application does not depend on Supabase-specific APIs.

## Run

```powershell
python -m pip install -e ".[dev]"
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

## Test

```powershell
python -m pytest
```

Tests use an isolated SQLite database only as a fast test double; production configuration and migrations target PostgreSQL.
