# R1 — WP3 handoff

**Branch:** `feat/r1-wp3-agent-orchestration`
- Built on `feat/r1-wp2-supply-exceptions` at `6edff96`.
- Pushed to `origin` (`github.com/TopRam3n/Koro-Farm`, public).
- Not merged; nothing deployed.

**Code verified:** `bb173d9199acbfeaece87f143a957776d2eb3a67`. The commit that adds this document contains documentation only.

**CI:** **green** on `bb173d9`: run [41228958503](https://github.com/TopRam3n/Koro-Farm/actions/runs/41228958503), job `verify`, every step passed (31 October 2026).

What was built, the role policy and each decision's implementation: [R1_WP3_REPORT.md](R1_WP3_REPORT.md). Deferred items with source references: [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md).

## Clean-checkout verification of `bb173d9` (31 October 2026)

Method:
- a new `git worktree` at the commit (0 dirty files, no `.env` files present);
- a new venv installed from `src/backend/pyproject.toml` with `[dev]` only, so the optional model package was **not** installed;
- `npm ci`;
- the disposable PostgreSQL 17 instance;
- a freshly created and migrated E2E database, including migration `0022`.

| Gate | Result |
|---|---|
| Backend on SQLite and PostgreSQL (`pytest src/backend/tests -rfEs`) | **363 passed, 0 skipped** |
| `tsc` / `eslint .` | exit 0 / exit 0 |
| Vitest | **44 passed** |
| Production-configured build plus `check:bundle` | exit 0; 966 files scanned, no test-auth material |
| `alembic upgrade head` (fresh) plus `seed_e2e` | exit 0 / exit 0 |
| Browser E2E with the worker and recovery agent running | **21 passed** |

The run changed one tracked file, `src/frontend/next-env.d.ts`, which `next build` regenerates. The worktree was then removed.

## Test results reconciled

| Run | Commit | Backend | Vitest | E2E | Notes |
|---|---|---|---|---|---|
| Clean checkout | `78ad576` | 306 | 39 | 17 | WP2 final |
| Local working tree | before `bb173d9` | 363 | 44 | 21 | Same code as below |
| Clean checkout | `bb173d9` | 363 | 44 | 21 | WP3 final |
| CI 41228958503 | `bb173d9` | pass | pass | pass | WP3 final |

**What WP3 added:**
- **Backend +57** (counting SQLite and PostgreSQL runs):
  - `test_recovery_agent.py`: 18 tests;
  - `test_recovery_model.py`: 10 tests (12 cases with parameters);
  - `test_postgres_integration.py`: new and rewritten races;
  - `test_migrations_postgres.py`: policy rows and a downgrade/upgrade round trip.
- **Vitest +5:** `recoveryTasks.test.tsx`.
- **E2E +4:** `recovery-approval.spec.ts`.

**Changed tests:** tests that asserted the removed automatic recovery were rewritten to drive the approved path and keep their original invariants:
- `test_milestone1_adversarial.py` (5);
- `test_fulfilment.py`, `test_state_transitions.py`, `test_supplier_consent.py`;
- `test_programmes_and_registries.py`;
- `test_authorization.py` (no role executes);
- `test_tenant_isolation.py` (new routes in the sweep).

The invariants they keep: exact coverage, no request counted as supply, immutable cost snapshots, rollback, and the truthful 40 kg residual.

**Faults found and fixed during the work:**
- A migration parameter-typing defect on PostgreSQL, caught by the migration test and the E2E database build.
- A stale-read bug: a locked re-read discarded an unflushed plan-version change.
- A lot holding standby was wrongly excluded from additional requests.

Two tests were flaky because the planner breaks ties on random test farmer names. They were fixed to assert totals, then run ten times in a row: 10 of 10 passed.

No test was skipped or retried in any run listed.

## Evidence

| Screenshot | Shows |
|---|---|
| `evidence/wp3/13-recovery-proposal-awaiting-approval.png` | Needs attention after a 110 kg cut: release 110 kg, activate 60 kg of standby, ask a supplier for 50 kg with the exact request text; cost, approval level, reasoning, drafts not sent |
| `evidence/wp3/14-recovery-applied-awaiting-supplier.png` | After approval: all three actions applied, exposure 0, 250 kg committed, 50 kg awaiting the supplier, timeline with agent, coordinator and gateway; the exception closed |
| `evidence/wp3/15-recovery-completed-with-timeline.png` | After the supplier's recorded acceptance: 300 kg committed, task completed, full order history |

## Model-on evaluation: not yet run

- **What exists:**
  - the adapter and the evaluation harness, `python -m src.backend.scripts.evaluate_recovery_model`;
  - eight synthetic cases, including prompt injection, invented figures, misleading claims of stock and regulatory bait.
- **What is tested:** the harness's own scoring, with scripted clients in CI.
- **What has not happened:** a real model run. This machine has no Anthropic credentials (no `ANTHROPIC_API_KEY` and no `ant` profile), so **there is no model-on evidence yet**. I have not produced or simulated any.
- **To produce it** in development or staging:
  1. `pip install "./src/backend[model]"`
  2. set `AGENT_MODEL_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and `APP_ENV=development`
  3. run the script

  It writes `docs/product/evidence/wp3/model-eval/recovery-model-eval-<time>.json`. It exits non-zero on any unsafe validated outcome or model error.

## Mandatory before any deployment or pilot

| Item | Status |
|---|---|
| Staging Supabase verification (`STAGING_AUTH_VERIFICATION.md`) | **Not run.** Needs a staging deployment, accounts and an order |
| Review and merge WP1, then WP2, then WP3 | Waiting for you; `main` is still the pre-R1 code in a public repository |
| Worker as a supervised service, uptime monitor on `/health/worker` (now also covering recovery tasks) | Deployment configuration |
| Real model-on evaluation, if the model will be enabled in staging | Waiting for credentials. Production stays disabled until provider, data handling, security and evaluation are approved |

## Later enhancements

Not needed for WP3: SMS, WhatsApp or email notifications; organization-wide response policies; buyer-side delivery confirmation; grades other than A; marketplace reservations in exposure; retiring the legacy ingestion endpoint. Each is in the register with its owner and intended work package.
