# KoroFarm Supply Assurance Platform

KoroFarm is an enterprise agricultural supply-assurance platform for buyer programmes, demand commitments, production-lot coordination, disruption recovery, fulfilment, and trade evidence. Planning is deterministic: committed and standby reservations are separate, landed-cost and risk snapshots are immutable, and physical acceptance never gets conflated with planned coverage. A quality rejection triggers the same reserve-first recovery policy as a farmer dropout; solicited supply never counts as committed until the farmer explicitly accepts.

## Prerequisites

Python 3.11+ (CI uses 3.12), PostgreSQL 17 and Node.js 22. Environment templates with placeholders only:
`src/backend/.env.example` (local backend), `src/frontend/.env.example` (local frontend) and `deploy/.env.example`
(staging stack). Copy them to their gitignored names and fill them in locally; never commit or paste real values.
The database is plain PostgreSQL (staging uses Supabase's); Supabase provides authentication. Staging setup:
`docs/product/R1_INFRASTRUCTURE_PLAN.md` and `docs/product/R1_PRODUCT_OWNER_SETUP_GUIDE.md`.

## Run

```powershell
python -m pip install -e "src/backend[dev]"
$env:APP_ENV = "development"   # required: development | test | staging | production
$env:DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/korofarm"
python -m alembic -c src/backend/alembic.ini upgrade head
python -m src.backend.app.infrastructure.database.seed   # optional: synthetic development data only
python -m uvicorn src.backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the complete API contract.

Run the supply-exception worker next to the API, with the same environment. It also runs the recovery agent (see R1 WP3 below). Exception detection is deterministic: it turns supplier capacity reports into supply exceptions through the transactional outbox, sends in-app reply reminders at the half-way point, expires unanswered supplier requests at their deadline, and expires standby authorizations past their end date. Without it, capacity reports are still stored and exposure is still shown, but no exceptions are opened and no deadlines are enforced.

```powershell
$env:WORKER_POLL_SECONDS = "2"   # optional, default 2
python -m src.backend.app.worker
```

Monitoring never assumes the worker is running. Each tick records a heartbeat.
- `GET /health/worker` (no sign-in, no tenant data) returns 200 only when monitoring is `OPERATIONAL`, and 503 with reasons otherwise. Point an uptime monitor at it; `GET /health` only says the API process is up.
- `GET /system/status` (signed-in staff) adds the organization's backlog counts.
- It reports `DEGRADED` when no worker has beaten within `WORKER_STALE_SECONDS` (default 30), a supplier update or deadline has waited longer than `PROCESSING_OVERDUE_SECONDS` (default 60), or any outbox message is dead-lettered. The app shows the same status in the header, with a banner when degraded, and the worker logs an error once per degraded condition.

## Supplier capacity and supply exceptions (R1 WP2)

- `POST /production-lots/{id}/capacity-reports` records what a supplier can still supply, not counting anything already delivered. A farmer reports for their own lots (`FARMER_PORTAL`, self-reported); a coordinator relaying it must give the original source and attestation (`COORDINATOR_RELAYED`, coordinator-attested). Reports are immutable; an older report arriving after a newer one is stored but not applied.
- A report below what is already committed keeps every commitment on record. The shortfall is reported as exposure (latest commitment first) and the worker opens one `CAPACITY_SHORTFALL` exception per order, closed automatically when capacity is restored. Nothing is activated automatically.
- Supplier requests get a reply deadline: 24 hours, or 4 hours when delivery starts within 48 hours; `PATCH /allocations/{id}/deadline` changes it with a recorded reason. A missed deadline expires the request (`RESPONSE_OVERDUE`); it is never treated as acceptance, refusal or permission to activate supply.
- `GET /exceptions`, `POST /exceptions/{id}/acknowledge`, `POST /exceptions/{id}/resolve` (refused for a capacity shortfall while exposure remains).

## Recovery agent with human approval (R1 WP3)

- Every supply exception opens, or joins, the order's single recovery task. Exceptions include supplier dropouts and quality rejections, which are recorded at once. The agent proposes options computed by deterministic tools:
  - release commitment a supplier's capacity report no longer supports;
  - activate authorized standby;
  - ask eligible suppliers;
  - escalate what is left.
- **Nothing happens until a person approves the exact proposal** (`POST /recovery-proposals/{id}/approve` with its `proposal_hash`). Supply coordinators approve ordinary proposals. Proposals with unknown or above-tolerance cost also need a procurement manager or organization administrator.
- The gateway in the worker re-verifies the approvals, the policy and current stock under row locks before applying anything. No user role can execute.
- `GET /recovery-tasks` (and `?requirement_id=` for an order's full timeline), `POST /recovery-proposals/{id}/reject`, `POST /recovery-tasks/{id}/cancel`, `GET|POST /recovery-approval-policy`.
- `POST /requirements/{id}/recovery` now only asks the agent to plan (202). `defer_recovery=false` on dropout is refused.
- **Optional model provider** (development and staging only; off by default):
  - `AGENT_MODEL_PROVIDER` is `none` (default), `minimax`, `nebius` or `anthropic`;
  - MiniMax and Nebius need `pip install "./src/backend[model]"` (the OpenAI-compatible SDK); Anthropic needs `[anthropic]`. Neither is needed for development, tests or CI;
  - each provider has its own settings, `<PROVIDER>_API_KEY`, `<PROVIDER>_MODEL` (required), `<PROVIDER>_BASE_URL` and `<PROVIDER>_TIMEOUT_SECONDS`, plus `MINIMAX_REASONING_EFFORT` and `NEBIUS_STRUCTURED_OUTPUT`;
  - base URLs must be https on the provider's documented host;
  - after a model error the agent falls back to deterministic rules and never switches provider;
  - model calls hold no database locks;
  - the API refuses to start with a provider set when `APP_ENV=production`.
- Check a provider without revealing the key: `python -m src.backend.scripts.check_model_provider`.
- Model-on evaluation with synthetic data, the same scenarios for every provider: `python -m src.backend.scripts.evaluate_recovery_model --repeats 3 --max-usd 2`. It writes JSON and Markdown reports.
- Secure setup: `docs/product/R1_WP3_MODEL_PROVIDERS_PLAN.md`, section 6.
- Details: `docs/product/R1_WP3_REPORT.md`.

## Fulfilment, reservation release and close-out (R1 WP4)

- Quantities stay separate: committed, received, accepted, rejected, dispatched, delivered, buyer-confirmed, disputed and released (`GET /requirements/{id}/fulfilment-record`). Receipts and deliveries are never edited; corrections are added beside them.
- Reserved stock is released only through `supply/application/release.py`: never what was received, and never by rewriting the agreed commitment. Released stock must be confirmed again before it is offered to another order.
- Every lot's reserved total is checked against what holds reservations on it (hourly in the worker, `LEDGER_CHECK_SECONDS`). A mismatch degrades monitoring (`stock_ledger_mismatch`) and is never repaired automatically.
- Cancelling an order with supplier commitments is a request (`POST /requirements/{id}/cancellation-requests`). It needs each supplier's recorded release agreement (or the organization's contractual right) and approval, and elevated approval after goods are received.
- Buyers confirm or dispute their own deliveries (`/deliveries`, `POST /buyer/deliveries/{id}/confirmation`); staff relay a confirmation only with the buyer's representative, channel, time and an attestation.
- Reconciliation is versioned; material corrections need a second reviewer. An order closes as `COMPLETED` only when everything is delivered, confirmed and undisputed. Otherwise a procurement manager or organization administrator closes it `CLOSED_WITH_VARIANCE` with a reason. Closing releases what was never received.
- Lots need re-verification `HARVEST_REVERIFY_DAYS` (default 7) after their harvest ends; a passed `viable_until` or a withdrawal makes them exhausted.
- Marketplace orders are off unless `MARKETPLACE_ORDERS_ENABLED=true` outside production.
- `python -m src.backend.scripts.release_audit` lists reservations that should no longer be held (dry run). `--apply` needs the reviewed report, a reason, an approval reference and a backup reference. Never run it on a shared database without approval.
- Details: `docs/product/R1_WP4_REPORT.md`.

## Current planning endpoints

- `POST /requirements/{id}/plan` creates one immutable initial plan. It reserves exactly the required committed quantity where possible, then a 20% standby target. A second initial plan request returns `409` rather than double allocating lots.
- `GET /requirements/{id}/assurance` reports committed and standby supply separately, current coverage health, source allocations, parish concentration, and the immutable committed-supply cost snapshot.
- `GET /requirements` provides bounded portfolio filtering by buyer, programme, lifecycle, and supply health.
- `POST|GET /programmes` and `GET /programmes/{id}` expose buyer-facing programme rollups without duplicating requirement truth.
- `GET /command-center/summary` aggregates requirement health, physical flow, concentration, and recent auditable activity.
- Operational registries are available at `/farmers`, `/allocations`, `/recovery-cases`, `/received-sublots`, `/shipments`, `/activity`, and `/compliance-rules`.

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

The demo-day database can be reset only when both the application mode
and database name are safe. The command refuses production-like targets:

```powershell
$env:APP_ENV = "development"   # the reset accepts only test or development
$env:DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/korofarm_demo"
python -m src.backend.scripts.reset_demo
```

The reset produces a stable synthetic portfolio: 3 buyers, 3 programmes,
16 farmers, 24 production lots, and 8 requirements. It includes covered,
at-risk, unplanned, completed disruption-recovery, and partial quality-rejection
states, plus one delivered, buyer-confirmed, evidence-backed reconciliation.
Every synthetic organisation, evidence reference, and operator-facing record
is labelled as synthetic. Re-running the seed is idempotent.

## Pre-R1 recovery demo scripts (retired)

`src/backend/scripts/e2e_recovery_demo.py` and `e2e_quality_recovery_demo.py` predate R1. They no longer run, and they describe automatic standby activation, which WP3 removed. See `docs/product/TECH_DEBT_REGISTER.md` (item 12). The approved recovery flow is shown end to end by `src/frontend/e2e/r1/recovery-approval.spec.ts`.

## Frontend integration and authentication

The Next.js frontend uses Supabase for sign-in and sends the resulting access token to the FastAPI domain API. The API validates each bearer token with Supabase before allowing access to domain routes; `/health` remains public.

Copy `src/frontend/.env.example` to `src/frontend/.env.local`. Live mode uses
the real API and demo mode is an explicit, deterministic offline fallback:

```env
NEXT_PUBLIC_APP_MODE=live
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
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

Sign in at `http://localhost:3000/login`. The API client in `src/frontend/src/lib/api.ts` reads the active Supabase session and adds `Authorization: Bearer <access-token>` to each request. Create buyers, suppliers, lots and orders from **Orders**, **Buyers** and **Suppliers & lots**; the overview screens show the order you last opened.

`APP_ENV` is required and must be one of `development`, `test`, `staging` or
`production`; the API refuses to start if it is missing or unrecognized. In
`staging` and `production` it also refuses to start unless `SUPABASE_URL` is https
on a public host with a publishable key, and unless `DATABASE_URL` is set explicitly, does not use the development
credentials and requires TLS (`sslmode=require`) for a remote host. A recovery model provider in staging also needs
`AGENT_MODEL_STAGING_APPROVAL`, the product owner's recorded approval reference. The insecure auth bypass
(`ALLOW_INSECURE_DEMO_AUTH=true`) works only with `APP_ENV=test`, for automated
tests; with any other value the API refuses to start if it is set.

The offline demo replay has been retired. A frontend built with
`NEXT_PUBLIC_APP_MODE=demo` shows only a notice that the replay is disabled.

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

## Governance and capability evaluations

Pilot accounts are invite-only. Live API requests must include the authenticated
Supabase bearer token and `X-Organization-ID`; set
`NEXT_PUBLIC_ORGANIZATION_ID` for the selected membership context. Public
self-registration is intentionally disabled.

### Farmer and customer access

Organization administrators invite an existing Supabase account from
`/admin/users`, assign its role, and link farmer accounts to a farm or customer
accounts to a buyer. The invitee signs in and accepts the one-time token at
`/signup`. `PLATFORM_ADMIN` (developer) access is internal-only and cannot be
granted through organization invitations.

Applicants can also create an account from the sign-in page and request Farmer
or Customer access. Supabase email confirmation must be enabled; only verified
accounts can submit requests. The configured `ACCESS_REQUEST_REVIEWER_EMAIL`
(no default; set it per environment, otherwise nobody can review requests) reviews the in-app queue in Users & Access.
That email must itself have an active organization membership with the
organization-admin invite permission; the email address alone does not grant
review authority. If overriding the backend setting, also set the matching
frontend `NEXT_PUBLIC_ACCESS_REQUEST_REVIEWER_EMAIL`. Approval links the account to an existing farm or buyer and
activates the membership. Developer access cannot be requested. Requests are
currently scoped to the configured pilot organization
(`DEFAULT_ORGANIZATION_ID`); do not use this as multi-tenant production
onboarding without tenant-specific organization selection and isolation tests.

Farmer accounts land in `/farmer` and submit expected crop, harvest window,
quantity, and estimated grade. A forecast is not orderable: the farmer must
separately report the kilograms ready before the lot appears in the customer
marketplace. Both actions are recorded as self-reported ingestion evidence with
low availability confidence until independently confirmed. Customer accounts
land in `/marketplace`, browse available lots, place quantity-checked orders,
and create crop/quantity availability watches. Orders reserve listed quantity
and remain subject to fulfilment; in-app alerts refresh every 30 seconds while
the marketplace is open. Email and SMS alerts are not configured.

To preview the offline farmer or customer experience only, set
`NEXT_PUBLIC_DEMO_ROLE=FARMER` or `NEXT_PUBLIC_DEMO_ROLE=BUYER` alongside the
explicit demo flags. Demo role selection is synthetic and does not authenticate
or authorize a real account.

Run the complete structured capability suite and zero-tolerance safety gate:

```powershell
python -m src.backend.scripts.evaluate_agents --release-gate
python -m src.backend.scripts.evaluate_agents --capability recovery_coordinator
python -m src.backend.scripts.evaluate_agents --test-id orchestrator-002
```

The latest JSON report is written to `tests/agent_eval/reports/latest.json`.
The architecture inventory is in `docs/agents/AGENT_ARCHITECTURE.md`; current
authorization coverage and remaining blockers are recorded in
`docs/governance/GOVERNANCE_PHASE_STATUS.md`.
