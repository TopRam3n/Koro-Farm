# R1 — WP1 report

**Branch:** `feat/r1-trade-core` (from `main` @ `731c459`). **Not pushed.**
**Date:** 29 October 2026.
**Scope:** your instruction of 28 October: tenant isolation, a passing build and PostgreSQL environment, crop schema, buyer/supplier/lot/order CRUD, and evidenced solicitation and acceptance.

## What now works, in plain language

- **Each organization sees only its own data.** Two organizations are isolated on every staff screen and API route: reads, writes, related records, event history, planning and recovery. A user who belongs to several organizations must choose one; the system never guesses.
- **A coordinator can run an order end to end from the screens, with nothing pre-loaded.** They can:
  - add a buyer;
  - add farmers;
  - record each farmer's declared lot, saying how they heard (phone call, form) and with what attestation;
  - create an order for any crop in the catalogue, including scotch bonnet.

  Everything persists through refresh and is visible to a colleague in another session. Edits are versioned: a stale edit is refused rather than overwriting someone else's change. Every action appears in the order's history with who did it.
- **Supply is never assumed.**
  - The planner only proposes. Asking a supplier is recorded.
  - Supply counts as committed only after the supplier's acceptance is recorded, either by the farmer themselves or relayed by a coordinator with an attestation. Acceptance re-checks that the stock is still free.
  - Standby needs the supplier's authorization with stated activation conditions and an optional expiry.
  - The screens keep proposed, awaiting supplier, committed, authorized standby and unsupported legacy apart.
- **Old fabricated consent ids are kept but not trusted.** They are marked *unsupported legacy*. They no longer count as commitments, and recovery will not activate them.

## Completion criteria

| Criterion | Status | Evidence |
|---|---|---|
| Two organizations demonstrably isolated | **Met** | `tests/test_tenant_isolation.py` runs on SQLite and PostgreSQL. It sweeps every `*_id` route with another organization's real ids. The same tests fail 8 of 9 against the old code. E2E test 4; screenshot 05 |
| Relevant tests execute against PostgreSQL | **Met** | 145 passed on a disposable PostgreSQL 17.11 instance, stable over repeated runs. This includes 9 concurrency tests, the isolation suite, and 2 tests that run Alembic migrations on a fresh database |
| Backend tests, frontend tests, lint, typecheck, production build pass | **Met** (see note) | Backend 145 passed. Vitest 27 passed. `eslint`, `tsc` and `next build` exit 0 |
| New buyer, supplier, lot and order created through the UI | **Met** | E2E test 1; screenshot 01 |
| Persists after refresh and across authenticated sessions | **Met** | E2E tests 1 and 3; screenshot 04 |
| Order not tied to the 500 kg ginger fixture | **Met** | The live screens resolve the order from the route, the last opened order, or the latest order. The fixture id is used only in demo mode |
| Supplier acceptance genuine and recorded | **Met** | `supplier_consents` records; `tests/test_supplier_consent.py`; E2E test 2; screenshot 03 |
| Unknown / proposed / accepted / committed distinguishable | **Met** | Assurance API fields and UI state labels; screenshot 02 |
| Browser tests cover the workflow and authorization boundaries | **Met** | `src/frontend/e2e/r1/`, 4 passed on repeated runs against the live stack |

**Note on the last checks:** after the final two UI changes (no retry for 4xx errors, and the "Assembling supply" label), I re-ran `tsc`, `eslint`, `next build` and the browser E2E, and all passed. I did **not** re-run Vitest or the backend suite after those changes. The backend was untouched by them.

**About the E2E setup.** Browser sign-in uses a test-only local stand-in for the Supabase Auth endpoints (`e2e/r1/support/auth-stub.mjs`). This avoided creating accounts in your hosted Supabase project. The login page and the backend's token check are unchanged. **A sign-in against your real Supabase project has not been tested in this package.**

## Commits

| Commit | Change |
|---|---|
| `fedbd78` | WP0 audit, delta plan, spec |
| `7c5c12b` | Migration `0011` PostgreSQL fix; PostgreSQL test fixture |
| `c0fe71c` | Centralized fail-closed organization scoping; event tenancy (migration `0015`) |
| `aae2108` | TypeScript build fix |
| `38a6fdc` | Crop catalogue; crop columns widened to `VARCHAR(64)` (migration `0016`) |
| `39946d1` | Buyer, supplier, lot and order commands (migration `0017`) |
| `7e81ef4` | Recorded supplier consent; fabricated consent removed (migration `0018`) |
| `7157666` | Frontend workflows; fixture dependency removed; `/me/organizations` |
| `d1da827` | Browser E2E, evidence screenshots, UI fixes |

