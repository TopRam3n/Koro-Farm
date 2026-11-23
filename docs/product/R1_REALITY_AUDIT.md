# R1 reality audit (WP0)

**Date:** 28 October 2026
**Branch:** `feat/r1-trade-core`, created from `main` at `731c45992860e964aaf483437d737c6c8f5ae70d` ("fixed auth for different roles").
**Worktree at branch creation:** no modified tracked files. Untracked files were left untouched: `docs/demo/`, `korofarm-demo-v4/`, `orgvid/`, `brag-output*/`, `.agents/`, `.impeccable/`, `src/frontend/artifacts/**`, `skills-lock.json` and similar.
**Spec:** [KoroFarm_R1_Functional_Trade_Core_Spec.md](KoroFarm_R1_Functional_Trade_Core_Spec.md)

## Status key

| Status | Meaning |
|---|---|
| **E2E** | Implemented and verified through a real browser against a live backend |
| **API** | Implemented and exercised by backend tests, not by a browser |
| **Partial** | Some of the behaviour exists; important parts are missing or unsafe |
| **Simulated** | Exists only as demo replay or a fixture-driven path |
| **Missing** | Not present |
| **Unknown** | Could not be determined from code or runnable checks |

**No workflow is classified E2E.** The browser specs in `src/frontend/e2e/` target the seeded 500 kg flow, and they were not run in this audit (see the baselines below).

## 1. Baselines run on 28 Oct 2026

| Gate | Command | Result |
|---|---|---|
| Backend tests (SQLite) | `.venv/Scripts/python.exe -m pytest src/backend/tests -q -p no:cacheprovider` | **75 passed, 9 skipped** |
| PostgreSQL concurrency tests | `POSTGRES_TEST_DATABASE_URL=… pytest src/backend/tests/test_postgres_integration.py` | **Not executed.** The local service `korofarm-postgres-test` (PostgreSQL 17) listens on port **55432**. The CI credentials from `.github/workflows` fail with `password authentication failed for user "korofarm"`, so all 9 tests error at connect. The working URL is needed from the founder |
| Frontend unit tests | `npx vitest run` (in `src/frontend`) | **16/16 passed** (4 files) |
| Frontend typecheck | `npx tsc --noEmit -p .` | **Failed, 2 errors.** (1) `src/pages/Profile.tsx:17` uses `String.replaceAll`, but the TS `lib` target is below ES2021. (2) a stale `.next/types/validator.ts` reference to `src/app/intelligence-lab/page.js`, a page that exists on `feature/agricultural-intelligence-v1` and not on `main` |
| Frontend lint | `npx eslint .` | **Passed** (exit 0) |
| Frontend production build | `npx next build` | **Failed**: "Failed to type check", on the `Profile.tsx` `replaceAll` error. **`main` does not build today** |
| Browser E2E | `npx playwright test` | **Not executed.** It requires the app served on `127.0.0.1:3000` against a live API and database. The existing specs (`competition.spec.ts`, `enterprise.spec.ts`) exercise the seeded 500 kg requirement and route navigation, not R1 journeys |

### Branch divergence

`main` and `feature/agricultural-intelligence-v1` have diverged:
- `main` has three commits the feature branch lacks: `d4211d9`, `1ed6827`, `731c459` (role-based auth, marketplace, farmer workspace, signup).
- The feature branch has `19d6b82`, which `main` lacks: the agricultural-intelligence data and Intelligence Lab, plus a reliability hotfix.

R1 is based on `main` because it carries the auth work. Merging `19d6b82` is a founder decision and is out of R1 scope.

## 2. Architecture as found

- **Backend:** FastAPI + SQLAlchemy 2, `src/backend/app/*`, wired in `app/main.py`.
  - Auth is a Supabase bearer token (`core/auth.py`).
  - `ALLOW_INSECURE_DEMO_AUTH=true` bypasses auth, but only when `APP_ENV` is `test` or `demo`.
- **Tenancy:**
  - `identity/application/authorization.py` resolves an `AuthorizationContext` (organization, role, permissions, farmer/buyer link) from the `X-Organization-ID` header and the user's active membership. The membership lookup is sound: missing, inactive and cross-tenant memberships all get an identical 403.
  - `buyers.organization_id` and `farmers.organization_id` exist (migration `0011_organization_ownership`).
  - `requirements` and `production_lots` are scoped indirectly through buyer and farmer.
  - `domain_events`, `supply_allocations`, `supply_plans`, `recovery_runs`, `received_sublots` and `shipments` have **no organization column**.
