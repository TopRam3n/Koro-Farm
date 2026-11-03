# R1 — WP4 decision record

**Status:** WP4 accepted as engineering-complete by the product owner (review of the handoff at `f5c0c58`, green CI on `cf873cc`), subject to the pilot-readiness and release gates in [R1_PILOT_READINESS_CHECKLIST.md](R1_PILOT_READINESS_CHECKLIST.md).
**Recorded:** 3 November 2026. This record supersedes the WP4 proposal and report wherever they differ.

## Decision 1: release audit

**Authorized:**
- prepare a backup of the pilot database;
- produce a **read-only dry-run report** on it.

**Not authorized:** `--apply`. A separate, explicit product-owner approval is required after the actual report has been reviewed.

**Required of the report:**
- the affected organizations, orders and allocation IDs;
- the quantities and release reasons;
- the current stock-ledger discrepancies;
- the expected effect of each release.

**Corrections:** no ambiguous correction is applied, and no mismatch is resolved automatically.

**Implemented** (`src/backend/scripts/release_audit.py`):
- **Read-only:** the dry run runs in a READ ONLY transaction on PostgreSQL, so it cannot write. This is tested.
- **Each finding names:**
  - the organization (id and name);
  - the order (crop, grade, quantity, buyer, status);
  - the allocation (id, role, status) and the farmer and lot;
  - commitment, already released, received and undelivered reserved quantities;
  - the release kind and a plain reason;
  - whether the lot must be re-verified afterwards.
- **Report sections:**
  - expected effect per lot (reserved before and after, free stock before and after re-verification, and whether the stock may be offered to new orders);
  - a summary per organization;
  - every stock-ledger discrepancy, with organization and farmer;
  - PLACED marketplace orders.
- **Ambiguous cases are set aside:**
  - any allocation on a lot whose ledger does not balance moves to *review*, not *releasable*;
  - so do legacy reconciled orders and activated standby that still hold stock.
  - Mismatches are reported, never resolved.
- **Execution safety** (for when an apply is approved), all in one transaction:
  - it locks every row it would change, in the application's lock order (orders, then allocations, then lots, by id), with a 10-second lock timeout;
  - it rebuilds the findings under those locks;
  - it refuses unless they match the reviewed report's fingerprint exactly;
  - any failure rolls everything back.
- **Tested on PostgreSQL:** an apply racing a concurrent release releases the stock exactly once.

**Status:** the pilot database is not reachable from the engineering workstation; no connection is configured, and credentials are not to be shared in conversation. The backup and dry run are therefore prepared as a procedure (checklist section 5), to be run by whoever holds pilot database access. Nothing was run against pilot data.

## Decision 2: supplier agreements

- `commitment_release_without_supplier_consent` stays **false** for every organization.
- Until actual supplier contracts establish otherwise, a cancellation or buyer reduction that releases a binding supplier commitment requires the supplier's recorded agreement (`POST /allocations/{id}/release-agreements`).
- Contractual authority is not inferred from operational permissions. No blanket unilateral release right is authorized.

**Implemented:**
- The approval-policy API (`POST /recovery-approval-policy`) refuses unknown fields, so the flag cannot be set through it, even by an organization administrator. This is tested.
- No code path sets it to true. Every policy version is created false.
- Changing this needs a contract-backed product-owner decision and a code change.

## Decision 3: harvest re-verification

- The seven-day default stays for the initial pilot (`HARVEST_REVERIFY_DAYS=7`).
- It is **not** a physical expiry declaration. An unverified lot stays excluded from new planning until its available capacity is confirmed. Time alone never marks a lot exhausted, and existing commitments are unchanged.
- Per-crop periods are deferred to WP5. Any exception must rest on documented crop-specific handling requirements or verified pilot evidence.

## Additional requirement: technical-debt item 26 (physical dispatch time)

**Required:**
- separate the physical dispatch timestamp from the record-created timestamp;
- allow legitimate retrospective entries and preserve attribution;
- flag impossible or inconsistent physical event sequences for review;
- never rewrite historical shipment evidence.

**Implemented** (migration `0025_physical_event_times`):

**Dispatch time:**
- Dispatch accepts the time the goods physically left (`dispatched_at`); it may be in the past, but not in the future.
- The system records its own `dispatch_recorded_at` and `dispatch_recorded_by_user_id` beside it.
- `dispatch_time_basis` says what the time is:
  - **STATED:** the departure time someone gave;
  - **RECORDED:** no time was given, so it is the recording time;
  - **LEGACY:** every shipment dispatched before 0025, whose time was always the recording time.
- Legacy times are labelled, never changed.

**Other events:**
- Deliveries keep the stated `delivered_at` and gain a system `recorded_at` (NULL for legacy rows; not guessed).
- Receipts already kept a stated `received_at` beside the system `created_at`. A receipt can no longer be dated in the future.

**Flagged sequences:** computed deterministically from the records (`sequence_findings`):
- delivered before a stated dispatch;
- dispatched (stated) before produce in the shipment was received;
- delivered before produce in the shipment was received.

**What a flag does:**
- A dispatch whose time is only the recording time is not compared, so back-entered deliveries are not flagged falsely.
- Flags are shown on the order page.
- A reconciler reviews each one with a note (`POST /requirements/{id}/sequence-reviews`, `trade.reconcile`), once, attributed and evented.
- The records concerned are not changed.
- An order cannot be closed, as completed or with a variance, while a flag is unreviewed.

## Unchanged

- No merge, deployment, production model inference or change to shared pilot data without separate authorization.
- Real-model evaluation stays an independent gate.
