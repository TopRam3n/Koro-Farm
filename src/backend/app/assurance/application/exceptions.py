"""Deterministic supply-exception detection (no language model).

Called by the worker (app/worker.py) for outbox events and timers, and by people through the exceptions API.
Every function works inside the caller's transaction and locks the rows it changes, so the exception, the
order's health and the events describing them change together or not at all.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import SYSTEM_ACTOR, record_event, record_system_event
from src.backend.app.assurance.domain.exceptions import ExceptionKind, ExceptionStatus, SupplyException
from src.backend.app.assurance.domain.models import RecoveryRun, RecoveryStatus
from src.backend.app.demand.domain.models import Buyer, Requirement, SupplyHealth
from src.backend.app.supply.application.capacity import free_kg, requirement_exposure
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, ConsentStatus, SupplyAllocation,
)

ZERO = Decimal("0")
FRESH = {"populate_existing": True}


class ExceptionActionError(ValueError):
    pass


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _organization_of(session: Session, requirement: Requirement) -> UUID:
    return session.scalar(select(Buyer.organization_id).where(Buyer.id == requirement.buyer_id))


def _lock_requirement(session: Session, requirement_id: UUID) -> Requirement:
    return session.scalar(select(Requirement).where(Requirement.id == requirement_id).with_for_update().execution_options(**FRESH))


def _open(session: Session, dedupe_key: str) -> SupplyException | None:
    return session.scalar(select(SupplyException).where(
        SupplyException.dedupe_key == dedupe_key, SupplyException.status == ExceptionStatus.OPEN,
    ).with_for_update().execution_options(**FRESH))


def _open_exception(session: Session, requirement: Requirement, kind: ExceptionKind, dedupe_key: str, shortfall: Decimal,
                    summary: str, details: dict, source_event_id: UUID | None) -> tuple[SupplyException, bool]:
    """Open an exception, or return the existing OPEN one with the same dedupe key. Returns (exception, created)."""
    existing = _open(session, dedupe_key)
    if existing is not None:
        return existing, False
    organization_id = _organization_of(session, requirement)
    row = SupplyException(organization_id=organization_id, requirement_id=requirement.id, kind=kind, status=ExceptionStatus.OPEN,
                          dedupe_key=dedupe_key, shortfall_kg=shortfall, summary=summary, details=details,
                          source_event_id=source_event_id)
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        # A concurrent detector opened it first (partial unique index on OPEN dedupe keys): use that one.
        existing = _open(session, dedupe_key)
        if existing is None:
            raise
        return existing, False
    record_system_event(session, organization_id, "exception.opened", "requirement", requirement.id, {
        "exception_id": str(row.id), "kind": kind.value, "shortfall_kg": str(shortfall), "summary": summary,
        "details": details}, causation_id=source_event_id)
    return row, True


def _resolve(session: Session, row: SupplyException, requirement: Requirement, resolved_by: str, resolution: str,
             source_event_id: UUID | None = None) -> None:
    row.status = ExceptionStatus.RESOLVED
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = resolved_by
    row.resolution = resolution
    row.updated_at = row.resolved_at
    record_system_event(session, row.organization_id, "exception.resolved", "requirement", requirement.id, {
        "exception_id": str(row.id), "kind": row.kind.value, "resolved_by": resolved_by, "resolution": resolution},
        causation_id=source_event_id, actor_id=resolved_by)


def resolve_for_ended_order(session: Session, requirement: Requirement, resolved_by: str, outcome: str) -> int:
    """An order that ended (closed or cancelled) needs no further supply action. Its open exceptions are resolved with
    the outcome; the exception records and their history stay."""
    rows = session.scalars(select(SupplyException).where(SupplyException.requirement_id == requirement.id,
                                                         SupplyException.status == ExceptionStatus.OPEN)).all()
    for row in rows:
        _resolve(session, row, requirement, resolved_by, f"order ended ({outcome}); no further supply action")
    return len(rows)


def open_incident_exception(session: Session, requirement: Requirement, kind: str, dedupe_key: str, shortfall: Decimal,
                            summary: str, details: dict) -> SupplyException:
    """A dropout or quality rejection, recorded in the caller's transaction as an actionable exception.

    Its `exception.opened` outbox event starts (or joins) the order's recovery task, so the incident cannot be left
    without a task even though recovery itself now needs approval.
    """
    row, _ = _open_exception(session, requirement, ExceptionKind(kind), dedupe_key, shortfall, summary, details, None)
    return row


# Incidents a recovery closes once the order's shortfall is covered. Capacity shortfalls close only when exposure does.
RECOVERABLE_KINDS = (ExceptionKind.SUPPLIER_DROPOUT, ExceptionKind.QUALITY_REJECTION, ExceptionKind.RESPONSE_OVERDUE,
                     ExceptionKind.STANDBY_EXPIRED, ExceptionKind.DEMAND_INCREASE, ExceptionKind.OVER_COMMITTED,
                     ExceptionKind.ELIGIBILITY_CHANGED, ExceptionKind.LOT_UNAVAILABLE)


def resolve_recovered(session: Session, requirement: Requirement, resolved_by: str, resolution: str) -> int:
    """Close the order's open incident exceptions after its shortfall has been covered."""
    rows = session.scalars(select(SupplyException).where(
        SupplyException.requirement_id == requirement.id, SupplyException.status == ExceptionStatus.OPEN,
        SupplyException.kind.in_(RECOVERABLE_KINDS)).with_for_update()).all()
    for row in rows:
        _resolve(session, row, requirement, resolved_by, resolution)
    return len(rows)


