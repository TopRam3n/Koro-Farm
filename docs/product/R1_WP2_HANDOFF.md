# R1 — WP2 handoff

**Branch:** `feat/r1-wp2-supply-exceptions` (built on `feat/r1-trade-core` @ `68d1767`), pushed to `origin` (`github.com/TopRam3n/Koro-Farm`, public). Not merged; nothing deployed.
**Code verified:** `134cbaf309b27e25889515eb8543e1cbfd397ce7` (backend in `866a0ee`, screens, E2E, CI and docs in `134cbaf`).
**CI:** **green** on `134cbaf`: run [41177853227](https://github.com/TopRam3n/Koro-Farm/actions/runs/41177853227), job `verify`, every step passed (31 Oct 2026, finished 06:49 UTC). The commit that adds this document contains documentation only.

What was built and why: [R1_WP2_REPORT.md](R1_WP2_REPORT.md).

## Clean-checkout verification of `134cbaf` (31 October 2026)

Method as for WP1: a new `git worktree` at the commit (0 dirty files, no `.env` files present), a new venv installed from `src/backend/pyproject.toml`, `npm ci`, the disposable PostgreSQL 17 instance, and a freshly created and migrated E2E database.

| Gate | Result |
|---|---|
| Backend on PostgreSQL (`pytest src/backend/tests -rfEs`) | **282 passed, 0 skipped** |
| `tsc` / `eslint .` | exit 0 / exit 0 |
| Vitest | **36 passed** |
| Production-configured build plus `check:bundle` | exit 0; 964 files scanned, no test-auth material |
| `alembic upgrade head` (fresh) plus `seed_e2e` | exit 0 / exit 0 |
| Browser E2E with the worker running (`npm run test:e2e`) | **16 passed** (4 new WP2 tests) |

The run changed one tracked file, `src/frontend/next-env.d.ts`, which `next build` regenerates. The worktree was then removed: it held only generated files (venv, `node_modules`, build output, test reports and screenshots; copies of the WP2 screenshots are in `docs/product/evidence/wp2/`).

## What CI now verifies (`.github/workflows/competition-readiness.yml`)

As for WP1, plus the following: the E2E stage starts the supply-exception worker, and the health wait fails if the worker process has exited. The worker log is uploaded with the other logs.

## Evidence

| Screenshot | Shows |
|---|---|
| `evidence/wp2/09-farmer-request-with-deadline.png` | The farmer's own request, its reply-by time, and that silence is never taken as an answer. The farmer sees only the farmer navigation |
| `evidence/wp2/10-farmer-reports-reduced-capacity.png` | The farmer's capacity report through the portal |
| `evidence/wp2/11-exposure-and-exception-live.png` | The coordinator's already-open order page after the report, without a reload: 300 kg committed, 180 kg covered and 120 kg exposed, an open capacity shortfall exception, and nothing activated |
| `evidence/wp2/12-needs-attention.png` | The organization's exception list after acknowledgement, with manual resolution refused while exposure remains |

## Running it

- **API and worker:** see the root `README.md`. The worker is `python -m src.backend.app.worker` with the API's environment. It must run for exceptions and deadlines to work.
- **Browser E2E:** see `src/frontend/e2e/r1/README.md`. It now includes the worker step and the farmer account.
- **Staging auth gate:** `docs/product/STAGING_AUTH_VERIFICATION.md`, run with `npm run test:staging-auth`.

## Outstanding risks

| Severity | Risk | Recommendation |
|---|---|---|
| High | Real Supabase sign-in, session refresh, cross-organization access and sign-out are unverified. All runs use the test-only stand-in | Provision staging and the three accounts, then run the staging task. Do not deploy publicly until it passes 5 of 5 |
| High | `main` is the vulnerable pre-R1 code in a public repository | Review and merge WP1, then WP2, when you are ready |
| Medium | Nothing alerts anyone if the worker stops | Add a worker heartbeat and an alert before production |
| Medium | Reminders and escalation are in-app only | Add a messaging channel (SMS or WhatsApp) in a later package |
| Medium | Deadline defaults (24 h / 4 h) are code constants | Make them organization settings if coordinators need different defaults |
| Low | The legacy ingestion availability endpoint still refuses figures below reserved stock | Retire it or route it through capacity reports |
| Low | "Synced now" and "System operational" are static text | Wire them to real checks or remove them |
| Low | Orders support Grade A only | Unchanged from WP1 |

## For WP3

Exception detection is deterministic and complete without a language model. Agent orchestration (WP3) can read `GET /exceptions` and the order assurance read model. It must keep to the same rules: no supply is activated, and no supplier confirmation is recorded, without a human decision.