- **Database:** PostgreSQL by default (`infrastructure/database/session.py`); 14 Alembic migrations in `src/backend/alembic/versions/`. The test suite runs on in-memory SQLite (`tests/conftest.py`), so row locks (`with_for_update`) are **not exercised** outside the skipped Postgres tests.
- **Events and outbox:**
  - `DomainEvent` and `OutboxMessage` tables exist (`assurance/domain/models.py`).
  - Events carry type, aggregate, correlation id, `actor_type` and payload.
  - They lack tenant id, actor id, causation id, schema version and idempotency key.
  - **Nothing consumes the outbox**: `infrastructure/outbox/__init__.py` states it is "intentionally deferred".
- **Frontend:** Next.js 16 (`src/frontend/src/app/*`), API client `lib/api.ts`.
  - `NEXT_PUBLIC_APP_MODE=demo` routes every call to `lib/demoApi.ts`, an in-browser three-state replay.
  - In live mode the client sends a Supabase token and an `X-Organization-ID` taken from **`NEXT_PUBLIC_ORGANIZATION_ID`, a build-time constant**, not the signed-in user's choice.

## 3. Critical findings

These block R1 and must be fixed before any acceptance claim.

### C1. Tenant isolation is missing on most of the trade path (R1-F01)

`demand`, `supply`, `ingestion`, `marketplace` and `identity` scope by organization. These routers do not. They check only that the caller holds a staff role, in any organization:

| Router | Endpoints | Organization filter | Exposure |
|---|---|---|---|
| `assurance/api/router.py` | plan, assurance read, risk, events, recovery | none (`session.get(Requirement, id)`) | Staff in org B can read, plan or recover org A's requirement by id |
| `assurance/api/allocations.py` | dropout, accept, decline | none | Cross-tenant mutation of allocations |
| `fulfilment/api/router.py` | receive, grade, fulfilment summary, traceability | none | Cross-tenant mutation and read |
| `reconciliation/api/router.py` | shipments, dispatch, delivery, reconcile, passport, traceability | none | Cross-tenant mutation and read |
| `registry/api/router.py` | farmers, allocations, recovery cases, sublots, shipments, activity, compliance rules, command-center summary | none | **Global** lists: every tenant's farmers, allocations and events |
| `programmes/api/router.py` | create, list, attach | none | Cross-tenant |
| `trade_evidence/api/corridors.py` | list/get corridors | none | Cross-tenant read |
| `compliance/api/router.py` | rules | none | Probably intended as global reference data; needs a decision |

The existing tests could not catch this: `tests/conftest.py` overrides authorization with a single `PLATFORM_ADMIN` holding every permission in one organization. `docs/product/TENANCY_AND_AUTHORIZATION_BOUNDARY.md` is out of date in the other direction: it says no organization model exists, but one does.

### C2. Planning fabricates commitment and consent (Principles 2 and 4)

`supply/application/planner.py`, `finalize_plan` (lines 200–205):
- writes allocations straight to `COMMITTED` (or `STANDBY`);
- increments `reserved_quantity_kg`;
- sets **`consent_evidence_id=uuid4()`**, a random identifier with no consent record behind it.

So no supplier accepts anything before their quantity counts as committed coverage, and "authorized standby" is authorized only by a generated id. `recovery.py` then treats `consent_evidence_id is not None` as proof of authorization, as does `risk/application/calculator.py:41`.

**Consequence beyond code:** the competition film materials (`korofarm-demo-v4/v5-output/definitive/10-JUDGES-TECHNICAL-EVIDENCE-WALKTHROUGH.md`, `02-TECHNICAL-TRUTH.md`) say standby "carries a `consent_evidence_id`, the farmer's authorization recorded in advance". **That statement is not supported by the code** and must be corrected before those documents are shared.

### C3. Exception detection is manual (R1-F05)

- A supply loss enters the system only through `POST /allocations/{id}/dropout`. The UI exposes it as "Simulate N kg dropout" (`components/DemoControls.tsx`, rendered by `pages/Index.tsx`).
- A farmer lowering availability is **rejected** if it would drop below reserved stock: `ingestion/api/router.py`, `report_farmer_availability`, returns 409 "ready quantity cannot be below already reserved stock". A real supplier reduction therefore cannot create an exposure at all; it is refused.
- Nothing listens for capacity changes, missed acceptance deadlines or quality rejections.

