# KoroFarm Full-Stack Competition Readiness Report

Assessment date: 2026-09-05

## Executive result

The domain-critical backend, actual PostgreSQL locking, deterministic 500kg / 80kg flow, guarded reset, production frontend build, offline demo contract, and CI gate pass. The local in-app browser runtime exposed no browser, so the required Playwright run, console inspection, screenshots, projector-resolution checks, refresh/deep-link proof, and two-browser proof could not be executed in this environment. The suite and CI orchestration are implemented, but unexecuted browser acceptance remains a competition blocker.

## System

- Backend: FastAPI, SQLAlchemy 2, Pydantic, Alembic, psycopg; entrypoint `src.backend.app.main:app`.
- Frontend: Next.js 16, React 18, TypeScript, TanStack Query, Tailwind and Radix; app `/` delegates to the existing supply-assurance page.
- Database: dedicated local PostgreSQL 17 test databases on port 55432. SQLite remains a fast test double for unit tests, not concurrency evidence.
- Production target: PostgreSQL. Supabase is used only for live authentication; domain persistence uses ordinary PostgreSQL APIs.
- API configuration: `NEXT_PUBLIC_API_URL`; explicit `NEXT_PUBLIC_APP_MODE=live|demo`; explicit `NEXT_PUBLIC_AUTH_MODE=supabase|demo`.
- Environments: root and frontend example files document public configuration. Tracked `.env` and `.env.local` files were removed. Demo auth bypass requires both `ALLOW_INSECURE_DEMO_AUTH=true` and `APP_ENV=test|demo`.
- Existing tests: pytest service/API/adversarial/PostgreSQL integration suites and Vitest component/API suites.
- E2E/demo: deterministic reset, quality-recovery demo, Playwright competition suite, and GitHub Actions full-stack job.

## Baseline and final verification

| Gate | Baseline | Final |
|---|---:|---:|
| Backend pytest | 34 passed, SQLite only | 48 passed, 0 failed, 2 third-party deprecation warnings, 4.99s |
| PostgreSQL concurrency | absent | 9 race/locking cases passed inside the 48-test suite |
| Frontend tests | no tests discovered; intentional failing file misnamed | 7 passed across 2 files, 1.40s |
| ESLint | 10 warnings | passed with 0 warnings |
| TypeScript | passed | passed |
| Next production build | passed with workspace/lock warning | passed cleanly; 13 routes generated |
| npm audit | 3 vulnerabilities | 0 vulnerabilities |
| Python dependency audit | not run | no known vulnerabilities; local package correctly skipped |
| Diff integrity | not run | `git diff --check` passed; only line-ending notices |

The two remaining pytest warnings originate in FastAPI/Starlette TestClient compatibility (`httpx2` migration and an AnyIO alias), not application behavior.

## PostgreSQL

**PASS**

- Installed and used PostgreSQL 17.11, not SQLite emulation.
- Recreated `korofarm_migration_test` from zero and applied revisions 0001 through 0008 successfully.
- Fixed an overlength Alembic revision identifier and a clean-checkout Alembic import-path defect.
- Seed/reset/reseed produced the fixed requirement `00000000-0000-0000-0000-000000000500`, one requirement, and eight production lots each time.
- Reset refuses non-PostgreSQL URLs, non-test/demo `APP_ENV`, and database names without `_test` or `_demo` suffixes.
- Real concurrency cases passed for competing plans, standby recovery, solicitation acceptance, dropouts, in-progress duplicate keys, receipts, shipments, planner availability changes, and recovery versus unrelated discovery demand.
- Every PostgreSQL case rechecked `reserved_quantity_kg <= available_quantity_kg`; no duplicate supply or over-coverage was observed.

## Contract

**PASS** for the exercised application contract.

Discovered and fixed mismatches:

- The seed used an invalid non-UUID requirement ID while the frontend expected a UUID.
- Frontend buyer, destination, dates and recovery premium were static or recomputed; these now come from backend responses/snapshots.
- Decimal wire values are treated as strings and formatted, not made authoritative in JavaScript.
- Raw committed coverage was previously conflated with rejection-adjusted assured coverage; both are now explicit.
- Dropout previously completed recovery in the same command, making the required 420kg / AT_RISK state unobservable. The API now records disruption first and recovery advances separately.
- Events now have a chronological API and frontend representation.
- Material commands require and preserve idempotency keys.
- Explicit app mode prevents silent live-to-mock switching.

