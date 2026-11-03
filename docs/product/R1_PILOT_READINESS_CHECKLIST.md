# R1 pilot-readiness checklist

**Purpose:** what must be true before KoroFarm R1 is used for a real operational pilot.

**How to read it:**
- Every item has an owner, a way to verify it and its current status.
- A pilot starts only when every **blocker** is done and signed off by the product owner.
- Nothing in this list is done by engineering on shared systems without the separate authorization named in the item.

**Owners:**
- **PO:** the product owner;
- **Eng:** engineering;
- **Ops:** whoever runs the deployment and the pilot database.

**Status** as of 3 November 2026.

## 1. Authentication: real Supabase (blocker)

| Item | Owner | Verify | Status |
|---|---|---|---|
| Staging deployment pointing at a real Supabase project (not the test-only stand-in) | Ops | `docs/product/STAGING_AUTH_VERIFICATION.md`, environment section | Not started |
| Sign-in, token refresh, sign-out, expired-session handling | Eng runs, PO reviews | The staging checklist, each step with evidence | Not run |
| Cross-organization access refused with real tokens (orders, deliveries, disputes, sites, reconciliations) | Eng | Staging checklist, cross-organization section; the WP4 routes are covered by `test_tenant_isolation.py` in code | Code: done. Staging: not run |
| Test-only auth stand-in absent from the deployed bundle | Eng | `npm run check:bundle` on the deployed build | Passes in CI; repeat on the staging build |

## 2. Branch review and merge (blocker; needs separate authorization)

| Item | Owner | Verify | Status |
|---|---|---|---|
| Review and merge in order: WP1 `feat/r1-trade-core` → WP2 → WP3 → model providers → WP4 `feat/r1-wp4-fulfilment-accounting` | PO authorizes; Eng merges | CI green on every merge result | Not merged. `main` is still pre-R1 code in a public repository |
| Migrations `0001`–`0025` applied to the pilot database **after** a backup | Ops, with PO authorization (this changes the pilot schema) | `alembic current` shows `0025_physical_event_times`; the backup is restorable | Not done |
| Production configuration: `APP_ENV=production`, no model provider set, `MARKETPLACE_ORDERS_ENABLED` unset | Ops | The API refuses to start with a provider in production; `GET /system/status` | Not done |

## 3. Worker supervision (blocker)

| Item | Owner | Verify | Status |
|---|---|---|---|
| `python -m src.backend.app.worker` runs under a supervisor that restarts it (systemd, a container restart policy or similar) | Ops | Kill the process and confirm it returns; `/health/worker` | Not configured |
| Uptime monitor on `/health/worker`, alerting a named person | Ops | Stop the worker and confirm the alert arrives | Not configured |
| Worker logs kept and searchable, including `stock ledger mismatch` and `monitoring degraded` lines | Ops | A forced mismatch (on staging) appears in the logs | Not configured |

## 4. Monitored exceptions and operating routine (blocker)

| Item | Owner | Verify | Status |
|---|---|---|---|
| A named coordinator checks *Needs attention* and recovery proposals daily | PO | Rota | Not assigned |
| Escalation path when monitoring is DEGRADED: `worker_not_running`, `processing_overdue`, `dead_letters`, `recovery_failed` or `stock_ledger_mismatch` | PO and Ops | The header shows the reason; a written runbook names who acts | Code: done. Runbook: not written |
| Stock-ledger findings are investigated, never repaired by hand in the database | PO and Eng | A finding stays open until a later check balances; corrections go through the audited script | Code: done |
| Flagged event sequences (debt item 26) are reviewed by a reconciler before close-out | PO | Order page, "Event times to review"; close is refused while any are unreviewed | Done (`0025`) |
| Buyer accounts are created for the pilot buyers, linked to their buyer record, so confirmation is direct where possible | Ops | A pilot buyer sees only their own deliveries at `/deliveries` | Not done |

