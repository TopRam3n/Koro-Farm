"""Reservation release audit (R1 WP4). Dry run by default; never run --apply on a shared database without approval.

The dry run reads only: on PostgreSQL it runs in a READ ONLY transaction, so it cannot change anything. Its report
names, for each finding, the organization, the order, the allocation, the farmer and lot, the quantities, the
release reason and the expected effect on the lot, plus every current stock-ledger discrepancy.

Releasable (applied only with --apply, after a separate product-owner approval of the actual report):
* an allocation on a CANCELLED or legacy CLOSED order that still holds undelivered stock (kind cancellation /
  close_out);
* an allocation that ended (LOST, WITHDRAWN, DECLINED, EXPIRED, RELEASED, CANCELLED) but still holds undelivered
  stock (kind dropout, request_withdrawn, ...).
Review only (never changed by this script, because the right correction is not certain):
* any allocation on a lot whose reserved total does not balance (stock ledger): releasing would act on a figure
  already known to be wrong, so the lot is investigated first;
* orders RECONCILED before WP4 that still hold stock: release happens at close-out (P2), through the close action;
* ACTIVATED standby still holding a reservation next to its commitment (a possible double hold before WP4);
* PLACED marketplace orders (P10: reviewed, never silently released or deleted).
Stock-ledger mismatches are reported, never resolved here.

Received stock is never released. Every release goes through supply/application/release.py and is recorded as an
`allocation.reservation_released` event naming the approval and backup references.

    python -m src.backend.scripts.release_audit --output report.json
    python -m src.backend.scripts.release_audit --apply --report report.json --reason "..." \\
        --approval-reference "..." --backup-reference "..."

Execution safety (--apply): one transaction. It first locks, in the application's lock order (orders, then
allocations, then lots, each by id), every row the reviewed report would change, with a lock timeout so it fails
rather than waits indefinitely. It then rebuilds the findings under those locks and refuses unless they are exactly
the reviewed report (same fingerprint). Any failure rolls everything back; nothing is applied partially.
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus as L
from src.backend.app.identity.domain.models import Organization
from src.backend.app.marketplace.domain.models import MarketplaceOrder, MarketplaceOrderStatus
from src.backend.app.supply.application.capacity import free_kg
from src.backend.app.supply.application.ledger import check_ledger, mismatches
from src.backend.app.supply.application.release import REVERIFY, received_kg, releasable_kg, release
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus as S, SupplyAllocation

ORDER_KIND = {L.CANCELLED: "cancellation", L.CLOSED: "close_out"}
ALLOCATION_KIND = {S.LOST: "dropout", S.WITHDRAWN: "request_withdrawn", S.DECLINED: "request_declined",
                   S.RELEASED: "approved_partial", S.CANCELLED: "cancellation"}
REASON = {
    "cancellation": "order cancelled; its undelivered reservation was never released",
    "close_out": "order closed before WP4; its undelivered reservation was never released",
    "dropout": "supplier dropped out; the lost undelivered reservation was never released",
    "request_withdrawn": "request withdrawn but still holding a reservation",
    "request_declined": "supplier declined but the reservation is still held",
    "request_expired": "request expired unanswered but still holding a reservation",
    "standby_expired": "standby authorization expired but still holding a reservation",
    "approved_partial": "allocation marked released but still holding a reservation",
}
LOCK_TIMEOUT = "10s"
kg = lambda value: format(Decimal(value).normalize(), "f")  # noqa: E731


def _kind(allocation: SupplyAllocation, requirement: Requirement) -> str | None:
    if requirement.lifecycle_status in ORDER_KIND:
        return ORDER_KIND[requirement.lifecycle_status]
    if allocation.status == S.EXPIRED:
        return "standby_expired" if allocation.role == AllocationRole.STANDBY else "request_expired"
    return ALLOCATION_KIND.get(allocation.status)


def audit(session: Session) -> dict:
    """Build the findings. Reads only."""
    ledger = mismatches(session)
    unbalanced = {m["production_lot_id"] for m in ledger}
    releasable, review = [], []
    rows = session.execute(select(SupplyAllocation, Requirement, Buyer, Organization, ProductionLot, Farmer)
                           .join(Requirement, Requirement.id == SupplyAllocation.requirement_id)
                           .join(Buyer, Buyer.id == Requirement.buyer_id)
                           .join(Organization, Organization.id == Buyer.organization_id)
                           .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
                           .join(Farmer, Farmer.id == ProductionLot.farmer_id)
                           .where(SupplyAllocation.holds_reservation.is_(True))
                           .order_by(Organization.id, Requirement.id, SupplyAllocation.id)).all()
    for allocation, requirement, buyer, organization, lot, farmer in rows:
        quantity = releasable_kg(session, allocation)
        if quantity <= 0:
            continue
        item = {
            "organization_id": str(organization.id), "organization_name": organization.name,
            "requirement_id": str(requirement.id), "order": f"{requirement.crop} grade {requirement.grade.value}, {kg(requirement.required_quantity_kg)} kg for {buyer.name}",
            "order_status": requirement.lifecycle_status.value,
            "allocation_id": str(allocation.id), "allocation_role": allocation.role.value, "allocation_status": allocation.status.value,
            "farmer_name": farmer.name, "production_lot_id": str(lot.id),
            "commitment_kg": kg(allocation.quantity_kg), "already_released_kg": kg(allocation.released_quantity_kg or 0),
            "received_kg": kg(received_kg(session, allocation.id)), "undelivered_reserved_kg": kg(quantity),
        }
        kind = _kind(allocation, requirement)
        if str(lot.id) in unbalanced:
            review.append({**item, "issue": "the lot's reserved total does not balance (see stock_ledger_mismatches); investigate before any release"})
        elif kind is not None:
            releasable.append({**item, "kind": kind, "reason": REASON[kind], "reverification_required_after": REVERIFY[kind]})
        elif requirement.lifecycle_status == L.RECONCILED:
            review.append({**item, "issue": "reconciled before WP4 and still holding stock; close the order to release it"})
        elif allocation.status == S.ACTIVATED:
            review.append({**item, "issue": "activated standby still holds a reservation next to its commitment"})

    # Expected effect on each lot if the releasable findings were applied.
    by_lot: dict[str, Decimal] = defaultdict(Decimal)
    for item in releasable:
        by_lot[item["production_lot_id"]] += Decimal(item["undelivered_reserved_kg"])
    effects = []
    for lot_id in sorted(by_lot):
        lot = session.get(ProductionLot, UUID(lot_id))
        released = by_lot[lot_id]
        before_free = free_kg(lot)
        effects.append({"production_lot_id": lot_id, "reserved_before_kg": kg(lot.reserved_quantity_kg),
                        "released_kg": kg(released), "reserved_after_kg": kg(lot.reserved_quantity_kg - released),
                        "free_before_kg": kg(before_free), "free_after_if_reverified_kg": kg(before_free + released),
                        "offered_to_new_orders": "not until usable capacity is confirmed again"
                        if any(i["reverification_required_after"] for i in releasable if i["production_lot_id"] == lot_id)
                        else "yes, once released"})

    farmers = {str(lot_id): name for lot_id, name in session.execute(
        select(ProductionLot.id, Farmer.name).join(Farmer, Farmer.id == ProductionLot.farmer_id))}
    organizations = {str(i): n for i, n in session.execute(select(Organization.id, Organization.name))}
    ledger_detail = [{**m, "organization_name": organizations.get(m["organization_id"]), "farmer_name": farmers.get(m["production_lot_id"])}
                     for m in ledger]
    placed = session.scalars(select(MarketplaceOrder).where(MarketplaceOrder.status == MarketplaceOrderStatus.PLACED)
                             .order_by(MarketplaceOrder.id)).all()
    summary: dict[str, dict] = {}
    for item in releasable:
        row = summary.setdefault(item["organization_id"], {"organization_name": item["organization_name"], "allocations": 0,
                                                            "orders": set(), "release_kg": Decimal(0)})
        row["allocations"] += 1
        row["orders"].add(item["requirement_id"])
        row["release_kg"] += Decimal(item["undelivered_reserved_kg"])
    findings = {
        "releasable": releasable,
        "expected_lot_effects": effects,
        "review": review,
        "stock_ledger_mismatches": ledger_detail,
        "marketplace_orders_placed": [{"marketplace_order_id": str(o.id), "production_lot_id": str(o.production_lot_id),
                                       "quantity_kg": kg(o.quantity_kg)} for o in placed],
        "summary_by_organization": {k: {**v, "orders": len(v["orders"]), "release_kg": kg(v["release_kg"])} for k, v in sorted(summary.items())},
    }
    fingerprint = hashlib.sha256(json.dumps(findings, sort_keys=True).encode()).hexdigest()
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": "dry-run", "fingerprint": fingerprint,
            "totals": {"releasable_allocations": len(releasable), "release_kg": kg(sum((Decimal(i["undelivered_reserved_kg"]) for i in releasable), Decimal(0))),
                       "review_items": len(review), "stock_ledger_mismatches": len(ledger), "marketplace_orders_placed": len(placed)},
            **findings}


def dry_run(session: Session) -> dict:
    """The audit in a read-only transaction (PostgreSQL enforces it). The caller rolls back."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET TRANSACTION READ ONLY"))
    return audit(session)