def _open_count(session: Session, requirement_id: UUID) -> int:
    return session.scalar(select(func.count(SupplyException.id)).where(
        SupplyException.requirement_id == requirement_id, SupplyException.status == ExceptionStatus.OPEN)) or 0


def _committed_cover(session: Session, requirement_id: UUID) -> Decimal:
    from src.backend.app.assurance.application.recovery import _coverage
    return _coverage(session, requirement_id)


def _restore_health_if_clear(session: Session, requirement: Requirement, source_event_id: UUID | None) -> None:
    if requirement.supply_health != SupplyHealth.AT_RISK or _open_count(session, requirement.id):
        return
    if _committed_cover(session, requirement.id) >= requirement.required_quantity_kg:
        requirement.supply_health = SupplyHealth.COVERED
        record_system_event(session, _organization_of(session, requirement), "requirement.covered", "requirement",
                            requirement.id, {"cause": "open supply exceptions resolved"}, causation_id=source_event_id)


def sync_capacity_exception(session: Session, requirement_id: UUID, source_event_id: UUID | None = None) -> SupplyException | None:
    """Make the order's CAPACITY_SHORTFALL exception match its current exposure (open, update or resolve)."""
    requirement = _lock_requirement(session, requirement_id)
    if requirement is None:
        return None
    exposed, by_allocation, lots = requirement_exposure(session, requirement.id)
    key = f"capacity:{requirement.id}"
    current = _open(session, key)
    if exposed > 0:
        details = {"lots": lots, "allocations": [
            {"allocation_id": str(item.allocation.id), "committed_kg": str(item.allocation.quantity_kg),
             "covered_kg": str(item.covered_kg), "exposed_kg": str(item.exposed_kg)}
            for item in by_allocation.values() if item.exposed_kg > 0]}
        summary = f"Reported capacity no longer covers {exposed} kg of confirmed commitments"
        row, created = _open_exception(session, requirement, ExceptionKind.CAPACITY_SHORTFALL, key, exposed, summary,
                                       details, source_event_id)
        if not created and (row.shortfall_kg != exposed or row.details != details):
            row.shortfall_kg, row.details, row.summary = exposed, details, summary
            row.updated_at = datetime.now(timezone.utc)
            record_system_event(session, row.organization_id, "exception.updated", "requirement", requirement.id, {
                "exception_id": str(row.id), "shortfall_kg": str(exposed)}, causation_id=source_event_id)
        if requirement.supply_health in (SupplyHealth.COVERED, SupplyHealth.UNPLANNED, SupplyHealth.RECOVERING):
            requirement.supply_health = SupplyHealth.AT_RISK
            record_system_event(session, row.organization_id, "requirement.at_risk", "requirement", requirement.id, {
                "cause": "supplier capacity report", "exposed_kg": str(exposed), "exception_id": str(row.id)},
                causation_id=source_event_id)
        session.flush()
        return row
    if current is not None:
        _resolve(session, current, requirement, SYSTEM_ACTOR, "Reported capacity again covers all confirmed commitments",
                 source_event_id)
        session.flush()
        _restore_health_if_clear(session, requirement, source_event_id)
    return None