## 5. Database backup and release-audit review (blocker)

**Authorized now:** the backup and the read-only dry run.
**Not authorized:** `--apply`. It needs a separate product-owner approval of the actual report.

Run by whoever holds pilot database access, from a machine with the repository and the backend virtual environment. Credentials come from that machine's own secret store. They are never pasted into chat, tickets or the repository.

1. **Backup.** Do it before any migration or audit.
   - Make the dump: `pg_dump --format=custom --no-owner --file=korofarm-pilot-<YYYYMMDD-HHMM>.dump "$PILOT_DATABASE_URL"`.
   - Verify it is readable: `pg_restore --list korofarm-pilot-<…>.dump | head`.
   - Restore it into a scratch database at least once, to prove it is restorable.
   - Record the file name, size, SHA-256 and storage location. That record is the **backup reference**.
2. **Migrate.** Do this only once authorized under section 2: bring the pilot database to `0025`. The audit needs the WP4 schema.
3. **Dry run.** It is read-only on PostgreSQL and cannot write.
   - Run: `DATABASE_URL="$PILOT_DATABASE_URL" APP_ENV=production python -m src.backend.scripts.release_audit --output release-audit-<date>.json`.
   - The report lists:
     - `releasable`: organization, order, allocation, farmer and lot, commitment, already released, received, undelivered reserved, release kind and reason, and whether re-verification follows;
     - `expected_lot_effects`: reserved and free stock before and after, per lot;
     - `review`: items deliberately not releasable, including any lot whose ledger does not balance;
     - `stock_ledger_mismatches`;
     - `marketplace_orders_placed`;
     - `summary_by_organization` and `totals`.
4. **Review.** The PO reviews the report with Eng.
   - Anything in `review` or `stock_ledger_mismatches` is investigated separately and is never part of an apply.
5. **Approval.** The PO records an explicit approval naming the report's `fingerprint`.
6. **Apply.** Only after step 5, in a quiet period:
   - Run: `python -m src.backend.scripts.release_audit --apply --report release-audit-<date>.json --reason "…" --approval-reference "…" --backup-reference "…"`.
   - It locks the affected orders, allocations and lots in the application's lock order, with a 10-second lock timeout.
   - It refuses if anything changed since the report.
   - It applies in one transaction or not at all, and records every release as an event naming both references.
7. **Afterwards.** Keep the apply output with the report.
   - `GET /stock-ledger` should show the lots balanced.
   - Released lots show *re-verification required* until usable capacity is confirmed.

| Item | Owner | Status |
|---|---|---|
| Backup taken, restore-tested and referenced | Ops | Not done |
| Dry-run report produced and reviewed | Ops runs; PO and Eng review | Not done; the pilot database is not reachable from the engineering workstation |
| Apply approved and run | PO approves; Ops runs | **Not authorized** |

## 6. Policy settings for the pilot (confirmed)

| Setting | Value | Source |
|---|---|---|
| `commitment_release_without_supplier_consent` | false; cannot be set through the API | [R1_WP4_DECISIONS.md](R1_WP4_DECISIONS.md), decision 2 |
| Harvest re-verification | 7 days after harvest end, all crops; exclusion from new planning only, never an expiry | Decision 3 |
| Marketplace orders | disabled; the backend fails closed | WP4 P10 |
| Model inference | disabled in production | WP3 |

## 7. Independent gate (not a pilot blocker for deterministic operation)

| Item | Owner | Status |
|---|---|---|
| Real-model evaluation with synthetic data before enabling any provider, even in staging | PO configures keys locally; Eng runs `evaluate_recovery_model` | Open. Production inference stays disabled; recovery works deterministically without it |

## 8. Known limitations accepted for the pilot

These come from the debt register:
- Grade A planning only (item 18).
- Organization-wide response windows are fixed (item 18).
- In-app supplier notifications only (item 4).
- Warehouse operators see refusal notes on the recovery panels (item 20).
