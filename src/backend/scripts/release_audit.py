"""Reservation release audit (R1 WP4). Dry run by default; never run --apply on a shared database without approval.

Lists reservations that the WP4 rules say should no longer be held, and things that need a person instead:

Releasable (applied only with --apply):
* an allocation on a CANCELLED or legacy CLOSED order that still holds undelivered stock (kind cancellation /
  close_out);
* an allocation that ended (LOST, WITHDRAWN, DECLINED, EXPIRED, RELEASED, CANCELLED) but still holds undelivered
  stock (kind dropout, request_withdrawn, ...).
Review only (never changed by this script):
* orders RECONCILED before WP4 that still hold stock: release happens at close-out (P2), through the close action;
* ACTIVATED standby still holding a reservation next to its commitment (a possible double hold before WP4);
* lots whose reserved quantity does not match what holds reservations on them (stock ledger);
* PLACED marketplace orders (P10: reviewed, never silently released or deleted).

Received stock is never released. Every release goes through supply/application/release.py and is recorded as an
`allocation.reservation_released` event naming the approval reference.

    python -m src.backend.scripts.release_audit --output report.json
    python -m src.backend.scripts.release_audit --apply --report report.json --reason "..." \\
        --approval-reference "..." --backup-reference "..."

--apply refuses unless the current findings are exactly those in the dry-run report (same fingerprint), so what was
reviewed is what is applied.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus as L
from src.backend.app.marketplace.domain.models import MarketplaceOrder, MarketplaceOrderStatus
from src.backend.app.supply.application.ledger import check_ledger, mismatches
from src.backend.app.supply.application.release import releasable_kg, release
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus as S, SupplyAllocation

ORDER_KIND = {L.CANCELLED: "cancellation", L.CLOSED: "close_out"}
ALLOCATION_KIND = {S.LOST: "dropout", S.WITHDRAWN: "request_withdrawn", S.DECLINED: "request_declined",
                   S.RELEASED: "approved_partial", S.CANCELLED: "cancellation"}


def _kind(allocation: SupplyAllocation, requirement: Requirement) -> str | None:
    if requirement.lifecycle_status in ORDER_KIND:
        return ORDER_KIND[requirement.lifecycle_status]
    if allocation.status == S.EXPIRED:
        return "standby_expired" if allocation.role == AllocationRole.STANDBY else "request_expired"
    return ALLOCATION_KIND.get(allocation.status)


def audit(session: Session) -> dict:
    releasable, review = [], []
    rows = session.execute(select(SupplyAllocation, Requirement, Buyer.organization_id)
                           .join(Requirement, Requirement.id == SupplyAllocation.requirement_id)
                           .join(Buyer, Buyer.id == Requirement.buyer_id)
                           .where(SupplyAllocation.holds_reservation.is_(True))
                           .order_by(SupplyAllocation.id)).all()
    for allocation, requirement, organization_id in rows:
        quantity = releasable_kg(session, allocation)
        if quantity <= 0:
            continue
        item = {"allocation_id": str(allocation.id), "requirement_id": str(requirement.id),
                "organization_id": str(organization_id), "production_lot_id": str(allocation.production_lot_id),
                "allocation_status": allocation.status.value, "order_status": requirement.lifecycle_status.value,
                "undelivered_reserved_kg": str(quantity)}
        kind = _kind(allocation, requirement)
        if kind is not None:
            releasable.append({**item, "kind": kind})
        elif requirement.lifecycle_status == L.RECONCILED:
            review.append({**item, "issue": "reconciled before WP4 and still holding stock; close the order to release it"})
        elif allocation.status == S.ACTIVATED:
            review.append({**item, "issue": "activated standby still holds a reservation next to its commitment"})
    placed = session.scalars(select(MarketplaceOrder).where(MarketplaceOrder.status == MarketplaceOrderStatus.PLACED)
                             .order_by(MarketplaceOrder.id)).all()
    findings = {
        "releasable": releasable,
        "review": review,
        "stock_ledger_mismatches": mismatches(session),
        "marketplace_orders_placed": [{"marketplace_order_id": str(o.id), "production_lot_id": str(o.production_lot_id),
                                       "quantity_kg": str(o.quantity_kg)} for o in placed],
    }
    fingerprint = hashlib.sha256(json.dumps(findings, sort_keys=True).encode()).hexdigest()
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": "dry-run", "fingerprint": fingerprint, **findings}


def apply(session: Session, report: dict, *, reason: str, approval_reference: str, backup_reference: str) -> dict:
    """Release exactly the reviewed findings. The caller commits."""
    for name, value in (("reason", reason), ("approval reference", approval_reference), ("backup reference", backup_reference)):
        if not (value or "").strip():
            raise SystemExit(f"Refusing apply: a {name} is required")
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
        released.append({**item, "released_kg": str(quantity)})
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
            result = audit(session)
            session.rollback()
        else:
            if not args.report:
                raise SystemExit("Refusing apply: --report (the reviewed dry-run report) is required")
            with open(args.report, encoding="utf-8") as handle:
                report = json.load(handle)
            result = apply(session, report, reason=args.reason, approval_reference=args.approval_reference,
                           backup_reference=args.backup_reference)
            session.commit()
    text = json.dumps(result, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