def reevaluate_lot(session: Session, lot_id: UUID, source_event_id: UUID | None = None) -> list[UUID]:
    """Re-sync capacity exceptions for every order with confirmed commitments on the lot."""
    requirement_ids = session.scalars(select(SupplyAllocation.requirement_id).where(
        SupplyAllocation.production_lot_id == lot_id,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    ).distinct()).all()
    for requirement_id in sorted(requirement_ids, key=str):  # stable lock order across workers
        sync_capacity_exception(session, requirement_id, source_event_id)
    return list(requirement_ids)


def _release(session: Session, allocation: SupplyAllocation, kind: str, reason: str) -> None:
    from src.backend.app.supply.application.release import release_remaining
    release_remaining(session, allocation, kind=kind, reason=reason, actor_id=SYSTEM_ACTOR)


def _lock_allocation(session: Session, allocation_id: UUID) -> SupplyAllocation | None:
    return session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update().execution_options(**FRESH))


def send_reminder(session: Session, allocation_id: UUID, now: datetime) -> bool:
    """At half of the response window, record an in-app reminder. Idempotent."""
    allocation = _lock_allocation(session, allocation_id)
    if allocation is None or allocation.status != AllocationStatus.SOLICITED or allocation.reminder_sent_at is not None:
        return False
    due, asked = _aware(allocation.response_due_at), _aware(allocation.solicited_at)
    if due is None or asked is None or now < asked + (due - asked) / 2 or now >= due:
        return False
    allocation.reminder_sent_at = now
    requirement = session.get(Requirement, allocation.requirement_id)
    record_system_event(session, _organization_of(session, requirement), "solicitation.reminder_due", "requirement",
                        requirement.id, {"allocation_id": str(allocation.id), "response_due_at": due.isoformat()})
    return True


def expire_overdue_response(session: Session, allocation_id: UUID, now: datetime) -> SupplyException | None:
    """At the deadline an unanswered request expires. Silence is not acceptance, refusal or permission."""
    from src.backend.app.assurance.application.recovery import refresh_after_decline
    allocation = _lock_allocation(session, allocation_id)
    if allocation is None or allocation.status != AllocationStatus.SOLICITED:
        return None
    due = _aware(allocation.response_due_at)
    if due is None or due > now:
        return None
    requirement = _lock_requirement(session, allocation.requirement_id)
    _release(session, allocation, "request_expired", "no supplier response before the deadline")
    allocation.status = AllocationStatus.EXPIRED
    organization_id = _organization_of(session, requirement)
    event = record_system_event(session, organization_id, "solicitation.expired", "requirement", requirement.id, {
        "allocation_id": str(allocation.id), "role": allocation.role.value, "quantity_kg": str(allocation.quantity_kg),
        "response_due_at": due.isoformat(), "interpretation": "no response; not acceptance, refusal or permission"})
    row, _ = _open_exception(
        session, requirement, ExceptionKind.RESPONSE_OVERDUE, f"overdue:{allocation.id}", allocation.quantity_kg,
        f"No supplier response before the deadline for {allocation.quantity_kg} kg ({allocation.role.value.lower()})",
        {"allocation_id": str(allocation.id), "response_due_at": due.isoformat()}, event.id)
    session.flush()
    refresh_after_decline(session, requirement, event.correlation_id)
    return row


def expire_standby(session: Session, allocation_id: UUID, today: date) -> SupplyException | None:
    """An expired standby authorization becomes ineligible and releases its stock.

    Contingency cover is flagged as degraded. An actionable exception opens only when recovery is affected:
    an active recovery or capacity shortfall on the order that remaining authorized standby cannot cover.
    Committed supply is never touched.
    """
    from src.backend.app.assurance.application.recovery import authorized_standby
    allocation = _lock_allocation(session, allocation_id)
    if (allocation is None or allocation.status != AllocationStatus.STANDBY or allocation.authorization_valid_until is None
            or allocation.authorization_valid_until >= today):
        return None
    requirement = _lock_requirement(session, allocation.requirement_id)
    _release(session, allocation, "standby_expired", "standby authorization reached its end date")
    allocation.status = AllocationStatus.EXPIRED
    session.flush()
    from src.backend.app.supply.domain.planning_models import obligation_sql
    remaining = session.scalar(select(func.coalesce(func.sum(obligation_sql()), 0)).where(
        SupplyAllocation.requirement_id == requirement.id, *authorized_standby())) or ZERO
    organization_id = _organization_of(session, requirement)
    event = record_system_event(session, organization_id, "standby.expired", "requirement", requirement.id, {
        "allocation_id": str(allocation.id), "quantity_kg": str(allocation.quantity_kg),
        "authorization_valid_until": allocation.authorization_valid_until.isoformat(),
        "authorized_standby_remaining_kg": str(remaining), "contingency_degraded": True})
    run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id,
                                                   RecoveryRun.status.in_([RecoveryStatus.RUNNING, RecoveryStatus.ESCALATED])))
    capacity = _open(session, f"capacity:{requirement.id}")
    needed = max(run.remaining_shortfall_kg if run else ZERO, capacity.shortfall_kg if capacity else ZERO)
    if needed > remaining:
        row, _ = _open_exception(
            session, requirement, ExceptionKind.STANDBY_EXPIRED, f"standby-expiry:{requirement.id}", needed - remaining,
            f"Expired standby leaves {needed - remaining} kg of an active shortfall without authorized cover",
            {"expired_allocation_id": str(allocation.id), "needed_kg": str(needed), "authorized_standby_remaining_kg": str(remaining)},
            event.id)
        return row
    return None


