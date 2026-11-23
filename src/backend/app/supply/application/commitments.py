"""Supplier solicitation and evidenced responses.

The only path from a proposed or solicited allocation to committed coverage (or authorized standby) is
`respond` with an ACCEPTED decision. That writes an immutable SupplierConsent record and, under a row
lock on the lot, re-checks free capacity before reserving it. Nothing here infers agreement.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event
from src.backend.app.assurance.domain.models import CommandDeduplication
from src.backend.app.demand.domain.models import Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import (
    AllocationRole,
    AllocationStatus,
    ConsentChannel,
    ConsentDecision,
    ConsentStatus,
    ConsentType,
    SupplierConsent,
    SupplyAllocation,
)

OPEN_STATES = {AllocationStatus.PROPOSED, AllocationStatus.SOLICITED}


class CommitmentError(ValueError):
    """A request that conflicts with current state (maps to HTTP 409)."""


class CommitmentForbidden(PermissionError):
    """The caller may not record this decision (maps to HTTP 403)."""


@dataclass(frozen=True)
class SupplierResponse:
    decision: ConsentDecision
    attestation_method: str
    evidence_reference: str | None = None
    accepted_quantity_kg: Decimal | None = None
    activation_conditions: str | None = None
    valid_until: date | None = None
    note: str | None = None
    channel: ConsentChannel | None = None  # forced for farmers; SYNTHETIC_FIXTURE only from the demo seed


def _replay(session: Session, command: str, key: str | None) -> dict | None:
    if not key:
        return None
    row = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == command,
                                                            CommandDeduplication.idempotency_key == key))
    return row.result if row else None


def _remember(session: Session, command: str, key: str | None, result: dict) -> dict:
    if key:
        session.add(CommandDeduplication(command_type=command, idempotency_key=key, result=result))
    return result


def _lock(session: Session, allocation_id: UUID) -> tuple[SupplyAllocation, Requirement, ProductionLot]:
    # populate_existing: if these rows were already loaded in this session, refresh them from the locked
    # row. Otherwise a transaction that waited for the lock would act on stale state and double-accept.
    fresh = {"populate_existing": True}
    allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id)
                                .with_for_update().execution_options(**fresh))
    if allocation is None:
        raise CommitmentError("allocation not found")
    requirement = session.scalar(select(Requirement).where(Requirement.id == allocation.requirement_id)
                                 .with_for_update().execution_options(**fresh))
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == allocation.production_lot_id)
                         .with_for_update().execution_options(**fresh))
    return allocation, requirement, lot


def _state(allocation: SupplyAllocation) -> dict:
    return {"allocation_id": str(allocation.id), "status": allocation.status.value, "role": allocation.role.value,
            "quantity_kg": str(allocation.quantity_kg), "consent_status": allocation.consent_status.value}


def solicit(session: Session, actor: AuthorizationContext, allocation_id: UUID, message: str | None, key: str | None) -> dict:
    """Record that a proposal was put to the supplier. It does not reserve stock or count as coverage."""
    if (done := _replay(session, "allocation.solicit", key)) is not None:
        return done
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation, requirement, lot = _lock(session, allocation_id)
        if allocation.status != AllocationStatus.PROPOSED:
            raise CommitmentError(f"only a proposed allocation can be solicited (it is {allocation.status.value})")
        if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
            raise CommitmentError("the order has been cancelled")
        allocation.status = AllocationStatus.SOLICITED
        allocation.solicited_at = datetime.now(timezone.utc)
        record_event(session, actor, "solicitation.sent", "requirement", requirement.id, {
            "allocation_id": str(allocation.id), "farmer_id": str(lot.farmer_id), "production_lot_id": str(lot.id),
            "role": allocation.role.value, "quantity_kg": str(allocation.quantity_kg), "message": message,
        }, idempotency_key=key)
        return _remember(session, "allocation.solicit", key, _state(allocation))


def withdraw(session: Session, actor: AuthorizationContext, allocation_id: UUID, reason: str, key: str | None) -> dict:
    """The coordinator stops asking. Any reservation held for the allocation is released."""
    if (done := _replay(session, "allocation.withdraw", key)) is not None:
        return done
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation, requirement, lot = _lock(session, allocation_id)
        if allocation.status not in OPEN_STATES:
            raise CommitmentError(f"only a proposed or solicited allocation can be withdrawn (it is {allocation.status.value})")
        if allocation.holds_reservation:
            lot.reserved_quantity_kg -= allocation.quantity_kg
            allocation.holds_reservation = False
        allocation.status = AllocationStatus.WITHDRAWN
        record_event(session, actor, "solicitation.withdrawn", "requirement", requirement.id,
                     {"allocation_id": str(allocation.id), "reason": reason}, idempotency_key=key)
        from src.backend.app.assurance.application.recovery import settle_initial_plan
        session.flush()
        settle_initial_plan(session, requirement)
        return _remember(session, "allocation.withdraw", key, _state(allocation))


def _channel(actor: AuthorizationContext, lot: ProductionLot, requested: ConsentChannel | None) -> ConsentChannel:
    if actor.role == RoleCode.FARMER:
        if actor.farmer_id is None or actor.farmer_id != lot.farmer_id:
            raise CommitmentForbidden("farmers may respond only for their own production lots")
        return ConsentChannel.FARMER_PORTAL
    if requested == ConsentChannel.SYNTHETIC_FIXTURE:
        return ConsentChannel.SYNTHETIC_FIXTURE
    if PermissionCode.SUPPLY_MANAGE not in actor.permissions:
        raise CommitmentForbidden("recording a supplier's decision on their behalf requires supply management permission")
    return ConsentChannel.COORDINATOR_RELAYED


def respond(session: Session, actor: AuthorizationContext, allocation_id: UUID, response: SupplierResponse,
            key: str | None) -> dict:
    """Record a supplier's decision on a solicited allocation."""
    from src.backend.app.assurance.application.recovery import _coverage, apply_accepted_commitment, refresh_after_decline, settle_initial_plan

    command = "allocation.respond"
    if (done := _replay(session, command, key)) is not None:
        return done
    if not response.attestation_method or len(response.attestation_method.strip()) < 3:
        raise CommitmentError("an attestation method is required to record a supplier's decision")
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation, requirement, lot = _lock(session, allocation_id)
        if (done := _replay(session, command, key)) is not None:
            return done
        channel = _channel(actor, lot, response.channel)
        if allocation.status != AllocationStatus.SOLICITED:
            raise CommitmentError(f"allocation is not awaiting a supplier response (it is {allocation.status.value})")
        if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
            raise CommitmentError("the order has been cancelled")
        is_standby = allocation.role == AllocationRole.STANDBY
        now = datetime.now(timezone.utc)
        correlation = uuid4()
        consent_type = ConsentType.STANDBY_AUTHORIZATION if is_standby else ConsentType.COMMITMENT

        if response.decision == ConsentDecision.DECLINED:
            if allocation.holds_reservation:
                lot.reserved_quantity_kg -= allocation.quantity_kg
                allocation.holds_reservation = False
            consent = SupplierConsent(
                organization_id=actor.organization_id, allocation_id=allocation.id, farmer_id=lot.farmer_id,
                production_lot_id=lot.id, consent_type=consent_type, decision=ConsentDecision.DECLINED, channel=channel,
                quantity_kg=allocation.quantity_kg, attestation_method=response.attestation_method.strip(),
                evidence_reference=response.evidence_reference, note=response.note, recorded_by_user_id=actor.user_id)
            session.add(consent)
            session.flush()
            allocation.status = AllocationStatus.DECLINED
            allocation.responded_at = now
            record_event(session, actor, "supplier.declined", "requirement", requirement.id, {
                "allocation_id": str(allocation.id), "consent_id": str(consent.id), "channel": channel.value,
                "role": allocation.role.value, "quantity_kg": str(allocation.quantity_kg)},
                idempotency_key=key, correlation_id=correlation)
            refresh_after_decline(session, requirement, correlation, actor)
            result = {**_state(allocation), "consent_id": str(consent.id), "channel": channel.value,
                      "supply_health": requirement.supply_health.value, "committed_kg": str(_coverage(session, requirement.id))}
            return _remember(session, command, key, result)

        quantity = response.accepted_quantity_kg if response.accepted_quantity_kg is not None else allocation.quantity_kg
        if quantity <= 0 or quantity > allocation.quantity_kg:
            raise CommitmentError("accepted quantity must be positive and no more than the quantity requested")
        if is_standby and not (response.activation_conditions and response.activation_conditions.strip()):
            raise CommitmentError("standby authorization must state its activation conditions")
        if response.valid_until is not None and response.valid_until < now.date():
            raise CommitmentError("authorization expiry date is in the past")
        if allocation.holds_reservation:
            lot.reserved_quantity_kg -= allocation.quantity_kg - quantity
        else:
            free = lot.available_quantity_kg - lot.reserved_quantity_kg
            if lot.status != ProductionLotStatus.AVAILABLE or free < quantity:
                raise CommitmentError(f"the lot no longer has {quantity} kg free (free now: {max(free, Decimal('0'))} kg); re-plan this allocation")
            lot.reserved_quantity_kg += quantity
            allocation.holds_reservation = True
        if lot.available_quantity_kg <= lot.reserved_quantity_kg:
            lot.status = ProductionLotStatus.UNAVAILABLE
        proposed = allocation.quantity_kg
        allocation.quantity_kg = quantity
        consent = SupplierConsent(
            organization_id=actor.organization_id, allocation_id=allocation.id, farmer_id=lot.farmer_id,
            production_lot_id=lot.id, consent_type=consent_type, decision=ConsentDecision.ACCEPTED, channel=channel,
            quantity_kg=quantity, attestation_method=response.attestation_method.strip(),
            evidence_reference=response.evidence_reference,
            activation_conditions=response.activation_conditions.strip() if response.activation_conditions else None,
            valid_until=response.valid_until, note=response.note, recorded_by_user_id=actor.user_id)
        session.add(consent)
        session.flush()
        allocation.consent_evidence_id = consent.id
        allocation.consent_status = ConsentStatus.RECORDED
        allocation.responded_at = now
        if is_standby:
            allocation.status = AllocationStatus.STANDBY
            allocation.activation_conditions = consent.activation_conditions
            allocation.authorization_valid_until = consent.valid_until
        else:
            allocation.status = AllocationStatus.COMMITTED
        session.flush()
        record_event(session, actor, "standby.authorized" if is_standby else "supplier.accepted", "requirement",
                     requirement.id, {
                         "allocation_id": str(allocation.id), "consent_id": str(consent.id), "channel": channel.value,
                         "proposed_kg": str(proposed), "accepted_kg": str(quantity),
                         "activation_conditions": consent.activation_conditions,
                         "valid_until": consent.valid_until.isoformat() if consent.valid_until else None,
                         "evidence_reference": consent.evidence_reference},
                     idempotency_key=key, correlation_id=correlation)
        if not is_standby:
            apply_accepted_commitment(session, requirement, allocation, correlation, actor)
        else:
            settle_initial_plan(session, requirement)
        result = {**_state(allocation), "consent_id": str(consent.id), "channel": channel.value,
                  "supply_health": requirement.supply_health.value, "committed_kg": str(_coverage(session, requirement.id))}
        return _remember(session, command, key, result)