def _lock(session: Session, report: dict) -> None:
    """Lock every row the reviewed report would change, in the application's lock order, failing fast."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    items = report.get("releasable", [])
    for model, ids in ((Requirement, {i["requirement_id"] for i in items}), (SupplyAllocation, {i["allocation_id"] for i in items}),
                       (ProductionLot, {i["production_lot_id"] for i in items})):
        if ids:
            session.scalars(select(model).where(model.id.in_([UUID(x) for x in ids])).order_by(model.id)
                            .with_for_update().execution_options(populate_existing=True)).all()


def apply(session: Session, report: dict, *, reason: str, approval_reference: str, backup_reference: str) -> dict:
    """Release exactly the reviewed findings, under locks, in one transaction. The caller commits."""
    for name, value in (("reason", reason), ("approval reference", approval_reference), ("backup reference", backup_reference)):
        if not (value or "").strip():
            raise SystemExit(f"Refusing apply: a {name} is required")
    _lock(session, report)
    current = audit(session)
    if current["fingerprint"] != report.get("fingerprint"):
        raise SystemExit("Refusing apply: findings changed since the dry-run report; run a new dry run and review it")
    released = []
    for item in current["releasable"]:
        allocation = session.get(SupplyAllocation, UUID(item["allocation_id"]))
        quantity = release(session, allocation, releasable_kg(session, allocation), kind=item["kind"],
                           reason=f"release audit: {reason}", actor_id=f"release-audit (approval {approval_reference})",
                           detail={"approval_reference": approval_reference, "backup_reference": backup_reference,
                                   "report_fingerprint": current["fingerprint"]})
        released.append({**item, "released_kg": kg(quantity)})
    remaining = check_ledger(session)
    return {"mode": "apply", "fingerprint": current["fingerprint"], "released": released,
            "stock_ledger_mismatches_after": remaining, "approval_reference": approval_reference,
            "backup_reference": backup_reference}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", help="write the report here (default: stdout)")
    parser.add_argument("--apply", action="store_true", help="release the findings of a reviewed dry-run report")
    parser.add_argument("--report", help="the dry-run report being applied")
    parser.add_argument("--reason")
    parser.add_argument("--approval-reference")
    parser.add_argument("--backup-reference", help="identifier of the backup taken before applying")
    args = parser.parse_args(argv)

    from src.backend.app.infrastructure.database.session import create_session_factory
    import src.backend.app.main  # noqa: F401  (registers every mapped model)
    factory = create_session_factory()
    with factory() as session:
        if not args.apply:
            result = dry_run(session)
            session.rollback()
        else:
            if not args.report:
                raise SystemExit("Refusing apply: --report (the reviewed dry-run report) is required")
            with open(args.report, encoding="utf-8") as handle:
                report = json.load(handle)
            try:
                result = apply(session, report, reason=args.reason, approval_reference=args.approval_reference,
                               backup_reference=args.backup_reference)
            except BaseException:
                session.rollback()
                raise
            session.commit()
    output = json.dumps(result, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
