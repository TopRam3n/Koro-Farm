"""Supplier capacity reports and exposure.

Quantities on a production lot:

* expected_quantity_kg  - the declared harvest.
* available_quantity_kg - planning availability: the most the platform may plan from the lot, delivered stock
                          included. Changed by declarations (coordinator create/edit with provenance, the farmer's
                          own ready-stock declaration) and by a farmer's own capacity report that offers more.
                          A coordinator-relayed report never raises it, and no report lowers it.
* reserved_quantity_kg  - held by accepted commitments, authorized standby and marketplace orders, delivered
                          stock included (receipts do not release reservations).
* reported_capacity_kg  - the capacity ceiling from the latest applied report: what had been delivered when the
                          report was made plus what the supplier said they could still supply. Later receipts move
                          stock from "still to supply" to "delivered" and leave the ceiling unchanged.
* delivered             - received against the lot's allocations (received_sublots), from any allocation.

Derived:

* effective capacity = min(planning availability, ceiling)
* free stock         = max(0, effective capacity - reserved)      (used by every path that reserves stock)
* exposure           = undelivered committed quantity the ceiling no longer covers

A supplier reports what they can still supply, so delivered stock is never counted twice and never offered again.
Commitments are never modified by a report. Delivered quantity is always covered; the rest of the ceiling covers
the undelivered part of commitments, earliest accepted first ("first agreed, first protected"), then authorized
standby, earliest authorized first. Reports, acceptances and receipts on a lot serialize on the lot's row lock.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode
from src.backend.app.supply.domain.capacity import CapacityChannel, CapacityReport, CapacityVerification
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationStatus, ConsentStatus, SupplyAllocation

ZERO = Decimal("0")


class CapacityError(ValueError):
    """Conflicts with current state (HTTP 409) or invalid input (HTTP 422, see `status`)."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class CapacityForbidden(PermissionError):
    pass


def effective_capacity(lot: ProductionLot) -> Decimal:
    if lot.reported_capacity_kg is None:
        return lot.available_quantity_kg
    return min(lot.available_quantity_kg, lot.reported_capacity_kg)


def free_kg(lot: ProductionLot) -> Decimal:
    """Stock that may still be reserved. Never negative."""
    return max(effective_capacity(lot) - lot.reserved_quantity_kg, ZERO)


def effective_capacity_sql():
    """SQL equivalent of effective_capacity, for queries that select lots with free stock."""
    return case(
        (ProductionLot.reported_capacity_kg.is_(None), ProductionLot.available_quantity_kg),
        (ProductionLot.reported_capacity_kg < ProductionLot.available_quantity_kg, ProductionLot.reported_capacity_kg),
        else_=ProductionLot.available_quantity_kg,
    )


def has_free_stock_sql():
    return effective_capacity_sql() > ProductionLot.reserved_quantity_kg


def free_kg_sql():
    return effective_capacity_sql() - ProductionLot.reserved_quantity_kg


@dataclass
class AllocationExposure:
    allocation: SupplyAllocation
    covered_kg: Decimal
    exposed_kg: Decimal


@dataclass
class LotExposure:
    lot: ProductionLot
    commitments: list[AllocationExposure] = field(default_factory=list)
    # Uncovered quantity of each authorized standby allocation on this lot; together they never exceed the lot's
    # actual standby shortfall, so totals for one order or across orders cannot double count.
    standby_uncovered: dict[UUID, Decimal] = field(default_factory=dict)

    @property
    def exposed_kg(self) -> Decimal:
        return sum((item.exposed_kg for item in self.commitments), ZERO)

    @property
    def standby_uncovered_kg(self) -> Decimal:
        return sum(self.standby_uncovered.values(), ZERO)


def delivered_by_allocation(session: Session, lot_id: UUID) -> dict[UUID, Decimal]:
    """Quantity received against each allocation on the lot."""
    from src.backend.app.fulfilment.domain.models import ReceivedSublot

    rows = session.execute(select(ReceivedSublot.allocation_id, func.sum(ReceivedSublot.received_quantity_kg))
                           .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
                           .where(SupplyAllocation.production_lot_id == lot_id)
                           .group_by(ReceivedSublot.allocation_id)).all()
    return {allocation_id: Decimal(total or 0) for allocation_id, total in rows}