### C4. No agent, task queue or approval step exists (R1-F09)

- There is no task model, worker, scheduler, proposal or approval record.
- `dropout(..., auto_recover=True)` executes recovery inline, inside the HTTP request.
- `actor_type="agent"` on events labels this synchronous deterministic code; no LLM or agent framework exists in the repository.

### C5. The frontend is fixture-locked

- `ControlCenterView.tsx`, `ModuleWorkspace.tsx`, `MyWork.tsx`, `pages/Index.tsx` and `pages/Notifications.tsx` take the requirement from `NEXT_PUBLIC_REQUIREMENT_ID`. In demo mode they fall back to `00000000-0000-0000-0000-000000000500`.
- There is no order list, no "new order" form, and no coordinator form for buyers, farmers or lots.

### C6. The crop column is too narrow on any Alembic-migrated database

- Migrations `0001_initial_foundation.py:17` and `0006_execution_compliance.py:16` define `crop` as `sa.Enum("GINGER", native_enum=False)`. On PostgreSQL that is **`VARCHAR(6)`**, used in `requirements`, `production_lots` and `compliance_rules`.
- The ORM enum (`domain/common/value_objects.py`) accepts nine crops, and five of them are longer than six characters: `PLANTAIN`, `CASSAVA`, `CALLALOO`, `BREADFRUIT`, `SWEET_POTATO`.
- On a migrated PostgreSQL database, inserts for those five crops fail. Tests never see this because they run on SQLite, which does not enforce VARCHAR length.
- `SCOTCH_BONNET`, which the R1 acceptance story requires, is not in the enum at all.

## 4. Workflow classification

| # | Workflow | Status | Evidence |
|---|---|---|---|
| 1 | Sign in, resolve organization and role | **API** | `identity/application/authorization.py`; `tests/test_authorization.py` (12 tests). Live login uses Supabase and was not exercised. The frontend organization id is a build constant (`lib/api.ts`) |
| 2 | Org admin invites users, approves access requests, changes roles | **API** | `identity/api/router.py`; `tests/test_access_requests.py`; UI `components/UserAccessWorkspace.tsx` (not E2E-verified) |
| 3 | Create a buyer | **Missing** | No endpoint or import creates `buyers`. Only `infrastructure/database/seed.py` writes them; access-request approval (`identity/api/router.py`) does not create a `Buyer` row. So a new order needs a pre-seeded buyer |
| 4 | Create a buyer requirement (order) | **Partial** | `POST /requirements`, and also CSV import (entity `buyer_requirements`) (`demand/api/router.py`): tenant-scoped, validated, writes `requirement.created` and an outbox row. **No UI.** Lacks product form, unit, origin, delivery terms, currency, provenance, notes and cancel. `Crop` enum is fixed to 9 crops and **has no scotch bonnet**; `Grade` is only A/B |
| 5 | Modify an order (quantity) with history | **Partial** | `POST /requirements/{id}/buyer-change` records a `BuyerOrderChange` row. No event written, no actor recorded, no other fields editable, no UI |
| 6 | Cancel an order | **Missing** | `CANCELLED` status exists; no command |
| 7 | Create a farmer (supplier) | **Partial** | Only via CSV bulk import (`POST /v1/ingestion/imports/preview` then `/imports/{id}/confirm`, entity `farmers`), which validates tenant ownership and writes `ingestion.entity_created`. No single-record command and no UI form |
| 8 | Farmer self-reports a lot | **API** | `POST /v1/ingestion/farmer-production-lots`: farmer role only, `SELF_REPORTED`, ingestion record with provenance; `tests/test_ingestion.py`. UI `components/FarmerWorkspace.tsx` (not E2E-verified) |
| 9 | Coordinator records a lot on a farmer's behalf | **Partial** | New lots: CSV import only (`production_lots` entity, farmer ownership validated); imported lots are created `AVAILABLE` with the CSV's quantity and confidence, with no declared/verified split. `POST /v1/ingestion/coordinator-observations` updates an **existing** lot with provenance and attestation; `tests/test_ingestion.py`. No single-record command and no UI form |
| 10 | Declared vs verified capacity and quality | **Partial** | `VerificationStatus` on ingestion records; lots have `availability_confidence` and `last_verified_at`, but the lot row itself does not separate declared from verified quantity |
| 11 | Plan supply (candidates, committed, standby) | **API, but violates C2** | `POST /requirements/{id}/plan` with idempotency key and dedup table; `tests/test_planner.py` (12). Fabricates commitment and consent. Not tenant-scoped (C1) |
| 12 | Solicit a supplier; supplier accepts/declines | **Partial** | `accept`/`decline` in `recovery.py` and `assurance/api/allocations.py`, used only for **replacement** supply during recovery, not for initial commitment. Timeouts and withdrawal are missing |
| 13 | Concurrent reservation safety | **API on SQLite; Postgres not run** | `with_for_update` and check constraints (`ck_lot_reserved_within_available`); 9 Postgres tests in `tests/test_postgres_integration.py` were skipped/errored in this audit |
| 14 | Detect supply loss automatically | **Missing** | See C3 |
| 15 | Record supplier dropout (manual) | **API; Simulated in UI** | `POST /allocations/{id}/dropout`; UI "Simulate dropout" in `DemoControls.tsx` |
| 16 | Recovery from standby, escalation | **API** | `recovery.py` (`dropout`, `continue_recovery`, `recover_quality_shortfall`) with locks and idempotency; `tests/test_milestone1_adversarial.py`, `test_execution_adversarial.py`. No approval step; relies on fabricated consent (C2) |
| 17 | Agent task lifecycle, approval of proposals | **Missing** | See C4 |
| 18 | Receive goods, grade accept/reject | **API** | `fulfilment/api/router.py`, `fulfilment/application/services.py`; `tests/test_fulfilment.py`. Not tenant-scoped |
| 19 | Shipment, dispatch, delivery, reconcile | **API** | `reconciliation/api/router.py`. Not tenant-scoped. Buyer confirmation as a buyer-role action needs verifying |
| 20 | Trade history / passport | **API** | `GET /farmers/{id}/trade-performance-passport`. Not tenant-scoped |
| 21 | Activity & Audit | **Partial** | Events listed globally by `registry/api/router.py` `/activity`, with no tenant filter (C1) |
| 22 | Marketplace orders (buyer reserves from a lot) | **API** | `marketplace/api/router.py`, tenant-scoped; `tests/test_marketplace.py`. Out of R1 scope per spec ("public produce marketplace"), but it **writes `reserved_quantity_kg` on the same lots** the planner uses, so it competes for capacity |
| 23 | Scenario Lab | **Simulated** (by design) | `components/ScenarioLab.tsx`, client-only |
| 24 | Demo replay of 500 kg ginger | **Simulated** (by design) | `lib/demoApi.ts` |