OpenAPI exposes 29 paths and matched the updated frontend adapters for identifiers, nullable fields, timestamps, enums, and assurance quantities. CORS preflight returned the configured localhost origin.

## Core domain invariants

| Invariant | Result | Evidence |
|---|---|---|
| Inventory never reserves above verified availability | PASS | constraints plus nine PostgreSQL races |
| Standby reserves capacity but is not committed until activation | PASS | planner/recovery tests |
| Solicited supply is not committed before acceptance | PASS | recovery and concurrent acceptance tests |
| Planning and physical quantities remain separate | PASS | API model and quality-flow assertions |
| Rejection remains visible and cannot be shipped | PASS | grading/shipment tests |
| Recovery complete means committed coverage restored | PASS | UI wording and prohibited-word checks |
| Dispatch is not delivery | PASS | state-machine validation |
| Evidence requires verified reconciliation | PASS | joins and adversarial tests |
| Risk is a heuristic label, not probability | PASS | UI and snapshot contract |
| Historical economics/risk snapshots remain authoritative | PASS | immutable backend snapshots |
| Compliance comes only from verified stored rules | PASS | filter tests and fallback search |
| Trade history is not a credit/loan decision | PASS | `BUILDING_HISTORY` / `NOT_ASSESSED` states |

## Competition flows

### 500kg / 80kg flow

**PASS at API + PostgreSQL level; browser acceptance pending.**

- Initial: required 500kg, committed 500kg, standby 100kg, COVERED.
- Dropout: lost 80kg, committed 420kg, shortfall 80kg, AT_RISK.
- Recovery: two standby fragments activated for 80kg; committed/assured coverage restored to 500kg, COVERED.
- Event order: plan created, allocation lost, requirement at risk, recovery started, two standby activations, recovery completed.
- Wording is exactly “Committed coverage restored” and explicitly says physical delivery is not yet claimed.

### Recovery failure / escalation

**PASS**

The exact adversarial case `500 - 140 + 70 + 30 = 460` ends with 40kg shortfall and `ESCALATION_REQUIRED`. No missing quantity is invented.

### Physical fulfilment

**PASS**

Receipt, grading, accepted/rejected separation, shipment, dispatch, delivery, buyer confirmation and evidence-gated reconciliation are tested. A replacement commitment does not increase accepted physical supply before receipt and grading.

### Traceability

**PASS**

Shipment-to-farmer/lot and production-lot-to-shipment routes traverse shipment sublot, received sublot, allocation, production lot and farmer. Rejected and already-consumed accepted quantities cannot enter shipment composition.

### Compliance

**PASS**

Rules are filtered by origin, destination, crop/product form, effective time, expiry, verification, issuer, verifier, source and version. Missing, expired, future, malformed and mismatched records resolve to `no_verified_rule_on_file`; invalid enum crops are rejected at validation. No LLM or generic regulatory fallback exists.

### Reconciliation

**PASS**

Reconciliation requires delivery and buyer-confirmation evidence, is idempotent, preserves different required/committed/received/accepted/delivered/confirmed values, and excludes unresolved disputes from trade evidence. Buyer-caused requirement changes are recorded separately.

### Trade performance

**PASS**

Only delivered, buyer-confirmed, verification-referenced, undisputed reconciliations contribute. Immature history reports `BUILDING_HISTORY`; financing remains `NOT_ASSESSED`.

### Economics

**PASS for arithmetic and snapshots.** Decimal calculations match backend formulas without NaN, Infinity or binary floating artifacts. Original and recovery snapshots are immutable, and positive/negative/zero deltas are supported. The unresolved commercial policy question is whether fixed pickup and transport costs apply per allocation, pickup, physical lot, route or shipment; no silent redesign was made.

### Risk

**PASS**

LOW/MEDIUM/HIGH are deterministic structural labels. COVERED + HIGH remains valid when concentration/standby resilience is weak, and the UI displays coverage and risk as separate dimensions.

### Idempotency

**PASS at backend/API and frontend component levels.** Planning, dropout, recovery, acceptance, receipt, grading, shipment composition, dispatch, delivery and reconciliation reuse logical results without duplicate events or quantities. Frontend mutation keys survive failed/retried responses and controls disable while pending. Actual rapid browser double-click remains part of the blocked Playwright gate.

### Transaction failures

**PASS**

Injected reservation, recovery and receipt failures rollback without half-created state. Retry behavior remains consistent with idempotency records.

### Network failure

**FAIL (incomplete browser proof)**