def delivered_kg(session: Session, lot_id: UUID) -> Decimal:
    return sum(delivered_by_allocation(session, lot_id).values(), ZERO)


def _earliest_first():
    return (func.coalesce(SupplyAllocation.responded_at, SupplyAllocation.created_at), SupplyAllocation.id)


def lot_exposure(session: Session, lot: ProductionLot) -> LotExposure:
    """Attribute any shortfall on a lot: delivered stock is covered; then earliest commitments, then standby."""
    commitments = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.production_lot_id == lot.id,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    ).order_by(*_earliest_first())).all()
    standby = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.production_lot_id == lot.id,
        SupplyAllocation.status == AllocationStatus.STANDBY,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    ).order_by(*_earliest_first())).all()
    result = LotExposure(lot=lot)
    if lot.reported_capacity_kg is None:  # no report: everything is covered
        result.commitments = [AllocationExposure(a, a.quantity_kg, ZERO) for a in commitments]
        result.standby_uncovered = {a.id: ZERO for a in standby}
        return result
    delivered = delivered_by_allocation(session, lot.id)
    budget = max(lot.reported_capacity_kg - sum(delivered.values(), ZERO), ZERO)  # what is still to be supplied
    for allocation in commitments:  # earliest accepted first: they keep their cover
        done = min(delivered.get(allocation.id, ZERO), allocation.quantity_kg)
        outstanding = allocation.quantity_kg - done
        covered = min(outstanding, budget)
        budget -= covered
        result.commitments.append(AllocationExposure(allocation, done + covered, outstanding - covered))
    for allocation in standby:  # earliest authorized first
        covered = min(allocation.quantity_kg, budget)
        budget -= covered
        result.standby_uncovered[allocation.id] = allocation.quantity_kg - covered
    return result


def requirement_exposure(session: Session, requirement_id: UUID) -> tuple[Decimal, dict[UUID, AllocationExposure], list[dict]]:
    """Exposure of one order across all lots it has commitments on."""
    lot_ids = session.scalars(select(SupplyAllocation.production_lot_id).where(
        SupplyAllocation.requirement_id == requirement_id,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    ).distinct()).all()
    by_allocation: dict[UUID, AllocationExposure] = {}
    lots: list[dict] = []
    total = ZERO
    for lot_id in lot_ids:
        lot = session.get(ProductionLot, lot_id)
        exposure = lot_exposure(session, lot)
        mine = [item for item in exposure.commitments if item.allocation.requirement_id == requirement_id]
        for item in mine:
            by_allocation[item.allocation.id] = item
        exposed = sum((item.exposed_kg for item in mine), ZERO)
        total += exposed
        if exposed > 0:
            lots.append({"production_lot_id": str(lot.id), "reported_capacity_kg": str(lot.reported_capacity_kg),
                         "exposed_kg": str(exposed)})
    return total, by_allocation, lots


def _committed_on_lot(session: Session, lot_id: UUID) -> Decimal:
    return session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
        SupplyAllocation.production_lot_id == lot_id,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    )) or ZERO


