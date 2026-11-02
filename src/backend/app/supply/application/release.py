"""The one way to release reserved stock (R1 WP4: P1, P2, P3, P4).

A release never rewrites a commitment: `SupplyAllocation.quantity_kg` stays what the supplier agreed, and the
released part is recorded in `released_quantity_kg` plus an `allocation.reservation_released` event. The quantity a
lot holds for an allocation is therefore `quantity_kg - released_quantity_kg` while `holds_reservation` is true
(supply/application/ledger.py checks that every lot's reserved total equals exactly that, summed).

Only undelivered stock can be released: anything received against the allocation (accepted or rejected, including
corrections) stays reserved forever, because delivered, rejected or consumed goods must never become plannable
again. Releases after close-out, cancellation, a buyer reduction or a dropout also flag the lot for
re-verification, so the freed quantity is not offered to another order until usable capacity is confirmed.

Every function works inside the caller's transaction and locks the lot row.
"""
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_system_event
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.supply.application.capacity import refresh_lot_status, require_reverification
from src.backend.app.supply.domain.models import ProductionLot
from src.backend.app.supply.domain.planning_models import SupplyAllocation

ZERO = Decimal("0")
# Release kinds and whether the freed stock must be re-verified before it is offered again.
REVERIFY = {"close_out": True, "cancellation": True, "surplus": True, "dropout": True, "approved_partial": True,
            "request_withdrawn": False, "request_declined": False, "request_expired": False, "standby_expired": False,
            "standby_unused": True, "capacity_exposure": False, "ineligible": False}
# Who a release is attributed to. Buyer-caused releases never count against a farmer.
ATTRIBUTION = {"close_out": "ORDER_CLOSE_OUT", "cancellation": "BUYER_CANCELLATION", "surplus": "BUYER_CHANGE",
               "dropout": "SUPPLIER_DROPOUT", "approved_partial": "COORDINATOR_RELEASE", "request_withdrawn": "COORDINATOR",
               "request_declined": "SUPPLIER_DECLINED", "request_expired": "NO_RESPONSE", "standby_expired": "AUTHORIZATION_EXPIRED",
               "standby_unused": "ORDER_CLOSE_OUT", "capacity_exposure": "SUPPLIER_CAPACITY_REPORT",
               "ineligible": "LOT_ELIGIBILITY_CHANGED"}


class ReleaseError(ValueError):
    pass


def received_kg(session: Session, allocation_id: UUID) -> Decimal:
    """Physically received against the allocation, corrections included."""
    return session.scalar(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0))
                          .where(ReceivedSublot.allocation_id == allocation_id)) or ZERO


def held_kg(allocation: SupplyAllocation) -> Decimal:
    return (allocation.quantity_kg - (allocation.released_quantity_kg or ZERO)) if allocation.holds_reservation else ZERO


def releasable_kg(session: Session, allocation: SupplyAllocation) -> Decimal:
    """Reserved and not yet received: the most that may ever be released."""
    return max(held_kg(allocation) - received_kg(session, allocation.id), ZERO)


def release(session: Session, allocation: SupplyAllocation, quantity: Decimal, *, kind: str, reason: str,
            actor_id: str, actor_type: str = "system", organization_id: UUID | None = None,
            correlation_id: UUID | None = None, detail: dict | None = None) -> Decimal:
    """Release `quantity` of the allocation's undelivered reservation. Returns the quantity released."""
    if kind not in REVERIFY:
        raise ReleaseError(f"unknown release kind {kind!r}")
    if quantity < 0:
        raise ReleaseError("a release cannot be negative")
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == allocation.production_lot_id)
                         .with_for_update().execution_options(populate_existing=True))
    available = releasable_kg(session, allocation)
    if quantity > available:
        raise ReleaseError(f"only {available} kg of this allocation is reserved and undelivered; {quantity} kg cannot be released")
    if quantity == 0:
        return ZERO
    lot.reserved_quantity_kg -= quantity
    allocation.released_quantity_kg = (allocation.released_quantity_kg or ZERO) + quantity
    if allocation.released_quantity_kg >= allocation.quantity_kg:
        allocation.holds_reservation = False
    if REVERIFY[kind]:
        require_reverification(lot, f"{quantity} kg released ({kind.replace('_', ' ')}); confirm usable capacity before it is offered again")
    else:
        refresh_lot_status(lot)
    session.flush()
    if organization_id is None:
        from src.backend.app.identity.application.tenancy import organization_of
        organization_id = organization_of(session, "allocation", allocation.id)
    record_system_event(session, organization_id, "allocation.reservation_released", "requirement", allocation.requirement_id, {
        "allocation_id": str(allocation.id), "production_lot_id": str(lot.id), "quantity_kg": str(quantity),
        "released_total_kg": str(allocation.released_quantity_kg), "commitment_kg": str(allocation.quantity_kg),
        "kind": kind, "attribution": ATTRIBUTION[kind], "reason": reason, "reverification_required": REVERIFY[kind],
        **(detail or {})}, correlation_id=correlation_id or uuid4(), actor_id=actor_id, actor_type=actor_type)
    return quantity


def release_remaining(session: Session, allocation: SupplyAllocation, **kwargs) -> Decimal:
    """Release whatever is still reserved and undelivered. Idempotent: a second call releases nothing."""
    return release(session, allocation, releasable_kg(session, allocation), **kwargs)
