# R1 — WP1 handoff

**Branch:** `feat/r1-trade-core`, pushed to `origin` (`github.com/TopRam3n/Koro-Farm`, a **public** repository, as you decided). Not merged to `main`.
**Code verified:** `e46e015e912bf0ff739253a883515c78a054a00a`.
**CI:** **green** on `e46e015`: run [41172752607](https://github.com/TopRam3n/Koro-Farm/actions/runs/41172752607), job `verify`, all 15 steps passed (31 Oct 2026, 05:28–05:33 UTC). The commit that adds this document contains documentation only.

## What CI verifies (`.github/workflows/competition-readiness.yml`)

1. **Backend tests on PostgreSQL 17**, Python 3.12, `APP_ENV=test`: 249 tests.
2. **Frontend lint, typecheck and unit tests:** 30 tests.
3. **A production-configured build plus `check:bundle`:** proves no test-only auth material ships.
4. **A fresh database:** schema reset, `alembic upgrade head`, two-organization seed.
5. **Browser E2E** (`npm run test:e2e`, 12 tests) against the live stack:
   - the guarded test-only auth stand-in;
   - the API with real membership authorization (no insecure bypass);
   - the E2E-configured production build.

The same gates also passed locally from a clean checkout of `377b937`. The only code change after that was the test fix in `e46e015`; see [R1_WP1_VERIFICATION.md](R1_WP1_VERIFICATION.md).

## Closing items you required

| Item | Status |
|---|---|
| **Explicit, recognized `APP_ENV`** | Done (`4d27035`). The allowed values are `development`, `test`, `staging` and `production`. A missing or unrecognized value stops startup, `staging` and `production` get every production safeguard, and the bypass works only under `test`. Local setup, CI, scripts, docs and tests are updated |
| **Re-verification after that change** | Done: clean checkout of `377b937`, then green CI on `e46e015` |
| **Branch pushed, not merged** | Done |
| **Green GitHub CI** | Done (run `41172752607`). Note that CI had been failing on every recent run, including before R1 (`release/korofarm-intelligence-clean`, 21–22 Oct) |
| **Outdated offline demo replay** | **Disabled.** The replay module, its controls, the frontend auth skip and the placeholder Supabase key are removed. A demo-mode build shows only a "replay disabled" notice. The old fixture spec is retired |
| **Verification checkout** | Removed after confirming it held only generated files (venvs, build output, regenerated reports and screenshots whose committed copies are in `docs/product/evidence/wp1/`) |
| **Real Supabase authentication as a release gate** | **Kept open.** Not verified. CI and E2E use the test-only stand-in |

## How the CI fixes were found

Recorded for transparency:
- **First push:** GitHub rejected the workflow before running any job. I had used the `runner` context in job-level `env`, where it isn't available. Fixed in `ef0d8d1`.
- **Second run:** one PostgreSQL test failed on Linux only. `test_two_requirements_cannot_reserve_the_same_lot` still asserted the pre-consent interleaving, so it passed on Windows by timing. It now asserts the invariant: exactly 100 kg committed, held by one order, recorded consent, and any refusal a stale-stock `CommitmentError`. Fixed in `e46e015`.

## Outstanding risks

| Severity | Risk | Recommendation |
|---|---|---|
| **High** | `main` still contains the pre-R1 vulnerabilities (cross-tenant reads and writes, fabricated consent ids), and the WP0 audit on this public branch now describes them | Do not deploy `main`. Review and merge `feat/r1-trade-core` soon, or keep `main` out of any environment holding real data |
| **High** (release gate) | Sign-in against a real Supabase project has never been exercised | Before any release: one manual and one scripted sign-in against a staging Supabase project, with `APP_ENV=staging` and an https project URL |
| Medium | Supplier capacity reductions (your decision 2) are not built; lot edits below reserved stock are refused | First item of WP2 |
| Medium | No automatic exception detection, durable task queue or approval workflow; the outbox is not consumed | WP2/WP3 |
| Medium | The planner proposes only for Grade A orders (hardcoded) | Decide as part of WP2 planning rules |
| Medium | A demo-mode build without Supabase settings fails at startup instead of showing the notice; no replay runs either way | Acceptable while demo builds aren't used; a lazy Supabase client would fix it |
| Medium | Fulfilment and reconciliation reads are organization-scoped but otherwise unchanged; buyer-role delivery confirmation is missing | WP4 |
| Low | GitHub warns that the actions in use target Node 20 (deprecated) and that `ubuntu-latest` will move to Ubuntu 26 | Bump action versions in a maintenance pass |
| Low | Alembic `path_separator` deprecation warning | Configuration tidy-up |

## Recommendations for WP2

**Supplier capacity changes, truthful commitment state, event-driven supply exceptions.**

1. **Model reported capacity separately from reserved capacity.** Today `available_quantity_kg` must stay at or above `reserved_quantity_kg`.
   - Add a supplier capacity report: reported quantity, effective time, provenance, and channel (farmer portal or coordinator relay).
   - Derive *exposure* = committed − reported, so commitments are never silently cancelled.
   - Free stock for new proposals becomes `min(available, reported) − reserved`, so nothing is double-reserved.
2. **Write an immutable event for every change.** `lot.capacity_reported` (for every report) and `allocation.at_risk` (per affected allocation), with organization, actor and causation ids. The `events.record_event` writer and the outbox are already in place.
3. **Persist an exception record:** type, shortfall, cause, affected order and allocations, source event, status (open, acknowledged, resolved, escalated) and dedupe key. Create it on the same transaction as the event, so a retry or replay can't duplicate it. Mark affected orders `AT_RISK`.
4. **Use event-driven detection, not a button.** A minimal outbox consumer (polling with `SELECT … FOR UPDATE SKIP LOCKED`, bounded retries, dead-letter state) opens exceptions from events. It should start deterministic and contain no language model. The agent task lifecycle and approvals are WP3.
5. **Make commitment state truthful end to end.** Each allocation should show committed, at risk (with the reported shortfall), lost, and recovery state. The order view separates committed, exposed and still-covered quantities. Supplier declines, solicitation timeouts and quality rejections feed the same exception path.
6. **Tests first, at the right level:**
   - PostgreSQL concurrency: a capacity report racing an acceptance; two reports on the same lot.
   - Idempotent exception creation under replay.
   - Tenant-isolation sweep entries for every new route.
   - E2E: a farmer reports reduced capacity, and the coordinator sees the exposure and an open exception without pressing anything.
7. **Decisions needed from you before WP2 starts:**
   - Who may report capacity: the farmer only, or coordinators on their behalf with attestation, as with lots?
   - What makes a reduction an exception: any amount, or a threshold?
   - Whether expired standby authorizations should open exceptions.
   - The solicitation timeout period.
