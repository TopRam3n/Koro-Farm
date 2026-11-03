# R1 — WP4 handoff

**Branch:** `feat/r1-wp4-fulfilment-accounting`
- Built on `feat/r1-wp3-model-providers`, with the WP4 proposal at `2d1d5dc`.
- Pushed to `origin` (`github.com/TopRam3n/Koro-Farm`, public).
- Not merged; nothing deployed. No production or pilot data was read or changed. The release audit was run only inside tests.

**Code verified:** `cf873cc`. The commit that adds this document contains documentation only.

**Commits:**
- `743bebe`: the WP4 implementation;
- `cf873cc`: fixes found by the browser run. Ended orders now resolve their open exceptions; the fulfilment figures have their own selector; the specs follow the new cancellation flow.

**CI:** **green** on `cf873cc`: run [41658626287](https://github.com/TopRam3n/Koro-Farm/actions/runs/41658626287), job `verify`, every step passed, browser E2E included (3 November 2026). The earlier run on `743bebe` ([41371191500](https://github.com/TopRam3n/Koro-Farm/actions/runs/41371191500)) failed in `npm run test:e2e`; see below.

What was built, and how each policy (P1–P11) is implemented: [R1_WP4_REPORT.md](R1_WP4_REPORT.md). Deferred items: [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md), items 17–26.

## Verification

| Gate | Where | Result |
|---|---|---|
| Backend on SQLite and PostgreSQL 17 (`pytest src/backend/tests`) | local working tree at `cf873cc` | **437 passed, 2 skipped**. The skips are the SQLite variants of the two PostgreSQL-only race tests |
| Same, from a clean checkout | new `git worktree` at `743bebe` (0 dirty files, no `.env` files), new venv with `[dev]` only | **437 passed, 2 skipped** |
| Migrations | `test_migrations_postgres.py`: fresh database, legacy backfill, downgrade to `0023` and back to head | passed (part of the totals above) |
| `tsc` / `eslint .` | local | exit 0 / exit 0 |
| Vitest | local | **49 passed** (+5: `fulfilment.test.tsx` 4, `recoveryTasks.test.tsx` 1) |
| Browser E2E, the full R1 suite with the worker running | production build from the clean worktree, disposable migrated database, test-only auth stand-in | **27 passed** (+6: `fulfilment-reconciliation.spec.ts`) |

The browser tests were run in the worktree on ports 3100, 8100 and 54999, so the dev server already running on port 3000 was not touched. Each run used a new disposable database, dropped afterwards.

## What the browser run found, and what changed

The first CI run on `743bebe` failed in `npm run test:e2e`. Run locally against the same stack, it showed:
- **A selector collision:** the new fulfilment figures reused `data-figure="Committed"`, which made the existing specs' supply-figure selectors ambiguous. The fulfilment figures now use `data-fulfilment-figure`.
- **An outdated spec:** `consent-and-boundaries.spec.ts` still expected direct cancellation to be refused with the old message. WP4 replaces it with a cancellation request (P1). The spec now checks the request, the agent's escalation for the missing supplier agreement, and that nothing changed.
- **WP4 spec timing:**
  - it filled forms before the pages had loaded;
  - it recorded a delivery dated in the future, which the API correctly refuses with 422.
- **An ended order still asking for action:** the closed order kept an open quality-rejection exception and showed "Escalation required". Closing, and an approved full cancellation, now resolve open exceptions with the outcome, keeping their records, and the page shows "Order ended". A backend test asserts it.
- **Delivery recorded before dispatch:** the run showed a delivery time earlier than the dispatch time. Dispatch records when staff pressed the button, not the physical departure, so refusing such deliveries would block legitimate back-entry. It is left unenforced and recorded as debt item 26.

## Test changes

**New:**
- `test_fulfilment_accounting.py`: 15 scenarios on SQLite and PostgreSQL, plus 2 PostgreSQL-only races (close-out against a late supplier acceptance; two simultaneous reconciliations);
- migration backfill and round-trip test;
- Vitest and E2E as above.

**Changed, each keeping its original invariant:**
- `test_execution_adversarial.py`: relayed confirmation; an unconfirmed delivery is reconciled but never completed;
- `test_ingestion.py`: a secure-link reply is a capacity report;
- `test_marketplace.py`: fail-closed test, 410 for the retired endpoint;
- `test_tenant_isolation.py`: new route identifiers;
- `test_programmes_and_registries.py`, `test_state_transitions.py`, `test_postgres_integration.py`: new service signatures and messages;
- `consent-and-boundaries.spec.ts`: as described above.

**Stock ledger:** every two-organization test now ends with the stock ledger invariant asserted. Two tests that deliberately set reserved stock directly are marked `ledger_drift_expected`.

**Known flaky test:** `test_planner.py::test_concurrent_planning_attempts_create_only_one_plan`, a SQLite file race under load, failed once in an earlier full local run. It passed 8 of 8 repeated alone and in every run listed here (debt item 23).

## Evidence

| Screenshot | Shows |
|---|---|
| `evidence/wp4/20-buyer-confirms-delivery.png` | The buyer's "My deliveries": 705 kg delivered, confirmed by the buyer in their own account |
| `evidence/wp4/21-reconciled-not-completed.png` | Reconciled, not closed: 730 required, 725 received, 705 accepted, 20 rejected, 705 delivered and confirmed; the blockers listed; the coordinator's variance attempt refused |
| `evidence/wp4/22-closed-with-variance.png` | Closed with variance by the procurement manager: the permanent 25 kg note, 5 kg released, no open exception, "Order ended" |

## Needs your decision or action before the pilot

1. **Release audit on the pilot database** (debt item 24): take a backup, run the dry run, review the report, then approve `--apply` with a reason and an approval reference. It has not been run on any shared data.
2. **Supplier terms:** whether your contracts give the organization the right to release commitments without each supplier's agreement. The default is no (`commitment_release_without_supplier_consent` false), so every cancellation or reduction needs recorded supplier agreement.
3. **Per-crop harvest re-verification periods** (P9; one 7-day setting for now).

## Independent release gates (unchanged)

| Gate | Status |
|---|---|
| Supabase staging authentication (`STAGING_AUTH_VERIFICATION.md`) | Not run; needs a staging deployment |
| Worker supervision and uptime monitoring | Deployment configuration |
| Real-model validation | Open; production model access stays disabled |
| Branch review and merge order | WP1, WP2, WP3, model providers, then WP4. Nothing merged |
