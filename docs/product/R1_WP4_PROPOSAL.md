# R1 WP4 proposal: supply accounting, release policies, and physical fulfilment and reconciliation

**Status:** proposal for your review. Nothing in it is implemented.

**Branch:** `feat/r1-wp4-fulfilment-accounting`, built on `feat/r1-wp3-model-providers` at `8519a3a`.

**Inputs:**
- [the R1 spec](KoroFarm_R1_Functional_Trade_Core_Spec.md): WP4 is "physical fulfilment and reconciliation", and §6 is the second half of the adversarial story;
- [the debt register](TECH_DEBT_REGISTER.md);
- the WP1 to WP3 handoffs;
- a fresh audit of the code at `8519a3a`.

Every defect below names its source location, and I checked each one against the code.

## 1. What the audit found

The ledger that WP1 to WP3 built for supply commitments is sound. Plans propose, suppliers accept, exposure is computed, and recovery needs approval. The weak points are where that ledger meets the physical world and the end of an order's life. Stock that is reserved, delivered or confirmed can drift away from what the records say, or stay reserved forever.

### 1.1 Defects that can cause inaccurate commitments or unreconciled stock

| # | Defect | Where | Consequence |
|---|---|---|---|
| D1 | A buyer quantity change never re-checks coverage, and does not check the order's state | `demand/api/router.py:328` (`buyer_change`) | An increase leaves the order marked COVERED although it is short: no exception and no recovery. A decrease leaves commitments above the order with no release. A cancelled or reconciled order can still be changed |
| D2 | Nothing releases reservations when an order ends | No close-out path exists. `reconciliation/api/router.py` (`reconcile`) only writes figures | The undelivered remainder of commitments, authorized standby and open requests keep stock reserved after reconciliation, permanently. Over time free stock shrinks for reasons nobody can see |
| D3 | A dropout keeps the lost allocation's reservation (register item 9) | `assurance/application/recovery.py:149` | The lost kilograms stay reserved on a lot the farmer says cannot supply them |
| D4 | Orders with binding supply cannot be cancelled (register item 8) | `demand/api/router.py:275` | Coordinators must work around it, for example by recording supplier responses to get unblocked. That distorts the records |
| D5 | Receipts are accepted against any allocation, whatever its state | `fulfilment/application/services.py:29` (checks only that the allocation exists) | Produce can be received against standby that was never activated, an unanswered request, a lost or declined allocation, or a cancelled order. It then counts as delivered stock and distorts exposure and reconciliation |
| D6 | Lot edits can change grade or harvest window under live commitments | `supply/api/router.py:204` (`update_production_lot`); `ingestion/api/router.py:148` (`_apply_observation`) | A Grade A commitment can sit on a lot re-declared as Grade B, or outside the order's window, with no exception |
| D7 | Writers disagree on how lot status is computed | Legacy availability endpoint `ingestion/api/router.py:238`; `_apply_observation`; marketplace `create_order` | Some set AVAILABLE or UNAVAILABLE from available minus reserved and ignore the WP2 capacity ceiling. A lot can show AVAILABLE with no free capacity |
| D8 | Legacy availability writers bypass capacity-report rules and events (register item 1) | `ingestion/api/router.py:238` (farmer-portal availability) and `:148` (`_apply_observation`, used by observation and secure-link writes). Import confirm only creates new lots, which is a declaration, and is not affected | Availability changes without a capacity report. There is no `lot.capacity_reported` event, so no exposure re-check and no exception |
| D9 | Marketplace orders reserve stock with no way back (register item 2) | `marketplace/api/router.py:115` | No cancel, fulfil or release path; no idempotency key, so a double submit reserves twice; no event; not part of exposure. The R1 spec places a public produce marketplace **out of scope** |
| D10 | No stock ledger check | — | Nothing detects when a lot's `reserved_quantity_kg` stops matching what holds reservations on it, so drift from any of the above stays silent |
| D11 | No lot expiry (spec R1-F03: "stock becomes unavailable when expired or withdrawn") | Nothing uses `ProductionLotStatus.EXHAUSTED` | Lots long past harvest stay plannable and recoverable |

### 1.2 Fulfilment and reconciliation defects (spec WP4 and R1-F07, F08)

