# R1 — WP4 report: fulfilment accounting, reservation release, buyer confirmation and close-out

**Branch:** `feat/r1-wp4-fulfilment-accounting`, built on `feat/r1-wp3-model-providers`. Not merged; nothing deployed.
**Authority:** the R1 WP4 Implementation Authorization (policies P1–P11 and the additional requirements), which supersedes the proposal in [R1_WP4_PROPOSAL.md](R1_WP4_PROPOSAL.md) where they differ.
**Verification and evidence:** [R1_WP4_HANDOFF.md](R1_WP4_HANDOFF.md). **Deferred items:** [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md).

Order of work, as authorized: ledger invariants, release primitives and domain rules first, then the API, migrations and monitoring, then the UI and the browser test.

## 1. What a quantity means now

Every quantity below is kept separately, computed from records, and shown separately in the API (`GET /requirements/{id}/fulfilment-record`) and on the order page:

| Quantity | Source |
|---|---|
| Required | the order |
| Committed | supplier commitments with recorded consent; a lost commitment counts only what was received |
| Received, accepted, rejected | receipts plus their correction rows (`received_sublots`, `entry_type`) |
| Dispatched | accepted produce on dispatched or delivered shipments |
| Delivered | proof of delivery plus delivery corrections (`delivery_adjustments`) |
| Buyer-confirmed | the buyer's current statement for each delivery (`buyer_confirmations`) |
| Disputed | open disputes |
| Released | `supply_allocations.released_quantity_kg`; the original commitment is never rewritten |

**Obligation** = commitment − released. Coverage, exposure, the receipt limit and standby figures use it for live allocations; ended allocations report their original quantity.

## 2. The stock ledger (M8, requirements 1, 2 and 5)

**Invariant, for every lot** (`supply/application/ledger.py`):

```
reserved = Σ (quantity − released) over allocations holding a reservation + Σ PLACED marketplace orders
```

- The worker checks it every `LEDGER_CHECK_SECONDS` (default 3600) in a single SQL statement, so a reservation committed mid-check cannot show up as a false mismatch.
- A mismatch becomes an open `StockLedgerFinding`. Monitoring then reports `DEGRADED` with reason `stock_ledger_mismatch`, and the header shows "Reserved stock on some lots does not match their commitments".
- It is **never repaired automatically**. The finding resolves only when a later check finds the lot balanced again.
- `GET /stock-ledger` runs the check for the caller's organization.
- Every two-organization test ends with the invariant asserted (`tests/two_orgs.py`). The two tests that deliberately create drift are marked `ledger_drift_expected`.

**Faults the invariant found and that are now fixed:**
- standby activation held the reservation twice;
- coverage dropped delivered stock after a dropout;
- the direct-cancel path decremented reserved stock by hand, using the full quantity rather than the release primitive.

## 3. The release primitive (P2, P3)

`supply/application/release.py` is the only code that releases reserved stock:
- `release(allocation, quantity, kind=…)` releases part or all of what is reserved **and not yet received**;
- `release_remaining(…)` releases the rest and is idempotent: a second call releases 0;
- received stock (accepted, rejected or corrected) is never released.

**Per release:**
- the lot row is locked;
- `released_quantity_kg` increases; `holds_reservation` turns false only when nothing remains held;
- event `allocation.reservation_released` records the kind, the attribution (for example `BUYER_CANCELLATION`, `SUPPLIER_DROPOUT`, `ORDER_CLOSE_OUT`), the reason and the actor;
- after close-out, cancellation, buyer reduction, dropout, approved partial release or unused standby, the lot is flagged for **re-verification**. Released stock is not offered to another order until a capacity report or a new declaration confirms usable capacity.

Every older path now goes through it:
- dropout;
- withdrawal and decline;
- expiry;
- capacity exposure and ineligibility in the gateway;
- direct cancel of unplanned requests.

## 4. Policies P1–P11: how each is implemented

### P1 Cancellation
- **Requesting:** `POST /requirements/{id}/cancellation-requests` records who asked, the buyer's instruction or evidence, the reason and the commercial consequences. A coordinator can only request.
- **Direct cancel:** still refused once suppliers hold commitments or standby, with a pointer to the request route.
- **Planning** (`agents/application/releases.py`): the agent plans deterministically.
  - Each commitment needs the supplier's recorded **release agreement** (`POST /allocations/{id}/release-agreements`, by the farmer for their own lot or relayed by staff with an attestation), unless the organization's approval policy records `commitment_release_without_supplier_consent`.
  - If any agreement is missing, no proposal is made. The task escalates and names the suppliers.
