# R1 — WP2 report: supplier capacity and supply exceptions

**Branch:** `feat/r1-wp2-supply-exceptions` (from `feat/r1-trade-core` @ `68d1767`). Not merged.
**Date:** 31 October 2026.
**Scope:** your WP2 instruction of 31 October and the four policy answers that followed it (attribution, expired standby, reminders, no automatic activation).

## What now works, in plain language

- **Suppliers can say they have less, and the system believes them without rewriting history.**
  - A farmer reports what they can now supply from their own lot in the farmer portal.
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
| Race safety | A report locks the lot row (`FOR UPDATE`), the same lock that supplier acceptance takes. A report and an acceptance therefore serialize; acceptance re-checks free stock against `min(available, reported) − reserved`. Free stock is clamped at zero and acceptance never exceeds it |
| Detection | `python -m src.backend.app.worker`, deterministic, no language model. Messages are claimed with `FOR UPDATE SKIP LOCKED`. Each handler runs in a savepoint; failures are recorded and retried with backoff, and dead-lettered after 5 attempts. Timers re-check each item under a row lock |
| Idempotency | One open exception per `(kind, order)` or `(kind, request)`, enforced by a partial unique index; a duplicate or replayed message updates instead of duplicating. Exception state and order health change in the same transaction |
| Tenancy | Exceptions carry the organization. All reads filter by it, and `exception_id` is in the central path-scope resolver and the tenant-isolation sweep |
| Configuration | Deadline defaults and limits are constants in `supply/application/commitments.py` (24 h, 4 h, 48 h window, 336 h maximum) |

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
| Separate staging verification of real Supabase auth | **Established, not run** | [STAGING_AUTH_VERIFICATION.md](STAGING_AUTH_VERIFICATION.md), `npm run test:staging-auth`. It needs a staging deployment and accounts that do not exist yet |
| No LLM in detection | **Met** | The worker and exception code import no model client |

## Fixed along the way

- **Farmers saw the staff navigation.** The sidebar rendered every staff section for every role; only the command palette was filtered. It now renders the role's own sections, and an E2E assertion covers it.
- **The header bell's warning dot was always lit.** It now reflects real open exceptions, and only staff see it.
- **"Not yet covered" was misleading next to an exposure.** The figure is required minus committed, so it now says *not yet committed*; exposure is reported beside it.

## Limitations

| Severity | Limitation |
|---|---|
| High | **Real Supabase authentication is untested.** Every E2E run uses the test-only stand-in. The staging task must pass before any public deployment |
| High | **`main` is still the vulnerable pre-R1 code** and the repository is public. Neither WP1 nor WP2 is merged |
| Medium | **Reminders and escalation are in-app only.** There is no SMS, WhatsApp or email. A farmer who does not open the portal will not see a reminder |
| Medium | **The worker must run as its own process.** Without it, reports are stored and exposure is still shown, but no exception opens and deadlines are not enforced. There is no health endpoint or alert for a stopped worker |
| Medium | **Deadline defaults are code constants.** Coordinators can change individual deadlines with an audit trail, but the 24 h and 4 h defaults cannot be changed per organization yet |
| Low | **The older ingestion endpoint** (`POST /v1/ingestion/farmer-production-lots/{id}/availability`) still refuses figures below reserved stock. The farmer portal no longer uses it; it should be retired or routed through capacity reports |
| Low | **Exceptions do not trigger recovery.** By your decision, an exception only alerts; activating standby or finding new supply remains a separate human action |
| Low | **Grade A only** for orders, unchanged from WP1 |
| Low | **Static status indicators.** The header's "Synced now" and the sidebar's "Environment LIVE · System operational" are fixed text, not live checks. They predate WP2 and should be wired up or removed |