| # | Defect | Where | Consequence |
|---|---|---|---|
| F1 | Shipment, dispatch, delivery and reconciliation have no permission checks | `reconciliation/api/router.py:51,65,84,101,117`, included with staff dependencies only (`main.py:63`) | Any staff role, auditors included, can dispatch, record delivery and reconcile. The permissions exist but are never checked: `shipment.create`, `shipment.dispatch`, `delivery.confirm` |
| F2 | No way to create fulfilment sites | `FulfilmentNode` is created only by the demo seed | **A newly onboarded organization cannot receive anything.** This blocks a pilot |
| F3 | Buyer confirmation is a yes/no flag on the whole delivery | `Delivery.buyer_confirmed` | It cannot record that a buyer confirmed less than was delivered, as spec §6 requires. Staff set it, with no channel or attestation (register item 6) |
| F4 | The event `delivery.confirmed` is written even when the buyer has not confirmed | `reconciliation/api/router.py` (`deliver`) | The audit trail says "confirmed" when nothing was confirmed |
| F5 | Reconciliation overwrites itself | `reconcile`: `session.get(...)` then mutate | Re-running it replaces the earlier figures. This breaks spec principle 7: correct with new records, never mutate history. There are no dispute or correction records |
| F6 | Reconciliation checks too little and records too little | `reconcile` | It does not require every shipment to be delivered or every receipt to be graded. It records committed, delivered and accepted, but not received, rejected, dispatched or buyer-confirmed |
| F7 | Shipment references are unique across all organizations | `Shipment.reference unique=True` | Organization B gets a conflict for a reference organization A used, which leaks that the record exists across tenants |
| F8 | Lifecycle states are never reached | `IN_FULFILMENT` and `CLOSED` are never set | The order list cannot separate orders being fulfilled from orders being planned |
| F9 | The passport mislabels a metric | `reconciliation/api/router.py:154` | `quantity_fulfilment_rate_pct` and `fulfilment_reliability_index` both return the quality acceptance rate. That is a misleading derived claim |
| F10 | No R1 user interface for receiving, grading, shipment, delivery or reconciliation | Only a read-only legacy `FulfilmentPanel` exists | The fulfilment half of the workflow is API-only |

## 2. Scope

### 2.1 Mandatory for pilot readiness (WP4)

Each item lists acceptance criteria (AC), the code affected, migration risk and regression tests.

#### M1. Fulfilment permissions and receipt eligibility (F1, D5)
- **AC:**
  - Shipment creation needs `shipment.create`, dispatch `shipment.dispatch`, delivery `delivery.confirm`, and reconciliation a new `trade.reconcile` (coordinator, procurement manager).
  - Auditors are refused every write.
  - A receipt is accepted only for a COMMITTED allocation of an order that is not cancelled or reconciled. Anything else is refused with 409.
- **Code:** `reconciliation/api/router.py`, `fulfilment/application/services.py`, `identity/domain/permissions.py`, plus a migration that syncs `role_permissions`.
- **Migration risk:** low (additive permission rows). Existing receipts against ineligible allocations are not altered; the ledger check in M8 reports them.
- **Tests:** a role matrix for every fulfilment write; receipts refused for standby, solicited, lost, declined and cancelled-order allocations; the tenant sweep extended.

#### M2. Fulfilment sites (F2)
- **AC:** organization administrators and coordinators can create, list and deactivate fulfilment sites (name, type, parish) through the API and UI. A receipt must name an active site of the same organization.
- **Code:** a new `fulfilment/api/nodes.py`, a tenancy resolver (exists), a frontend form.
- **Migration risk:** none; the table exists.
- **Tests:** CRUD, permissions, isolation, refusal of an inactive site.

#### M3. Delivery and buyer confirmation as separate quantities (F3, F4)
- **AC:**
  - A delivery records the delivered quantity, which may not exceed the dispatched quantity.
  - A buyer confirmation is a separate record: a quantity no more than the delivered quantity, the channel, an attestation and the actor.
  - Events: `delivery.recorded` and `delivery.buyer_confirmed`.
  - "Confirmed" is never written for an unconfirmed delivery.
  - Whether the buyer confirms in their own portal or staff relay it is policy decision P5.
- **Code:** `reconciliation` domain and API; the migration adds `buyer_confirmations`.
- **Migration risk:** medium.
  - Existing `deliveries.buyer_confirmed=true` rows are migrated to confirmations of the delivered quantity, flagged `LEGACY_UNQUANTIFIED`, and reported as such, never as quantified buyer confirmation.
  - The old `delivery.confirmed` events are left unchanged, because history is immutable.
- **Tests:** a confirmation above delivery refused; partial confirmation; idempotency; attribution; legacy rows labelled.

