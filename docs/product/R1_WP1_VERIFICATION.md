# R1 — WP1 verification record

**Verified commit:** `7e88eceddf50fb85936b49b2b6f0f81f2a94865a` on `feat/r1-trade-core` (not pushed). The commit that adds this document changes documentation and evidence images only.
**Date:** 29 October 2026.
**Method:** a clean checkout. A new `git worktree` at the commit (0 dirty files), a new Python venv installed from `src/backend/pyproject.toml`, `npm ci`, and a disposable PostgreSQL 17.11 instance. No files from the development working directory were used. Untracked local files such as `.env.local` and existing `.venv`/`node_modules` were absent.

## Results

| Gate | Command (run in the clean worktree) | Result |
|---|---|---|
| Backend, PostgreSQL enabled | `pytest src/backend/tests -rfEs` with `POSTGRES_TEST_DATABASE_URL` | **220 passed, 0 failed, 0 skipped** |
| Frontend typecheck | `npx tsc --noEmit -p .` | exit 0 |
| Frontend lint | `npx eslint .` | exit 0 |
| Frontend unit tests | `npx vitest run` | **33 passed** |
| Production-configured build | `next build` with an https Supabase URL and live mode | exit 0 |
| No test-auth material in build | `npm run check:bundle` | **948 files scanned, none found** |
| Fresh migrations | `alembic upgrade head` on a new empty database | exit 0 |
| Browser E2E, live stack | `playwright test -c playwright.r1.config.ts` (backend, stand-in and E2E build all from the worktree) | **9 passed** |

## Your release gates, mapped to evidence

| Gate | Evidence |
|---|---|
| **1. Outstanding work committed and re-run together** | All work is in commits up to `7e88ece`; everything above ran from a clean checkout of exactly that commit |
| **2. Test authentication cannot operate in production** | See the next section |
| **3a. Cross-organization access attempts** | `test_tenant_isolation.py`, on SQLite and PostgreSQL: reads, mutations, body identifiers, lists, planner supply, idempotency, events, header spoofing, and a sweep of every `*_id` route. E2E: another organization's **real session token** is refused (404) on 10 read/write endpoints, and the owner's state is unchanged afterwards; UI isolation is shown in screenshot 05 |
| **3b. Supplier consent and withdrawal** | `test_supplier_consent.py`; `test_state_transitions.py`. E2E: decline and withdrawal through the UI (screenshot 06); committed only after a recorded response (screenshot 03) |
| **3c. Concurrent inventory reservation** | PostgreSQL tests, 10 in total, including: two orders' acceptances racing on one lot; acceptance vs capacity edit; double acceptance of one allocation; two requirements on one lot; receipts and shipments. These are database-level by design; a browser cannot prove serialization |
| **3d. Invalid state transitions** | `test_state_transitions.py`: responding before solicitation, double solicitation, reversing or repeating an acceptance, withdrawing a commitment, acting on a withdrawn allocation, editing after planning, re-planning, cancelling with commitments, planning or soliciting a cancelled order. Each is refused and the state checked unchanged. E2E: locked terms after planning; cancellation refused with commitments (screenshot 07) |
| **3e. Persistence across independent sessions** | E2E: a reload; a second user's separate browser session seeing the same order state (screenshot 04); a change in one session appearing in another |
| **3f. Fabricated consent never valid after migration** | `test_migrations_postgres.py` migrates a pre-R1 row and confirms it becomes `UNSUPPORTED_LEGACY` with its id kept and no consent invented. `test_state_transitions.py`: legacy rows cannot be revived by responding, are not counted, are not activated by immediate or deferred recovery, and are excluded from risk snapshots |

## Gate 2 in detail: test authentication

There are two separate test-authentication mechanisms. Both now fail closed.

### 1. Backend insecure bypass (`ALLOW_INSECURE_DEMO_AUTH`), pre-existing

