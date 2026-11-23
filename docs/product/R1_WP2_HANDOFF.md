# R1 — WP2 handoff

**Branch:** `feat/r1-wp2-supply-exceptions` (built on `feat/r1-trade-core` @ `68d1767`), pushed to `origin` (`github.com/TopRam3n/Koro-Farm`, public). Not merged; nothing deployed.
**Code verified:** `78ad576da0df727940e1bde542feadbc803a816c`. It contains:
- the WP2 backend (`866a0ee`);
- screens, E2E, CI and docs (`134cbaf`);
- the technical review corrections (`78ad576`).

**CI:** **green** on `78ad576`: run [41179879009](https://github.com/TopRam3n/Koro-Farm/actions/runs/41179879009), job `verify`, every step passed (31 Oct 2026, finished 07:19 UTC). The previous head `134cbaf` was also green (run [41177853227](https://github.com/TopRam3n/Koro-Farm/actions/runs/41177853227)). The commit that adds this document contains documentation only.

What was built, the review corrections and the quantity definitions: [R1_WP2_REPORT.md](R1_WP2_REPORT.md).

## Final clean-checkout verification of `78ad576` (31 October 2026)

Method as before:
- a new `git worktree` at the commit (0 dirty files, no `.env` files present);
- a new venv installed from `src/backend/pyproject.toml`;
- `npm ci`;
- the disposable PostgreSQL 17 instance;
- a freshly created and migrated E2E database, including migrations `0020` and `0021`.

| Gate | Result |
|---|---|
| Backend on PostgreSQL (`pytest src/backend/tests -rfEs`) | **306 passed, 0 skipped** |
| `tsc` / `eslint .` | exit 0 / exit 0 |
| Vitest | **39 passed** |
| Production-configured build plus `check:bundle` | exit 0; 964 files scanned, no test-auth material |
| `alembic upgrade head` (fresh) plus `seed_e2e` | exit 0 / exit 0 |
| Browser E2E with the worker running (`npm run test:e2e`) | **17 passed** |

The run changed one tracked file, `src/frontend/next-env.d.ts`, which `next build` regenerates. The worktree was then removed. It held only generated files: venv, `node_modules`, build output, test reports and screenshots; copies of the screenshots are in `docs/product/evidence/wp2/`.

## Test results reconciled

| Run | Commit | Backend | Vitest | E2E | Notes |
|---|---|---|---|---|---|
| Clean checkout | `134cbaf` | 282 | 36 | 16 | Before the review |
| CI 41177853227 | `134cbaf` | pass | pass | pass | |
| Local working tree | before `78ad576` | 306 | 39 | 17 | Same code as below |
| Clean checkout | `78ad576` | 306 | 39 | 17 | Final |
| CI 41179879009 | `78ad576` | pass | pass | pass | Final |

The review added:
- **Backend +24** (each runs on SQLite and PostgreSQL): `test_capacity_accounting.py`, 8 tests; `test_worker_monitoring.py`, 4 tests.
- **Vitest +3:** `systemStatus.test.tsx`.
- **E2E +1:** the live monitoring check.
- **One changed test:** a WP2 test asserted the old rule that a reduction lowered planning availability, so it now asserts free stock instead.

Six of the eight accounting tests failed on the code before the fix. No test was skipped or retried in any run listed.

The tests run locally during development were unchanged code at each point. One local E2E run failed with "page couldn't load" because a server from my earlier run was still serving an older build on port 3100. My run script now frees the ports before and after each run. That failure was not a product defect.

## What CI verifies (`.github/workflows/competition-readiness.yml`)

| Stage | What it checks |
|---|---|
| Backend tests | PostgreSQL 17 |
| Frontend checks | Lint, typecheck and unit tests |
| Production build | Built with production settings, then `check:bundle` |
| Database | Fresh database, migrations to head, E2E seed |
| E2E stack | Auth stand-in, API and the exception worker. The wait fails if the worker process exits |
| Browser E2E | Full suite, including `/health/worker` returning 200 from the running worker |

## Evidence

| Screenshot | Shows |
|---|---|
| `evidence/wp2/09-farmer-request-with-deadline.png` | The farmer's own request with its reply-by time; farmer navigation only |
| `evidence/wp2/10-farmer-reports-reduced-capacity.png` | The farmer reports what they can still supply |
| `evidence/wp2/11-exposure-and-exception-live.png` | The open order page without a reload: 300 kg committed, 180 kg covered, 120 kg exposed, an open exception, and "Exception monitoring running" from the live worker heartbeat |
| `evidence/wp2/12-needs-attention.png` | Acknowledged exception; manual resolution refused while exposed |

## Mandatory before any public deployment or pilot

| Item | Status |
|---|---|
| Staging Supabase verification (`docs/product/STAGING_AUTH_VERIFICATION.md`, 5 checks) | **Not run.** It needs a staging deployment, three accounts and one order |
| Review and merge WP1, then WP2 | Waiting for you; `main` is the vulnerable pre-R1 code in a public repository |
| Run the worker as a supervised service and point an uptime monitor at `/health/worker` | Probe, status endpoint, banner and logs are built; wiring them to an alerting service is deployment configuration |

## Later enhancements

None of these is needed to close WP2; details are in the report:
- SMS or WhatsApp reminders;
- an organization-wide deadline policy;
- retiring the legacy ingestion availability endpoint;
- marketplace reservations in exposure;
- grades other than A.

## Next

The proposed WP3 architecture is in [R1_WP3_ARCHITECTURE_PROPOSAL.md](R1_WP3_ARCHITECTURE_PROPOSAL.md). It needs four decisions from you, including whether to remove the two pre-R1 paths that activate authorized standby without a coordinator's approval.