#### M4. Immutable, versioned reconciliation with disputes (F5, F6, F8)
- **AC:**
  - Reconciliation appends a versioned record and never overwrites. Each record carries:
    - the figures: required, committed, received, quality-accepted, rejected, dispatched, delivered, buyer-confirmed;
    - the variances between them;
    - the shipments, deliveries and confirmations it rests on, by id.
  - A correction is a new version that names the version it supersedes and gives a reason.
  - Disputes are their own records: opened, resolved or withdrawn, each with an actor.
  - Preconditions: every receipt graded; every shipment delivered or explicitly cancelled with a reason; confirmed quantity no more than delivered.
  - "Completed" is shown only when your completion rule (P6) is met.
  - Lifecycle:
    - ACTIVE → IN_FULFILMENT at the first receipt;
    - → RECONCILED at the first reconciliation record;
    - → CLOSED at close-out (M5).
- **Code:** a new `reconciliation_records` and `reconciliation_disputes`; `reconcile` rewritten; the read model and order page.
- **Migration risk:** medium. Each existing `requirement_reconciliations` row becomes version 1 of a `reconciliation_records` entry, flagged `LEGACY_RECORD`. The old table becomes read-only and is dropped in a later release, not in WP4.
- **Tests:**
  - **the spec §6 second half:** 725 kg received, 705 accepted and 20 rejected, buyer confirmation no more than delivered; the record shows 25 kg required-to-accepted and never claims 730 kg delivered;
  - re-reconciliation creates version 2 and leaves version 1 unchanged;
  - preconditions refused; disputes; PostgreSQL concurrency between two reconciles.

#### M5. Close-out release and cancellation policy (D2, D3, D4)
- **AC:**
  - **Close-out**, at reconciliation or when you choose (P2), releases what is still reserved:
    - the undelivered remainder of each commitment, recorded as `RELEASED` with the reason "order closed";
    - every authorized standby, which becomes `RELEASED`;
    - every open request, which is withdrawn.
    Each release is an event attributed to the order, never to the farmer's reliability.
  - **Cancellation with binding supply** follows your policy (P1). Through the approval gateway, it releases commitments, standby and requests, cancels recovery tasks and records `BUYER_CANCELLATION` attribution.
  - **A dropout releases the lost allocation's reservation** in the same transaction (P3).
- **Code:** a new `supply/application/release.py`, the single release primitive that also replaces the inline releases in `exceptions._release`, `commitments.withdraw` and the decline path; `demand/api/router.py` cancel; `recovery.dropout`; a gateway action `RELEASE_FOR_CANCELLATION` if P1 requires approval.
- **Migration risk:** low for new events.
  - Existing over-held reservations are not released automatically.
  - A one-off, **dry-run-first** script (`scripts/release_audit.py`) lists them for you to approve. It writes a report, then applies only with `--apply` plus a reason, and every release becomes an event.
- **Tests:**
  - the stock-ledger invariant (M8) asserted after close-out, cancellation and dropout in every scenario;
  - idempotent repeats;
  - concurrency: close-out racing a late acceptance on the same lot (PostgreSQL);
  - farmer attribution unchanged.

#### M6. Buyer quantity changes keep coverage true (D1)
- **AC:**
  - A change is refused on cancelled, reconciled or closed orders.
  - **An increase** recomputes coverage. If short, a `DEMAND_INCREASE` exception opens and the recovery agent proposes cover, needing approval as in WP3.
  - **A decrease below commitments** opens an `OVER_COMMITTED` exception. The agent proposes which commitments to reduce, using a new gateway action `RELEASE_SURPLUS`, which needs approval; the default ordering is set by P4. Nothing is released automatically.
  - Supply health is always recomputed, and the change wakes the order's recovery task.
- **Code:** `demand/api/router.py` (`buyer_change`), `assurance/domain/exceptions.py` (2 kinds), `agents/application/evidence.py` (surplus options), `gateway.py` (`RELEASE_SURPLUS`), orchestrator wake topics.
- **Migration risk:** none (additive).
- **Tests:**
  - increase to shortfall to proposal to approval;
  - decrease to over-commitment to release proposal; a rejected proposal leaves commitments unchanged;
  - status guards;
  - concurrency between a buyer change and a supplier acceptance.

#### M7. One authority for lot capacity and status (D6, D7, D8, D11)
- **AC:**
  - **One status rule.** A single `refresh_lot_status(lot)`, aware of the capacity ceiling, is the only code that sets AVAILABLE, UNAVAILABLE or EXHAUSTED. It is used by every writer.
  - **Lot edits.** Changing grade, crop or harvest window on a lot with active commitments or standby is refused (409, naming the affected orders). The coordinator first resolves those, or records a capacity report and lets recovery act. P7 decides whether a grade downgrade should open an exception instead.
  - **Legacy availability endpoints.** These are `ingestion/.../availability` and availability changes applied by `_apply_observation`. Each is retired or routed through `record_capacity_report` (P8): either way, no path changes availability without the capacity-report rules and a `lot.capacity_reported` event.
  - **Lot expiry.** A lot past `harvest_end` plus a grace period (P9) becomes EXHAUSTED for new planning and recovery. Existing commitments stay, and the worker opens an exception if undelivered commitments remain past the grace period.