- It is honoured only when `APP_ENV=test`.
- With any other `APP_ENV`, unset, typos and `demo` included, the API **refuses to start** if the bypass is set. Previously `APP_ENV=demo` enabled it.
- Even under `APP_ENV=test`, the fixed bypass identity has no user record or membership. A test shows it gets 401/403 on `/requirements`, `/buyers`, `/production-lots`, `/activity`, `/me` and `/me/organizations`.

### 2. E2E auth stand-in (`src/frontend/e2e/r1/support/auth-stub.mjs`), added in WP1

- No application code imports it.
- It refuses to start without `KOROFARM_E2E_AUTH_STANDIN=1`, under `NODE_ENV=production`, or with `APP_ENV` set to anything other than `test`. It listens on 127.0.0.1 only. Tested in `authStandin.test.ts`.
- The backend refuses to start in production unless `SUPABASE_URL` is an https URL on a public host. This rejects loopback, private, link-local and `.local`/`.test`/`.internal` hosts, so the stand-in, or any local identity server, cannot back a production API.
- A production build is checked for stand-in material (`check:bundle`).

### Before and after

The same commands, run on the old and new code:

| Configuration | Before (`c26b0a0`) | After (`7e88ece`) |
|---|---|---|
| `APP_ENV=production`, `SUPABASE_URL=http://127.0.0.1:54999` | Started | Refuses to start: "production SUPABASE_URL must be an https URL" |
| `APP_ENV=demo`, `ALLOW_INSECURE_DEMO_AUTH=true` | Started; bypass enabled = True | Refuses to start: "only permitted when APP_ENV=test" |

`test_runtime_security.py` (60 tests) starts the real application in subprocesses under these and other unsafe settings and requires it to exit with `UnsafeConfigurationError`.

## Defects found and fixed during this verification

- **High:** a cancelled order could still be planned, and its open proposals could still be solicited. Now refused (409). Cancelling withdraws open proposals and solicitations and releases any held reservation.

## Remaining issues, by severity

| Severity | Issue | Note |
|---|---|---|
| Medium | If `APP_ENV` is **unset** it means `development`, so the production URL check does not run | The bypass is still impossible, because it needs `APP_ENV=test`. Production must set `APP_ENV=production`; this is documented in the README. Making "unset" mean production would change local developer setup, so it is **your decision** |
| Medium | Sign-in against your real Supabase project was not exercised | E2E uses the stand-in by design. A one-time manual sign-in on a staging Supabase project is recommended before release |
| Medium | GitHub CI (`competition-readiness.yml`) was not run in this verification | It uses `APP_ENV=test` plus the bypass, which remains valid. It has not been executed since these changes |
| Medium | The offline demo replay (`lib/demoApi.ts`) still shows the pre-R1 flow (`plan.created`, no consent step) | Technically separate (no backend, labelled demo), but it no longer mirrors live behaviour. This is relevant to your rule 1 |
| Medium | The planner proposes only for Grade A orders | Hardcoded in `_eligible`; pre-existing |
| Medium | Supplier capacity reductions (decision 2) not built | Scheduled first in the next package, per your choice |
| Low | `scripts/reset_demo.py` still accepts `APP_ENV=demo` | A destructive local script, not part of authentication; it already refuses production-like database names |
| Low | Alembic `path_separator` deprecation warning | Pre-existing configuration |

## Local state after verification

- **Clean worktree.** It remains at `C:\Users\Lecturer\KoroFarm-wp1-verify`, detached at `7e88ece`, with its own venv and `node_modules`. It can be removed with `git worktree remove --force C:\Users\Lecturer\KoroFarm-wp1-verify`.
- **Servers.** All E2E servers were stopped. The disposable PostgreSQL is stopped with its data kept.
- **Your development checkout.** `src/frontend/.next` holds an E2E-configured build; rebuild before `next start`. Your servers on ports 3000 and 8000 were not touched.
- **Logs.** Verification logs are in the session scratchpad: `verify/verify.log`, `verify/e2e.log`, `verify/playwright.log`.