- **Before any receipt:** a FULL cancellation with ordinary approval through the WP3 gateway.
- **After a receipt:** REMAINDER, which needs elevated approval from a procurement manager or organization administrator. Only undelivered obligations are released; receipts, shipments and deliveries stay. The order stays open for reconciliation and closes with an accepted variance.
- **Attribution:** releases are recorded as `BUYER_CANCELLATION`, never as farmer default.
- **Tests:** `test_cancellation_is_a_request_that_needs_supplier_agreement_and_approval`, `test_cancellation_after_receipt_keeps_physical_records_and_needs_elevated_approval`.

### P2 Release at close-out
- `POST /requirements/{id}/close` (`reconciliation/application/services.py: close_order`) releases only what was never received:
  - commitments: kind `close_out`;
  - unused standby: `standby_unused`, and the allocation becomes RELEASED;
  - open requests are withdrawn.
- Reconciliation alone releases nothing.
- Closing (or an approved FULL cancellation) also ends the order's recovery task and resolves its open exceptions with the outcome ("order ended (closed with variance)"); the exception records stay. The order page then shows "Order ended" instead of a supply-health call to action.
- Earlier partial releases use `POST /allocations/{id}/release-requests`, which goes through an approved proposal. Elevated approval is needed once goods are received.

### P3 Dropout
- The lost undelivered reservation is released in the same transaction with attribution `SUPPLIER_DROPOUT`.
- The commitment, the dropout event and its cause are kept.
- Delivered quantities stay counted.
- **Test:** `test_dropout_releases_only_the_undelivered_part_at_once_and_keeps_the_history`.

### P4 Buyer reduction
- A reduction opens `OVER_COMMITTED`; the recovery task proposes reductions:
  - latest accepted first;
  - allocations already in physical fulfilment last;
  - each one needs the supplier's agreement or the contractual right, and approval.
- Nothing is revoked automatically. An increase opens `DEMAND_INCREASE`.
- **Test:** `test_buyer_changes_never_revoke_commitments_automatically`.

### P5 Buyer confirmation
- **Buyer's own confirmation:** `POST /buyer/deliveries/{id}/confirmation`, in the buyer's account, only for their own deliveries.
- **Staff relay:** `POST /deliveries/{id}/confirmations` requires the representative, channel, attestation and the time of the statement (not in the future). It is always shown as "Relayed by staff: … via …".
- **Rules for both:**
  - a confirmation can never exceed the delivered quantity;
  - a partial confirmation with a discrepancy needs a description and opens a buyer dispute;
  - later statements supersede earlier ones and nothing is overwritten.
- **Legacy flag:** the old yes/no `buyer_confirmed` field is refused with 422.

### P6 Completion states
- **Reconciled:** a versioned comparison exists. Shown as "Reconciled, not closed".
- **Completed:** needs buyer-confirmed ≥ required, every delivery confirmed, no discrepancy and no open dispute.
- **Closed with variance:** needs `trade.accept_variance` (procurement manager or organization administrator) and a documented reason. It stays visible on the order permanently, with the variance figures.
- An unconfirmed delivery is never shown as completed.

### P7 Changed lot information
- A grade, crop or harvest change re-checks every order with live allocations (`assess_lot_eligibility`) and opens `ELIGIBILITY_CHANGED`. It resolves when the lot matches again.
- Commitments and their original grade are untouched; nothing is substituted.
- A withdrawn lot cannot be edited.

### P8 One capacity-reporting service
- Secure-link replies and coordinator observations go through `record_capacity_report`:
  - the farmer's secure-link reply as channel `FARMER_SECURE_LINK`;
  - coordinator-supplied or imported data always as relayed.
- `POST /v1/ingestion/farmer-production-lots/{lot_id}/availability` returns **410** with guidance to use capacity reports.