- **Code:** `supply/application/capacity.py`, `supply/api/router.py`, `ingestion/api/router.py`, `marketplace/api/router.py`, `worker.py` (an expiry timer).
- **Migration risk:**
  - Low for code.
  - Recomputing status on existing lots changes some from AVAILABLE to UNAVAILABLE. That is a correction, and the migration reports each one.
  - Retiring an endpoint breaks any external caller. None exists in this repository; the farmer portal does not use it. A 410 response with a pointer is proposed for one release.
- **Tests:** a status-rule matrix including the ceiling; edits refused under commitments; each legacy path routed or refused; the expiry timer is idempotent and opens one exception.

#### M8. Stock ledger check and monitoring (D10)
- **AC:**
  - For every lot, `reserved_quantity_kg` must equal the sum of allocations holding reservations plus PLACED marketplace orders.
  - A deterministic check runs:
    - in the worker (hourly by default);
    - in tests, as a shared assertion after every accounting scenario;
    - on demand through a staff endpoint.
  - Any mismatch is recorded with its lot and difference, and makes monitoring DEGRADED (`stock_ledger_mismatch`). It is never auto-corrected; correction goes through M5's audited release script.
- **Code:** a new `supply/application/ledger.py`, `operations.py`, `worker.py`.
- **Migration risk:** none. The first run on existing databases may report legacy drift, which is the point.
- **Tests:** a seeded drift is detected; consistent data passes; the assertion is wired into the WP2, WP3 and WP4 accounting suites.

#### M9. Marketplace held out of the pilot (D9)
- **AC:**
  - Marketplace order creation is off unless `MARKETPLACE_ORDERS_ENABLED=true`, and is refused in production until you enable it (P10).
  - Existing marketplace reservations are listed by the M5 audit script for your decision.
  - If enabled, creation requires an idempotency key. Cancellation that releases its reservation is added as the minimum.
- **Code:** `marketplace/api/router.py`, `core/config.py`.
- **Migration risk:** low. Marketplace screens show "not available in this release" instead of failing.
- **Tests:** refused when off; idempotent when on; cancellation releases stock; the ledger check stays balanced.

#### M10. Truthful passport and tenant-safe references (F7, F9)
- **AC:**
  - Shipment references are unique per fulfilment site, not globally.
  - The passport returns only measures it can compute from reconciliation records. Quantity fulfilment comes from buyer-confirmed against committed quantity, labelled as such. `fulfilment_reliability_index` is withheld ("not assessed") until you define it.
- **Code:** `reconciliation/domain/models.py` and router; migration.
- **Migration risk:** low. The unique index is replaced by `(fulfilment_node_id, reference)`; existing references are already globally unique, so none collide.
- **Tests:** the same reference in two organizations is allowed; passport fields; isolation.

#### M11. Minimal fulfilment workflow in the R1 UI (F10)
- **AC:** on the order page, a warehouse operator or coordinator can complete the whole fulfilment half:
  - record a receipt against a committed allocation at a site;
  - grade it, with rejection reasons;
  - build a shipment only from accepted quantity;
  - dispatch it with evidence;
  - record the delivery;
  - record the buyer's confirmation (P5);
  - reconcile, with the full variance table, and open or resolve disputes.

  Every screen handles loading, error, empty and conflict states, and receipt does not equal acceptance, nor dispatch delivery. A consolidated Receiving workspace waits for WP5.
- **Code:** `OrderDetail.tsx` plus new components, and `useFulfilment` hooks.
- **Tests:** Vitest for each form; **E2E for spec §6 in full**, in two browser sessions: the existing recovery story, then 725 kg received, 705 accepted, delivery, partial confirmation, and reconciliation preserving 25 kg.

### 2.2 Enhancements that can safely wait until WP5