def acknowledge(session: Session, actor, exception_id: UUID) -> SupplyException:
    row = session.scalar(select(SupplyException).where(SupplyException.id == exception_id).with_for_update())
    if row.status != ExceptionStatus.OPEN:
        raise ExceptionActionError("only an open exception can be acknowledged")
    if row.acknowledged_at is None:
        row.acknowledged_at = datetime.now(timezone.utc)
        row.acknowledged_by_user_id = actor.user_id
        record_event(session, actor, "exception.acknowledged", "requirement", row.requirement_id, {"exception_id": str(row.id)})
    return row


def resolve_manually(session: Session, actor, exception_id: UUID, resolution: str) -> SupplyException:
    row = session.scalar(select(SupplyException).where(SupplyException.id == exception_id).with_for_update())
    if row.status != ExceptionStatus.OPEN:
        raise ExceptionActionError("the exception is already resolved")
    requirement = _lock_requirement(session, row.requirement_id)
    if row.kind == ExceptionKind.CAPACITY_SHORTFALL and requirement_exposure(session, requirement.id)[0] > 0:
        raise ExceptionActionError("confirmed commitments are still exposed; it resolves when capacity covers them again")
    row.status = ExceptionStatus.RESOLVED
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = str(actor.user_id)
    row.resolution = resolution
    row.updated_at = row.resolved_at
    record_event(session, actor, "exception.resolved", "requirement", requirement.id,
                 {"exception_id": str(row.id), "kind": row.kind.value, "resolution": resolution})
    session.flush()
    _restore_health_if_clear(session, requirement, None)
    return row


# --- Buyer changes and lot eligibility (R1 WP4: M6, P7, P9) ----------------------------------------------------------

def _sync_kind(session: Session, requirement: Requirement, kind: ExceptionKind, key: str, quantity: Decimal, summary: str,
               details: dict, actor: str, resolution: str) -> SupplyException | None:
    current = _open(session, key)
    if quantity > 0:
        row, created = _open_exception(session, requirement, kind, key, quantity, summary, details, None)
        if not created and (row.shortfall_kg != quantity or row.summary != summary):
            row.shortfall_kg, row.summary, row.details, row.updated_at = quantity, summary, details, datetime.now(timezone.utc)
            record_system_event(session, row.organization_id, "exception.updated", "requirement", requirement.id,
                                {"exception_id": str(row.id), "shortfall_kg": str(quantity)})
        return row
    if current is not None:
        _resolve(session, current, requirement, actor, resolution)
    return None


def sync_demand_exceptions(session: Session, requirement: Requirement) -> dict:
    """After a buyer change: a shortfall opens DEMAND_INCREASE, committed cover above the order opens OVER_COMMITTED.
    Nothing is released or requested here; the recovery agent proposes and a person approves."""
    from src.backend.app.agents.application.evidence import basis_of
    session.flush()
    basis, _ = basis_of(session, requirement)
    surplus = max(basis.assured_kg - basis.required_kg, ZERO)
    gap = basis.gap_kg
    _sync_kind(session, requirement, ExceptionKind.DEMAND_INCREASE, f"demand:{requirement.id}", gap,
               f"The buyer's quantity leaves {gap} kg without committed cover", {"required_kg": str(basis.required_kg),
               "assured_kg": str(basis.assured_kg)}, SYSTEM_ACTOR, "Committed cover again meets the order quantity")
    _sync_kind(session, requirement, ExceptionKind.OVER_COMMITTED, f"over-committed:{requirement.id}", surplus,
               f"Commitments exceed the buyer's quantity by {surplus} kg", {"required_kg": str(basis.required_kg),
               "assured_kg": str(basis.assured_kg)}, SYSTEM_ACTOR, "Commitments no longer exceed the order quantity")
    if gap > 0 and requirement.supply_health in (SupplyHealth.COVERED, SupplyHealth.UNPLANNED):
        requirement.supply_health = SupplyHealth.AT_RISK
    elif gap <= 0 and requirement.supply_health == SupplyHealth.AT_RISK and not _open_count(session, requirement.id):
        requirement.supply_health = SupplyHealth.COVERED
    return {"gap_kg": str(gap), "surplus_kg": str(surplus)}


