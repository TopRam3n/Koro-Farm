# KoroFarm demo-day final certification

Assessment date: 2026-09-20

## Decision

**NOT CERTIFIED FOR PRODUCTION OR CUSTOMER DATA.**

The local synthetic demo and its enterprise UI are demonstrable. Production
certification is withheld because fresh PostgreSQL migration/concurrency/reset
evidence, deployed-environment verification, live Supabase authentication, and
tenant authorization have not all passed in this environment.

Only `PASS`, `FAIL`, and `NOT TESTED` are used below.

| Gate | Result | Evidence |
|---|---|---|
| Committed enterprise UI baseline | PASS | Commit `17be6eb4412c049170aa00b7bb4549d753630cbf` |
| Backend fast suite | PASS | 44 passed |
| PostgreSQL integration suite | NOT TESTED | 9 tests skipped; server reachable on port 55432 but credentials unavailable |
| Alembic revision graph | PASS | Single head: `0009_programmes` |
| Fresh PostgreSQL migration | NOT TESTED | Authentication unavailable |
| PostgreSQL demo reset/reseed | NOT TESTED | Authentication unavailable |
| Deterministic demo seed logic | PASS | Idempotency and portfolio/scenario assertions pass in isolated test database |
| Frontend ESLint | PASS | Zero reported errors |
| Frontend TypeScript | PASS | `tsc --noEmit` completed successfully |
| Frontend component tests | PASS | 7 passed |
| Configured demo production build | PASS | 28 routes generated |
| Build without required auth/mode configuration | FAIL | Supabase configuration is required unless explicit demo mode is set |
| Local Playwright browser suite | PASS | 9 passed across hero flow, route map, command palette, Scenario Lab, and five viewports |
| In-app Browser session | NOT TESTED | No browser instance was exposed by the in-app browser runtime |
| Deployed URL smoke test | NOT TESTED | No deployed URL supplied or discovered |
| Live Supabase sign-in/session refresh | NOT TESTED | No live project credentials supplied |
| Tenant isolation | FAIL | Authentication exists; organisation ownership and authorization do not |

## Data and scenario certification

| Scenario | Result | Evidence |
|---|---|---|
| Portfolio depth | PASS | 3 buyers, 3 programmes, 16 farmers, 24 lots, 8 requirements |
| Covered demand | PASS | Multiple finalized, costed, risk-snapshotted requirements |
| At-risk demand | PASS | Deliberate capacity shortfall remains visible and is not invented away |
| Planning queue | PASS | One deliberately unplanned requirement |
| Disruption recovery | PASS | Allocation loss, recovery events, standby activation, and recovery cost delta projection |
| Quality exception | PASS | 30 kg received; 15 kg accepted and 15 kg rejected with traceable synthetic evidence |
| Failed recovery/escalation domain behavior | PASS | Existing adversarial backend tests pass |
| Completed shipment/reconciliation in demo seed | FAIL | Domain support exists, but the portfolio reset does not yet include a completed reconciled case |
| Compliance truthfulness | PASS | Only stored, sourced verification fields are exposed; empty state is explicit |

## Production blockers

1. Add organisation ownership, membership roles, server-side authorization, and
   cross-tenant isolation tests before ingesting real data.
2. Run revision `0001` through `0009` against a fresh PostgreSQL database, then
   run all 53 tests with zero skips and execute the guarded reset twice.
3. Verify live Supabase login, token expiry/refresh, logout, and unauthorized
   access against the deployed API.
4. Deploy a candidate build and rerun health, API, deep-link, refresh, console,
   mobile/tablet/desktop, and multi-session browser gates on the deployed URL.
5. Add one deterministic delivered, buyer-confirmed, evidence-backed,
   reconciled requirement to the demo reset.
6. Add structured observability, backups with restore rehearsal, rate limiting,
   error tracking, and operational runbooks before a production launch.

## Demo configuration

The offline demo is valid only when explicitly configured with
`NEXT_PUBLIC_APP_MODE=demo` and `NEXT_PUBLIC_AUTH_MODE=demo`. A production build
without Supabase values must not be treated as a live deployment. The backend
demo-auth bypass requires both `APP_ENV=demo|test` and
`ALLOW_INSECURE_DEMO_AUTH=true`.