def record_capacity_report(session: Session, actor: AuthorizationContext, lot_id: UUID, reported_kg: Decimal,
                           *, effective_at: datetime | None, original_source: str | None, attestation_method: str | None,
                           evidence_reference: str | None, key: str | None) -> dict:
    """Store an immutable capacity report and, unless it is stale, apply it to the lot.

    Exception detection is not done here: the report's event is written to the outbox in this transaction and
    the worker (app/worker.py) opens or resolves exceptions from it.
    """
    from src.backend.app.assurance.application.events import record_event, remember, replay_or_none

    command = "capacity.report"
    if (done := replay_or_none(session, command, key)) is not None:
        return done
    if reported_kg < 0:
        raise CapacityError("reported capacity cannot be negative", 422)
    now = datetime.now(timezone.utc)
    effective_at = effective_at or now
    if effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=timezone.utc)
    if effective_at > now:
        raise CapacityError("a capacity report cannot take effect in the future", 422)
    with session.begin_nested() if session.in_transaction() else session.begin():
        lot = session.scalar(select(ProductionLot).where(ProductionLot.id == lot_id).with_for_update()
                             .execution_options(populate_existing=True))
        if lot is None:
            raise CapacityError("production lot not found", 404)
        if (done := replay_or_none(session, command, key)) is not None:
            return done
        if actor.role == RoleCode.FARMER:
            if actor.farmer_id is None or actor.farmer_id != lot.farmer_id:
                raise CapacityForbidden("farmers may report capacity only for their own production lots")
            channel, verification = CapacityChannel.FARMER_PORTAL, CapacityVerification.SELF_REPORTED
            original_source = (original_source or "farmer portal").strip()
            attestation_method = (attestation_method or "farmer portal sign-in").strip()
        else:
            if PermissionCode.SUPPLY_MANAGE not in actor.permissions:
                raise CapacityForbidden("recording capacity on a farmer's behalf requires supply management permission")
            if not original_source or len(original_source.strip()) < 3 or not attestation_method or len(attestation_method.strip()) < 3:
                raise CapacityError("a relayed report must state its original source and attestation method", 422)
            channel, verification = CapacityChannel.COORDINATOR_RELAYED, CapacityVerification.COORDINATOR_ATTESTED
            original_source, attestation_method = original_source.strip(), attestation_method.strip()
        delivered = delivered_kg(session, lot.id)
        if delivered + reported_kg > lot.expected_quantity_kg:
            raise CapacityError(
                f"the declared harvest is {lot.expected_quantity_kg} kg and {delivered} kg has already been delivered, "
                f"so at most {lot.expected_quantity_kg - delivered} kg can still be supplied; "
                "update the lot declaration first if the harvest is larger", 422)
        ceiling = delivered + reported_kg

        last = lot.capacity_reported_at
        if last is not None and last.tzinfo is None:  # SQLite returns naive UTC datetimes
            last = last.replace(tzinfo=timezone.utc)
        stale = last is not None and effective_at < last
        previous = lot.reported_capacity_kg
        committed = _committed_on_lot(session, lot.id)
        report = CapacityReport(
            organization_id=actor.organization_id, production_lot_id=lot.id, farmer_id=lot.farmer_id,
            reported_capacity_kg=reported_kg, previous_reported_kg=previous, committed_at_report_kg=committed,
            effective_at=effective_at, channel=channel, original_source=original_source,
            attestation_method=attestation_method, evidence_reference=evidence_reference,
            verification_status=verification, applied=not stale, recorded_by_user_id=actor.user_id,
            delivered_at_report_kg=delivered)
        session.add(report)
        availability_raised_from = None
        if not stale:
            lot.reported_capacity_kg = ceiling
            lot.capacity_reported_at = effective_at
            # Only the farmer's own report can offer more than planning availability; a relayed report constrains
            # but never restores stock a declaration removed. No report lowers availability: the ceiling does that.
            if channel == CapacityChannel.FARMER_PORTAL and ceiling > lot.available_quantity_kg:
                availability_raised_from = lot.available_quantity_kg
                lot.available_quantity_kg = ceiling
            lot.status = ProductionLotStatus.AVAILABLE if free_kg(lot) > 0 else ProductionLotStatus.UNAVAILABLE
            lot.version += 1
        session.flush()
        exposed = lot_exposure(session, lot).exposed_kg if not stale else ZERO
        record_event(session, actor, "lot.capacity_reported", "production_lot", lot.id, {
            "capacity_report_id": str(report.id), "production_lot_id": str(lot.id), "farmer_id": str(lot.farmer_id),
            "reported_capacity_kg": str(reported_kg), "delivered_kg": str(delivered), "capacity_ceiling_kg": str(ceiling),
            "previous_ceiling_kg": str(previous) if previous is not None else None,
            "availability_raised_from_kg": str(availability_raised_from) if availability_raised_from is not None else None,
            "committed_kg": str(committed), "exposed_kg": str(exposed), "applied": not stale,
            "channel": channel.value, "verification_status": verification.value,
            "effective_at": effective_at.isoformat(), "original_source": original_source,
            "attestation_method": attestation_method, "evidence_reference": evidence_reference,
        }, idempotency_key=key)
        result = {"capacity_report_id": str(report.id), "production_lot_id": str(lot.id), "applied": not stale,
                  "reported_capacity_kg": str(reported_kg), "delivered_kg": str(delivered), "capacity_ceiling_kg": str(ceiling),
                  "committed_kg": str(committed), "exposed_kg": str(exposed),
                  "free_kg": str(free_kg(lot)), "channel": channel.value, "verification_status": verification.value}
        remember(session, command, key, result)
        return result
