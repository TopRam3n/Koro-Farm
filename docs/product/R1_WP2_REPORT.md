# R1 — WP2 report: supplier capacity and supply exceptions

**Branch:** `feat/r1-wp2-supply-exceptions` (from `feat/r1-trade-core` @ `68d1767`). Not merged.
**Date:** 31 October 2026.
**Scope:** your WP2 instruction of 31 October and the four policy answers that followed it (attribution, expired standby, reminders, no automatic activation), and the corrections from your WP2 technical review (see [Technical review corrections](#technical-review-corrections)).

## What now works, in plain language

- **Suppliers can say they have less, and the system believes them without rewriting history.**
  - A farmer reports what they can still supply from their own lot in the farmer portal, not counting anything already delivered.
  - A coordinator can relay a farmer's report on the suppliers page, but must say how the farmer told them and how it was attested.
  - Every report is stored permanently with who recorded it, for which supplier, the original source, the channel, the time it applies from, evidence, attestation and verification status. A coordinator's relay is marked coordinator-attested; it never appears as the farmer's own confirmation.
  - A report that arrives after a newer one is kept but not applied.
- **A shortfall is shown, not hidden or "fixed".** When reported capacity drops below what suppliers have already accepted:
  - every acceptance stays on record exactly as it was;
  - the uncovered part is shown separately as **exposed**, attributed to the most recent acceptance first;
  - the order turns *at risk* and one **capacity shortfall** exception opens, even for a small difference;
  - nothing is activated automatically;
  - a reduction that still covers every acceptance only lowers what is free for new orders.
  - When capacity is restored, the exposure clears and the exception closes by itself.
- **Supplier requests have deadlines, and silence means nothing.**
  - The default is 24 hours, or 4 hours when delivery starts within 48 hours.
  - The farmer sees each request and its reply-by time in their portal and can accept or decline there.
  - At the half-way point an in-app reminder appears on the farmer's request and on the coordinator's order.
  - At the deadline the request lapses, any stock held for it is released, and a *supplier reply overdue* exception opens. The lapse is never recorded as acceptance, refusal or permission. The coordinator can ask again.
  - A coordinator can change a deadline; the change and the reason are recorded.
- **Expired standby is retired honestly.** A standby authorization past its end date stops being usable and releases its stock, and the expiry is recorded as degraded contingency. An exception opens only when the remaining authorized standby can no longer cover the recovery need. Committed supply is never described as lost.
- **The coordinator sees it without refreshing.**
  - An order page shows these quantities separately: committed, currently covered, exposed, authorized standby, standby uncovered, expired standby, awaiting supplier, proposed and not yet committed.
  - Each supplier row shows its exposure and reply-by time.
  - Exceptions appear on the order and on a new **Needs attention** page. The header bell links there and lights only when exceptions are open; it was previously a decorative dot.
  - Exceptions can be acknowledged. Manual resolution is refused for a capacity shortfall while exposure remains.

## How it works

| Concern | Design |
|---|---|
| Durability | The capacity report, its domain event and its outbox message are written in one transaction (`supply/application/capacity.py`) |
| Race safety | A report locks the lot row (`FOR UPDATE`), the same lock that supplier acceptance and receipts take. Reports, acceptances and receipts on a lot therefore serialize; acceptance re-checks free stock against `min(available, ceiling) − reserved`. Free stock is clamped at zero and acceptance never exceeds it |
| Detection | `python -m src.backend.app.worker`, deterministic, no language model. Messages are claimed with `FOR UPDATE SKIP LOCKED`. Each handler runs in a savepoint; failures are recorded and retried with backoff, and dead-lettered after 5 attempts. Timers re-check each item under a row lock |
| Idempotency | One open exception per `(kind, order)` or `(kind, request)`, enforced by a partial unique index; a duplicate or replayed message updates instead of duplicating. Exception state and order health change in the same transaction |
| Tenancy | Exceptions carry the organization. All reads filter by it, and `exception_id` is in the central path-scope resolver and the tenant-isolation sweep |
| Configuration | Deadline defaults and limits are constants in `supply/application/commitments.py` (24 h, 4 h, 48 h window, 336 h maximum) |
| Monitoring | Each worker tick writes a heartbeat. `GET /health/worker` (for uptime probes; 503 unless operational) and `GET /system/status` (staff; organization backlog) derive the state in `assurance/application/operations.py` |

## Quantity meanings

| Quantity | Meaning | Changed by |
|---|---|---|
| `expected_quantity_kg` | The declared harvest | Lot declaration (create or edit, with provenance) |
| `available_quantity_kg` | Planning availability: the most the platform may plan from the lot, delivered stock included | Declarations, and a farmer's own capacity report offering more (recorded as `availability_raised_from_kg`). A coordinator-relayed report never raises it; no report lowers it |
| `reserved_quantity_kg` | Held by accepted commitments, authorized standby and marketplace orders, delivered stock included | Acceptance, withdrawal, expiry, recovery, marketplace orders. Receipts do not release it |
| delivered | Received against the lot's allocations (`received_sublots`), from any allocation | Receipts |
| `reported_capacity_kg` | Capacity ceiling from the latest applied report: delivered at the time of the report plus what the supplier said they could still supply | Applied capacity reports only. Later receipts move stock from "still to supply" to "delivered" and leave the ceiling unchanged |
| capacity report `reported_capacity_kg` | What the supplier said they could still supply, as entered; the report also stores `delivered_at_report_kg` | Immutable |

Derived:
- effective capacity = min(planning availability, ceiling);
- free stock = max(0, effective capacity − reserved);
- delivered quantity is always covered;
- the rest of the ceiling covers the undelivered part of commitments, earliest accepted first, then authorized standby, earliest authorized first;
- exposure is the undelivered committed quantity left uncovered.

A report can never ask for more than the declared harvest minus what has been delivered.

## Completion criteria

| Requirement | Status | Evidence |
|---|---|---|
| Capacity reporting by farmers and authorized coordinators, fully attributed, never fabricating confirmation | **Met** | `test_capacity_exceptions.py` (authorization, attribution, relay requires source and attestation); E2E screenshot 10 |
| Every report an immutable event; exception on any shortfall of confirmed commitments; non-threatening reductions only change availability; commitments preserved, exposure separate | **Met** | `test_capacity_exceptions.py` (no exception while covered; exposure with commitments preserved; latest-first attribution; restore); E2E tests 2 and 4; screenshot 11 |
| Standby expiry policy | **Met** | `test_capacity_exceptions.py` (expiry with and without recovery impact) |
| Deadlines: 24 h / 4 h defaults, configurable with audit, reminders, escalation, silence never acceptance | **Met** | `test_capacity_exceptions.py` (default, urgent, custom, audited change, reminder, expiry, late response refused, ask again); farmer inbox test in `test_supplier_consent.py`; E2E test 1; screenshot 09 |
| Race-safe against acceptance; no negative free stock; no new over-reservation | **Met** | PostgreSQL: report vs acceptance, concurrent reports; `test_capacity_exceptions.py` (no over-reservation) |
| Durable reports and outbox; retry-safe worker; idempotent exceptions; atomic exception and order state | **Met** | PostgreSQL: concurrent workers open exactly one exception; duplicate events; dead-lettering |
| Tenant isolation and meaningful consent | **Met** | `test_tenant_isolation.py` sweep includes exceptions; E2E test 3 (other organization sees nothing) |
| Committed, covered, exposed and standby shown separately | **Met** | Order page; screenshot 11 |
| Exceptions visible without manual refresh | **Met** | E2E test 2 asserts the exposure and exception appear on an already-open page with no navigation |
| Tests: database concurrency, duplicate events, stale reports, authorization, browser E2E | **Met** | See [R1_WP2_HANDOFF.md](R1_WP2_HANDOFF.md) for counts and the clean-checkout and CI runs |
| Review 1: standby uncovered never double counted | **Met** | `test_capacity_accounting.py` (several standby allocations on one lot, across two orders and within one order; standby on separate lots) |
| Review 2: reports cannot recreate stock removed from planning; quantities documented; lifecycle tests | **Met** | `test_capacity_accounting.py` (declared reduction not restored by a relay; full and partial delivery; receipts after a report; harvest-minus-delivered limit; farmer's own increase) |
| Review 3: worker liveness, overdue processing and dead-letter detection | **Met** | `test_worker_monitoring.py`; E2E monitoring test (live probe returns 200 with the worker running; status refused without sign-in) |
| Review 4: truthful status indicators | **Met** | `systemStatus.test.tsx` (degraded, unavailable, farmer); screenshot 11 |
| Separate staging verification of real Supabase auth | **Established, not run** | [STAGING_AUTH_VERIFICATION.md](STAGING_AUTH_VERIFICATION.md), `npm run test:staging-auth`. It needs a staging deployment and accounts that do not exist yet |
| No LLM in detection | **Met** | The worker and exception code import no model client |

## Technical review corrections

1. **Standby uncovered was double counted. Fixed.**
   - Before: the order view added, for each standby allocation, the smaller of its quantity and its whole lot's shortfall. Two 40 kg standby allocations on a lot with a 30 kg shortfall therefore reported 60 kg.
   - Now: the lot's remaining capacity is assigned to each standby allocation in turn (earliest authorized first), and each order sums only its own allocations' uncovered shares. The total across orders equals the lot's real shortfall.
   - The regression tests failed on the old code.
2. **Capacity accounting had two conservation defects. Both fixed.**
   - *A report could recreate stock a declaration had removed.* A report set planning availability to the reported figure whenever it covered reserved stock. A coordinator's relay of an old figure therefore restored stock the coordinator had just declared sold elsewhere. Now no report lowers availability (the ceiling does that), and only the farmer's own report can raise it. That raise is recorded on the event.
   - *Delivered stock was counted as if it were still in the field.* Receipts never left the lot's figures, so a report was read as the lot's total. A farmer who had delivered 200 kg and then said "100 kg left" opened a false 100 kg shortfall on an order being fulfilled. Now a report means what can still be supplied, and the ceiling adds what had been delivered when the report was made. Delivered stock is always covered and never offered again, and a report cannot exceed the harvest minus deliveries.
   - Receipts now take the lot lock, so they serialize with reports. The worker re-checks the lot after each receipt, so an exception closes once deliveries cover it.
   - Six of the eight new tests failed on the old code.
3. **Worker reliability: done.**
   - Heartbeats are recorded on every tick.
   - A readiness probe (`/health/worker`, 503 unless operational) detects a stopped or never-started worker, overdue outbox processing, overdue deadlines and dead letters. Signed-in staff get the same status with their organization's counts.
   - The worker logs an error once per degraded condition.
   - `/health` is documented as API-process-only.
4. **Status indicators: made truthful.**
   - The header's "Synced now" and the sidebar's "System operational" were fixed text. Both now show the real monitoring status for staff, or "status unavailable" when it cannot be read.
   - A banner lists the reasons whenever monitoring is degraded.
   - Farmers and buyers see no staff status.
5. **Release gates: kept.** The staging Supabase verification remains mandatory. Nothing is merged or deployed.

## Fixed along the way

- **Farmers saw the staff navigation.** The sidebar rendered every staff section for every role; only the command palette was filtered. It now renders the role's own sections, and an E2E assertion covers it.
- **The header bell's warning dot was always lit.** It now reflects real open exceptions, and only staff see it.
- **"Not yet covered" was misleading next to an exposure.** The figure is required minus committed, so it now says *not yet committed*; exposure is reported beside it.

## Remaining work

### Mandatory before any public deployment or pilot

| Item | Why |
|---|---|
| **Run the staging Supabase verification** (5 of 5) | Real sign-in, refresh, cross-organization access and sign-out are untested; every run so far uses the test-only stand-in |
| **Review and merge WP1, then WP2** | `main` is still the vulnerable pre-R1 code, and the repository is public |
| **Deploy the worker as a supervised service and point an uptime monitor at `/health/worker`** | The probe and in-app banner exist, but paging someone depends on the deployment wiring them to an alerting service |

### Later enhancements (not required to close WP2)

| Item | Note |
|---|---|
| SMS or WhatsApp reminders | Reminders and escalation are in-app only; a farmer who does not open the portal will not see one |
| Organization-wide deadline policy | Individual deadlines can be changed with an audit trail; the 24 h and 4 h defaults are code constants |
| Retire the legacy ingestion availability endpoint | `POST /v1/ingestion/farmer-production-lots/{id}/availability` is no longer used by the portal and still refuses figures below reserved stock |
| Marketplace reservations in exposure | Exposure covers supplier commitments and standby. A capacity cut below stock reserved by marketplace orders lowers free stock but does not open an exception |
| Exceptions do not trigger recovery | By your decision. Activating standby or finding new supply stays a separate human action (WP3 must keep this) |
| Grade A only for orders | Unchanged from WP1 |