| Item | Why it can wait | Register |
|---|---|---|
| Buyer self-service portal beyond confirming a delivery | Staff-relayed confirmation with attestation is truthful for a shadow-mode pilot, if you accept it (P5) | 6 |
| Consolidated Receiving and Shipments workspace | M11 delivers the working flow on the order page | — |
| Organization-wide response-deadline policies | Defaults plus per-request changes, with an audit trail, work | 5 |
| SMS, WhatsApp or email notifications | Needs channel, consent and provider decisions; drafts exist | 4 |
| Grades other than A | No pilot requirement yet | 3 |
| Full marketplace lifecycle (fulfilment, exposure) | Out of R1 scope; off by default after M9 | 2 |
| Retiring pre-R1 demo scripts and the rule-based evaluator | No product impact | 12, 13 |
| Planning on the same tick as an incident | 2-second latency | 14 |
| Reserving stock when a request is made | Contention is already safe (acceptance re-checks) | 10 |

## 3. Policy decisions needed from you

| # | Decision | My recommendation |
|---|---|---|
| P1 | Cancelling an order that holds commitments or standby: who may do it, and does it need approval? | Coordinator proposes; ordinary approval through the WP3 gateway; elevated approval if any delivery has started. Attribution `BUYER_CANCELLATION`; never counted against farmers |
| P2 | When to release undelivered reservations at the end of an order | At reconciliation version 1. Allow a coordinator to close out earlier with a reason |
| P3 | Release a dropped-out allocation's reservation immediately? | Yes. The farmer has said the stock cannot be supplied |
| P4 | When a buyer reduces quantity below commitments, which commitments are reduced first? | The latest accepted first (mirrors WP2 exposure), always as a proposal for approval, never automatically |
| P5 | Buyer confirmation for the pilot: the buyer in their own portal, or staff relaying with an attestation? | Both channels recorded distinctly. Staff relay is enough for the shadow-mode pilot; portal confirmation for buyer accounts that exist |
| P6 | What counts as "completed" for an order | Reconciled, with no open dispute, and buyer-confirmed quantity recorded for every delivery. A shortfall is allowed but shown, never hidden |
| P7 | A lot downgraded (for example A to B) while it holds commitments | Refuse the edit and require a quality-rejection or capacity-report path. Alternatively, allow it and open an exception |
| P8 | Legacy availability endpoint and ingestion writes | Route through capacity reports. Retire the farmer-portal legacy endpoint with 410 for one release |
| P9 | Lot expiry grace period after `harvest_end` | 7 days, configurable per organization later |
| P10 | Marketplace in the pilot | Off (out of R1 scope); existing reservations reviewed through the audit script |
| P11 | Reconciliation authority | Coordinator and procurement manager (`trade.reconcile`); corrections by the same roles with a reason; disputes opened by any staff role except auditors |

## 4. Sequence and verification

1. **Ledger foundations:** M8 (the ledger check, which then guards all later steps), the release primitive from M5, and M7's status rule.
2. **Accounting policies:** M5 (close-out, cancellation, dropout), M6 (buyer changes), M7 (edits, legacy writers, expiry), M9 (marketplace off).
3. **Fulfilment backend:** M1, M2, M3, M4, M10, with migrations `0024` onward. Each is additive, with a legacy-flag backfill and no destructive drops in WP4.
4. **Fulfilment UI:** M11, then the full spec §6 E2E in two sessions.
5. **Verification:**
   - every existing gate: the backend suite on SQLite and PostgreSQL, lint, typecheck, Vitest, the production build with the bundle check, and E2E with the worker;
   - the new PostgreSQL concurrency tests;
   - a migration round trip on a copy of a populated database;
   - the dry-run audit report on that database;
   - clean-checkout verification, Linux CI, and a handoff.

**Migration safety:**
- Every migration is additive or a reversible index change.
- Data corrections (status recompute, legacy flags) are reported by the migration.
- Reservation corrections are never made by a migration, only by the audited script after your approval.
- Before running on any non-test database: a backup, the dry-run report, then apply.

## 5. Independent release gates (unchanged, not part of WP4)

| Gate | Status |
|---|---|
| Supabase staging authentication (`STAGING_AUTH_VERIFICATION.md`) | Not run; needs a staging deployment |
| Branch review and merge order | WP1, then WP2, then WP3, then model providers, then WP4. Nothing merged |
| Worker supervision and uptime monitoring of `/health/worker` | Deployment configuration |
| Real-model validation before enabling any provider | Open; needs keys configured locally. Production model access stays disabled |

## 6. Risks

- **The release script touches real reservations.** It is dry-run by default, needs explicit apply with a reason, and records every release as an event. Your approval is required before it runs on any shared database.
- **Retiring the legacy endpoint breaks any unknown external caller.** The 410 window and the pointer to capacity reports mitigate this.
- **Recomputing status may surprise users** when lots flip to UNAVAILABLE. The migration report lists each change and why.
- **Scope:** M11 is deliberately minimal. If the pilot needs the consolidated workspace sooner, it moves from WP5 to WP4 and the estimate grows.