Vitest verifies offline transport, HTTP 500, malformed JSON, timeout plumbing, unknown-value rendering and no automatic mode switch. The UI does not substitute J$0, LOW risk or 0kg for unknown state, and secondary panels have error boundaries. Browser-level 5s/10s latency, stale-data labeling, connection loss after mutation, and response-lost-after-success cases were not executed.

### Offline demo

**PASS for build, serving and deterministic contract.** A production demo build served the application shell while the backend port was confirmed down. Demo mode shares the live view contract and exact 500/420/500 storyline and is visibly labeled. Interactive browser verification remains covered by the outstanding browser gate.

### Playwright

**FAIL / BLOCKED BY EXECUTION ENVIRONMENT**

`src/frontend/e2e/competition.spec.ts` and `playwright.config.ts` automate the required production-stack scenario, refresh/deep link, two-browser state, prohibited wording, and five viewports, with screenshots 01 through 05. The mandatory in-app browser runtime reported zero available browsers, so the suite and browser-console/projector checks were not executed locally. GitHub Actions installs Chromium and runs the gate against local PostgreSQL, backend and production frontend services.

### Demo reset

**PASS**

The reset safety guards were exercised, including refusal under production-like environment settings. Reset/reseed passed twice in the final clean migration rehearsal. The complete real HTTP reset-and-flow soak was run ten consecutive times.

### Soak test

- Runs: 10
- Passes: 10
- Failures: 0
- Determinism: seven events per run and one stable recovered landed cost, J$174,086.00
- Scope: real HTTP API, backend and PostgreSQL. Browser-console soak is pending Playwright availability.

## Security

- Remaining blockers: 0 found in code/configuration review.
- Remaining high findings: 0 found in code/configuration review.
- Fixed: removed tracked environment files, constrained CORS, gated insecure demo auth to test/demo, removed unsafe interpolated `dangerouslySetInnerHTML`, validated mutation bodies, and guarded destructive reset targets.
- Dependency scans: npm reports zero vulnerabilities; Python audit reports no known vulnerabilities in published dependencies.
- No database/service-role/LLM secrets are exposed through frontend public variables.

## Performance

- Assurance endpoint, 50 local calls: median 19.40ms, p95 21.92ms, maximum 27.72ms.
- Initial dashboard: three domain requests (assurance, fulfilment, events), with no accidental polling loop.
- Production static assets: 2,323,637 bytes raw (about 2.22 MiB), before transfer compression.
- No competition-impacting N+1 query or render loop was observed in the exercised path. Browser paint and interaction timing remain unmeasured because no browser was available.

## Agentic validity

The recovery system credibly qualifies as a bounded deterministic coordination agent: it retains the coverage objective, observes loss/quality events, selects only authorized standby or solicitation actions, re-evaluates coverage after each action, records an immutable event trail, and escalates when authority/capacity is exhausted. It is coordinator-triggered rather than a continuously running autonomous worker; product claims should describe bounded supply-assurance orchestration, not general AI autonomy.

## Red-team findings

Fixed BLOCKER/HIGH findings included the broken clean migration revision/import path, missing PostgreSQL concurrency evidence, uncommitted API mutations, unobservable AT_RISK transition, solicitation/commitment ambiguity, arbitrary nondeterministic dropout selection, unsafe reset risk, missing reconciliation evidence gates, non-idempotent execution commands, silent mock/live ambiguity, stale contract fields, unknown values rendered as zeros, and committed secrets/config files.

Remaining issues:

- **BLOCKER:** local Playwright/browser acceptance is unexecuted because the in-app environment has zero browsers. Run the CI browser gate or provide a browser runtime, inspect all screenshots and console output, and require a green result before judging.
- **HIGH:** browser-only network chaos and projector-resolution checks are unverified until the same gate runs.
- **HIGH:** the real Supabase sign-in path was not exercised; the competition test used the deliberately gated demo auth mode. If judging requires live auth, rehearse the real project/session separately.
- **MEDIUM:** fixed pickup/transport cost scope is a commercial policy decision.
- **MEDIUM:** the frontend retains both App Router and legacy Pages Router entry surfaces; the competition route builds correctly, but later consolidation would reduce maintenance risk.
- **LOW:** two third-party test-client deprecation warnings should be removed during the next dependency-compatibility upgrade.

## Final decision

All fixable code/data blockers found in this environment were addressed and rerun. PostgreSQL concurrency, migration, reset, tests, builds and API soak are green. Competition readiness is withheld solely because the required actual-browser acceptance and its dependent console/projector/two-session checks have not produced evidence.

KOROFARM: NOT COMPETITION READY
