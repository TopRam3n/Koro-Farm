from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage, RecoveryRun, RecoveryStatus
from app.demand.domain.models import Requirement, SupplyHealth
from app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation


def _event(session: Session, name: str, requirement_id: UUID, correlation_id: UUID, payload: dict) -> None:
    event = DomainEvent(event_type=name, aggregate_type="requirement", aggregate_id=requirement_id, correlation_id=correlation_id, actor_type="agent", payload=payload)
    session.add(event); session.flush()
    session.add(OutboxMessage(event_id=event.id, topic=name, payload=payload))


def _coverage(session: Session, requirement_id: UUID) -> Decimal:
    return session.scalar(select(SupplyAllocation.quantity_kg).where(
        SupplyAllocation.requirement_id == requirement_id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
    ).with_only_columns(__import__('sqlalchemy').func.coalesce(__import__('sqlalchemy').func.sum(SupplyAllocation.quantity_kg), 0))) or Decimal("0")


def dropout(session: Session, allocation_id: UUID, reason: str, key: str) -> dict:
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.dropout", CommandDeduplication.idempotency_key == key))
    if existing: return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update())
        if allocation is None: raise ValueError("allocation not found")
        requirement = session.scalar(select(Requirement).where(Requirement.id == allocation.requirement_id).with_for_update())
        if allocation.status == AllocationStatus.LOST: raise ValueError("allocation already lost")
        allocation.status = AllocationStatus.LOST; allocation.lost_at = datetime.now(timezone.utc)
        correlation = uuid4()
        _event(session, "allocation.lost", requirement.id, correlation, {"allocation_id": str(allocation.id), "quantity_kg": str(allocation.quantity_kg), "reason": reason})
        covered = _coverage(session, requirement.id); shortfall = requirement.required_quantity_kg - covered
        if shortfall > 0:
            requirement.supply_health = SupplyHealth.AT_RISK
            _event(session, "requirement.at_risk", requirement.id, correlation, {"shortfall_kg": str(shortfall)})
        run = RecoveryRun(requirement_id=requirement.id, status=RecoveryStatus.RUNNING, active_key="RUNNING", lost_quantity_kg=allocation.quantity_kg, cause=reason, remaining_shortfall_kg=max(shortfall, Decimal("0")))
        session.add(run); session.flush(); _event(session, "recovery.started", requirement.id, correlation, {"recovery_run_id": str(run.id)})
        # Activate only the exact required amount from pre-authorized standby reservations.
        for standby in session.scalars(select(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.STANDBY, SupplyAllocation.status == AllocationStatus.STANDBY).order_by(SupplyAllocation.id).with_for_update()):
            if shortfall <= 0: break
            activated = min(shortfall, standby.quantity_kg)
            standby.quantity_kg -= activated
            session.add(SupplyAllocation(requirement_id=requirement.id, supply_plan_id=standby.supply_plan_id, production_lot_id=standby.production_lot_id, role=AllocationRole.COMMITTED, status=AllocationStatus.COMMITTED, quantity_kg=activated, consent_evidence_id=standby.consent_evidence_id, plan_version=standby.plan_version))
            run.standby_activated_kg += activated; shortfall -= activated
            _event(session, "allocation.standby_activated", requirement.id, correlation, {"source_allocation_id": str(standby.id), "quantity_kg": str(activated)})
        run.remaining_shortfall_kg = max(shortfall, Decimal("0"))
        if shortfall <= 0:
            requirement.supply_health = SupplyHealth.COVERED; run.status = RecoveryStatus.COMPLETED; run.active_key = None; run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.completed", requirement.id, correlation, {"standby_activated_kg": str(run.standby_activated_kg)})
        else:
            requirement.supply_health = SupplyHealth.ESCALATION_REQUIRED; run.status = RecoveryStatus.ESCALATED; run.active_key = None; run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.escalated", requirement.id, correlation, {"remaining_shortfall_kg": str(shortfall)})
        result = {"requirement_id": str(requirement.id), "lost_kg": str(allocation.quantity_kg), "committed_kg": str(_coverage(session, requirement.id)), "supply_health": requirement.supply_health.value, "recovery_status": run.status.value, "standby_activated_kg": str(run.standby_activated_kg), "remaining_shortfall_kg": str(run.remaining_shortfall_kg)}
        session.add(CommandDeduplication(command_type="allocation.dropout", idempotency_key=key, result=result))
        return result