## 5. Manual-only and fixture-locked controls

- `components/DemoControls.tsx`: "Simulate N kg dropout" calls the real dropout API. It is shown whenever a plan exists, **in live mode as well as demo mode**.
- `NEXT_PUBLIC_REQUIREMENT_ID`, with the fallback `00000000-0000-0000-0000-000000000500`, in five screens (C5).
- `NEXT_PUBLIC_ORGANIZATION_ID`, a build-time organization header (`lib/api.ts`).
- The `Idempotency-Key` header is required by plan, recovery, receive and other commands; the UI hooks generate it (`hooks/useAssurance.ts`).

## 6. Reusable, sound foundations

These should be kept and migrated rather than rewritten:
- `AuthorizationContext` and `require_permission` (`identity/application/authorization.py`), and the `ROLE_PERMISSIONS` matrix (`identity/domain/permissions.py`).
- Tenant-scoped query patterns already used in `demand`, `supply`, `ingestion` and `marketplace`.
- Value objects (`QuantityKg`, `DateWindow`) and lot check constraints.
- The deterministic planner's eligibility and scoring (`supply/application/planner.py`), once it is changed to *propose* rather than *commit*.
- Recovery arithmetic, locking and idempotency (`recovery.py`, `CommandDeduplication`).
- Ingestion provenance (`ingestion/domain/models.py`: source channel, verification status, attestation, evidence reference).
- Separate receipt, grading, shipment, delivery and reconciliation records (`fulfilment`, `reconciliation`), which already keep physical states distinct.
- The Postgres concurrency test harness (`tests/test_postgres_integration.py`).

## 7. Out-of-date or incompatible documents

- `docs/product/TENANCY_AND_AUTHORIZATION_BOUNDARY.md` says no organization model exists; it does, partially (see C1).
- `docs/FINAL_INTEGRATION_VERIFICATION.md`, referenced in the brief, **does not exist** on this branch.
- The film and judges' materials under `korofarm-demo-v4/v5-output/definitive/` overstate consent (C2).