def eligibility_problems(lot: ProductionLot, requirement: Requirement, today: date) -> list[str]:
    problems = []
    if lot.crop != requirement.crop:
        problems.append("crop differs from the order")
    if lot.quality_grade_estimate != requirement.grade:
        problems.append(f"lot is now declared Grade {lot.quality_grade_estimate.value}; the order needs Grade {requirement.grade.value}")
    if lot.harvest_start > requirement.delivery_window_end or lot.harvest_end < requirement.delivery_window_start:
        problems.append("harvest window no longer overlaps the delivery window")
    return problems


def unavailability(lot: ProductionLot, requirement: Requirement, today: date) -> str | None:
    if lot.withdrawn_at is not None:
        return f"the lot was withdrawn: {lot.withdrawal_reason}"
    if lot.viable_until is not None and lot.viable_until < max(today, requirement.delivery_window_start):
        return f"the produce is viable only until {lot.viable_until.isoformat()}"
    return None


def assess_lot_eligibility(session: Session, lot_id: UUID, source_event_id: UUID | None = None) -> list[UUID]:
    """Re-check every order with live allocations on a lot after its declaration changed (P7, P9).

    Opens ELIGIBILITY_CHANGED when grade, crop or harvest window no longer match, LOT_UNAVAILABLE when verified
    withdrawal or expiry affects undelivered commitments, and resolves either when it no longer applies. Agreed
    commitments are never changed here; recovery stays approval-controlled."""
    from src.backend.app.supply.application.release import received_kg
    lot = session.get(ProductionLot, lot_id)
    today = datetime.now(timezone.utc).date()
    live = (AllocationStatus.COMMITTED, AllocationStatus.STANDBY, AllocationStatus.SOLICITED, AllocationStatus.PROPOSED)
    rows = session.scalars(select(SupplyAllocation).where(SupplyAllocation.production_lot_id == lot_id,
                                                          SupplyAllocation.status.in_(live))).all()
    by_requirement: dict[UUID, list[SupplyAllocation]] = {}
    for allocation in rows:
        by_requirement.setdefault(allocation.requirement_id, []).append(allocation)
    for requirement_id in sorted(by_requirement, key=str):
        requirement = _lock_requirement(session, requirement_id)
        allocations = by_requirement[requirement_id]
        undelivered = sum((max(a.obligation_kg - received_kg(session, a.id), ZERO) for a in allocations
                           if a.status == AllocationStatus.COMMITTED), ZERO)
        problems = eligibility_problems(lot, requirement, today)
        quantity = sum((a.obligation_kg for a in allocations), ZERO) if problems else ZERO
        _sync_kind(session, requirement, ExceptionKind.ELIGIBILITY_CHANGED, f"eligibility:{requirement.id}:{lot.id}", quantity,
                   f"Lot no longer matches this order: {'; '.join(problems)}" if problems else "",
                   {"production_lot_id": str(lot.id), "problems": problems,
                    "allocations": [str(a.id) for a in allocations]}, SYSTEM_ACTOR, "The lot matches the order again")
        reason = unavailability(lot, requirement, today)
        _sync_kind(session, requirement, ExceptionKind.LOT_UNAVAILABLE, f"lot-unavailable:{requirement.id}:{lot.id}",
                   undelivered if reason else ZERO, f"{undelivered} kg of undelivered commitments are affected: {reason}" if reason else "",
                   {"production_lot_id": str(lot.id), "reason": reason}, SYSTEM_ACTOR, "The lot is available again")
        if (problems or reason) and requirement.supply_health in (SupplyHealth.COVERED, SupplyHealth.RECOVERING):
            requirement.supply_health = SupplyHealth.AT_RISK
    session.flush()
    return list(by_requirement)