### P9 Harvest expiry (worker, `supply/application/lot_timers.py`)
- **Re-verification:** once `HARVEST_REVERIFY_DAYS` (default 7) have passed since `harvest_end`, a lot with stock left and no confirmation in the last 7 days is flagged for re-verification. This excludes it from new planning only.
- **Time alone** never marks a lot exhausted.
- **Verified limits:** a passed `viable_until` or a withdrawal (`POST /production-lots/{id}/withdraw`) makes the lot EXHAUSTED at once. It opens `LOT_UNAVAILABLE` for orders with undelivered commitments on it.
- **Per crop:** the period is one setting for every crop in R1 (debt register).

### P10 Marketplace
- Disabled for the pilot. `marketplace_orders_enabled()` is false unless `MARKETPLACE_ORDERS_ENABLED=true` and the environment is not production, and the backend returns 403 otherwise.
- Existing PLACED orders are part of the ledger check and are listed for review by the release audit, never released or deleted.

### P11 Reconciliation authority
- **Who reconciles:** coordinators and procurement managers, with `trade.reconcile`.
- **Corrections:** a correction is a new version naming its predecessor and a reason.
- **Material corrections:** a change to received, accepted, rejected, delivered, buyer-confirmed or committed figures is PENDING_REVIEW until a different reconciler approves it. The previous version stays effective meanwhile.
- **Warehouse operators:** record receipts, grading, shipments and deliveries but get 403 on reconcile.
- **Buyers and staff:** buyers dispute their own deliveries; staff with `dispute.raise` raise discrepancies.
- **Dispute resolution:** recorded once, attributed, never overwritten.
- **Auditors:** read-only, plus `POST /audit-flags`.

## 5. Physical evidence (requirement 3) and tenancy (requirement 4)

**Physical evidence:**
- Receipts are never edited after grading. A correction is an ADJUSTMENT row linked to its receipt, with signed differences and a reason (`POST /sublots/{id}/adjustments`), so every sum includes it.
- Delivery corrections are `DeliveryAdjustment` rows.
- A receipt needs a COMMITTED allocation with recorded consent, an open order and an active site, and it cannot exceed the obligation.
- Shipments that never left can be cancelled with a reason; their produce can then go on another shipment.

**Tenancy:**
- Sites, deliveries, disputes and reconciliations are organization-scoped, with tenancy resolvers.
- The route sweep in `test_tenant_isolation.py` covers every new path parameter.
- Shipment references are unique per site, not across tenants.

## 6. Migration `0024_fulfilment_accounting` (requirement 8)

**Additive.** It adds:
- the columns and tables listed in its docstring;
- the WP4 permission rows.

**Backfill:**
- each legacy `requirement_reconciliations` row becomes reconciliation version 1, marked `legacy`;
- each delivery with the old flag gets a `LEGACY_UNQUANTIFIED` confirmation of 0 kg, so it is never counted as confirmed quantity;
- the legacy rows are left unchanged.

**Downgrade:**
- refuses if receipt adjustments exist, rather than delete physical evidence;
- leaves `lifecycle_status` widened.

**Reservation corrections** are never made by the migration. `scripts/release_audit.py`:
- is a dry run by default;
- applies only with `--apply`, the reviewed report, a reason, an approval reference and a backup reference;
- refuses if the findings changed since the report was produced.

It was **not** run against any shared or pilot database.

## 7. UI (M11, deliberately minimal)

**Order page** (`components/trade/FulfilmentSection.tsx`):
- the separate quantities;
- record receipt, grading, shipments (create, add, dispatch, cancel with a reason, deliver);
- relayed buyer confirmation;
- disputes;
- reconciliation versions with review;
- close as completed, or close with variance;
- a cancellation request in place of direct cancel once suppliers are involved.

**Other pages:**
- **Fulfilment sites:** `/fulfilment/sites`.
- **My deliveries** for buyers: `/deliveries`. Confirm, part-confirm or report a difference.
- **Proposal cards:** label release, standby release, withdrawal and cancellation actions, with the attribution ("buyer cancellation, not the farmer's default"), what stays on record, why the release is allowed, the buyer's instruction and the commercial consequences.

**Deferred to WP5:** the consolidated fulfilment workspace and buyer portal enhancements.

## 8. Independent release gates (unchanged)

- Supabase staging authentication: not run.
- Worker supervision and uptime monitoring.
- Real-model validation: production model access stays disabled.
- Branch review and merge order: nothing merged or deployed.