Key new files:
- `identity/application/tenancy.py`
- `supply/application/commitments.py`
- `assurance/application/events.py`
- `demand/api/buyers.py`
- `supply/api/farmers.py`
- `supply/api/crops.py`
- `components/trade/*`
- `hooks/useTrade.ts`
- `hooks/useActiveRequirement.ts`
- migrations `0015`–`0018`

All migrations are additive. Migration `0011` was corrected without changing the schema it produces.

## Real defects found and fixed along the way

1. **Cross-tenant data.** Planning and recovery could use another organization's farmers' stock. Idempotency keys were global, so one tenant could replay another tenant's stored result.
2. **Migrations broken on PostgreSQL.** `alembic upgrade head` failed on any fresh PostgreSQL database (migration `0011`). The PostgreSQL tests had been failing since `0011`, unnoticed, because they never ran.
3. **Crops that couldn't be stored.** Crop columns were `VARCHAR(6)`, so five crops the API accepted could not be stored on PostgreSQL.
4. **A double-accept race,** found by a PostgreSQL concurrency test. In the new acceptance code, a transaction that had waited for a row lock could act on stale state and accept twice. Fixed by refreshing the locked rows.

## Decisions I made that you should review

1. **Declared lots can now be proposed.** The planner used to ignore LOW-confidence (coordinator-declared) lots, so nothing a coordinator entered could ever be planned. Since a proposal commits nothing and the supplier's acceptance is the confirmation, I lowered the default threshold. Scoring still prefers higher confidence. To go back: `PlannerConfig.minimum_confidence = MEDIUM`.
2. **Coordinators can create orders.** `SUPPLY_COORDINATOR` gained order create and update, per spec §2.
3. **Coverage counts only recorded consent.** Existing databases will show their old commitments as *unsupported legacy*, with 0 committed, until suppliers' agreement is recorded. That is the truthful state, but anyone looking at existing data will see the numbers change.
4. **Partial shortfalls read "at risk".** An order whose supplier responses leave it short, with nothing pending, is marked *at risk*. Before that point the UI says "Assembling supply".

## Unresolved risks and limitations

- **Capacity reductions (decision 2) are not built.** Lot edits below reserved stock are still refused. Scheduled first in the next package.
- **The planner only plans Grade A orders.** This is hardcoded in `_eligible`; Grade B orders get no proposals.
- **No automatic detection, task queue, approval workflow or agent yet.** That is WP3. The outbox is still not consumed.
- **Some reads and labels are unchanged since WP0.**
  - Fulfilment and reconciliation reads are organization-scoped but otherwise unchanged; buyer-role delivery confirmation is WP4.
  - The demo replay (`lib/demoApi.ts`) still mirrors the old flow (`plan.created`, no consent step). It is offline only, but no longer matches the live behaviour.
  - The product label "SYSTEM · VERIFIED" is unchanged.
- **The local `.next` build is the E2E one.** `src/frontend/.next` currently holds a production build pointed at the E2E endpoints (API `127.0.0.1:8100`, auth stand-in `54999`). Rebuild before using `next start` with your normal settings. Your dev servers on ports 3000 and 8000 were not touched.
- **The disposable PostgreSQL is stopped, data kept.** Location: `C:\Users\Lecturer\korofarm-pg-r1-test`, port 55499. Credentials are only in `src/backend/.env.test.local`, which is gitignored. Restart command is in that file.
- **The 730 kg acceptance story has not been run.** The full scotch bonnet story (loss, standby, escalation, receipt, reconciliation) needs WP2–WP4.

## Next package (proposed)

1. **Capacity reductions (decision 2).** Record reported capacity separately from reserved stock. Write `lot.capacity_changed` and compute exposure. Mark affected orders at risk and open an operational exception, without cancelling commitments or double-reserving.
2. **WP2 contention.** Order-vs-order and order-vs-marketplace contention on the same lot, plus solicitation timeouts.
3. **Then WP3:** the durable outbox worker, the agent task state machine and the approval service.
