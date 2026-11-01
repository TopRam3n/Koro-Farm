from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage, RecoveryRun, RecoveryStatus

from sqlalchemy import or_

from src.backend.app.demand.domain.models import Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, ConsentStatus, SupplyAllocation
from src.backend.app.supply.domain.planning_models import SupplyPlan, SupplyPlanStatus
from src.backend.app.economics.domain.calculator import CostBreakdown, allocation_cost, money
from src.backend.app.economics.domain.models import CostSnapshot, LotCostInput
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.risk.application.calculator import create_risk_snapshot
from src.backend.app.identity.application.tenancy import farmers_in_requirement_organization
from src.backend.app.supply.application.capacity import free_kg, free_kg_sql, has_free_stock_sql


def authorized_standby() -> list:
    """Standby that may be activated: the supplier's authorization is recorded and has not expired.

    Allocations whose consent is UNSUPPORTED_LEGACY (planner-generated ids) are never activated.
    """
    return [
        SupplyAllocation.status == AllocationStatus.STANDBY,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
        # UTC, like standby expiry (worker), response validation and the gateway: one authorization day everywhere.
        or_(SupplyAllocation.authorization_valid_until.is_(None),
            SupplyAllocation.authorization_valid_until >= datetime.now(timezone.utc).date()),
    ]


def _event(session: Session, name: str, requirement_id: UUID, correlation_id: UUID, payload: dict) -> None:
    event = DomainEvent(event_type=name, aggregate_type="requirement", aggregate_id=requirement_id, correlation_id=correlation_id,
                        actor_type="agent", payload=payload, occurred_at=datetime.now(timezone.utc))
    session.add(event); session.flush()
    session.add(OutboxMessage(event_id=event.id, topic=name, payload=payload))


def committed_quantity(session: Session, requirement_id: UUID) -> Decimal:
    """Planning truth: active committed capacity, independent of physical grading."""
    allocations = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == requirement_id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    )).all()
    return sum((allocation.quantity_kg for allocation in allocations), Decimal("0"))


def _coverage(session: Session, requirement_id: UUID) -> Decimal:
    """Assured Grade-A coverage used by recovery, kept separate from commitment truth."""
    allocations = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == requirement_id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    )).all()
    return sum((allocation.quantity_kg - (
        session.scalar(select(func.coalesce(func.sum(ReceivedSublot.rejected_quantity_kg), 0)).where(
            ReceivedSublot.allocation_id == allocation.id
        )) or Decimal("0")) for allocation in allocations), Decimal("0"))


def _create_recovery_snapshot(session: Session, requirement: Requirement) -> SupplyPlan:
    """Freeze the *current* committed mix in a new immutable plan and cost snapshot."""
    # Callers may have just activated or accepted allocations.  This service is
    # intentionally usable with autoflush disabled, so snapshot reads must not
    # depend on implicit ORM flushing.
    session.flush()
    allocations = list(session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == requirement.id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
        SupplyAllocation.consent_status == ConsentStatus.RECORDED,
    )))
    version = requirement.plan_version + 1
    committed = _coverage(session, requirement.id)
    standby = session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
        SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.STANDBY,
        *authorized_standby(),
    )) or Decimal("0")
    plan = SupplyPlan(requirement_id=requirement.id, plan_version=version, planner_version="supply-assurance-v1",
                      status=SupplyPlanStatus.FINALIZED, required_quantity_kg=requirement.required_quantity_kg,
                      committed_quantity_kg=committed, standby_quantity_kg=standby,
                      unfilled_quantity_kg=max(requirement.required_quantity_kg - committed, Decimal("0")))
    session.add(plan); session.flush()
    breakdown = CostBreakdown()
    for allocation in allocations:
        cost = session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == allocation.production_lot_id))
        if cost:
            breakdown = breakdown.plus(allocation_cost(allocation.quantity_kg, cost))
    session.add(CostSnapshot(supply_plan_id=plan.id, produce_cost_jmd=breakdown.produce_cost_jmd,
        pickup_cost_jmd=breakdown.pickup_cost_jmd, handling_cost_jmd=breakdown.handling_cost_jmd,
        packaging_cost_jmd=breakdown.packaging_cost_jmd, transport_cost_jmd=breakdown.transport_cost_jmd,
        expected_rejection_cost_jmd=breakdown.expected_rejection_cost_jmd,
        total_landed_cost_jmd=breakdown.total_landed_cost_jmd,
        landed_cost_per_kg_jmd=money(breakdown.total_landed_cost_jmd / committed) if committed else Decimal("0.00"),
        calculation_version="landed-cost-v1"))
    requirement.plan_version = version
    create_risk_snapshot(session, requirement, plan)
    return plan


def _open_recovery_run(session: Session, requirement: Requirement, lost: Decimal, cause: str) -> RecoveryRun:
    """The order's recovery bookkeeping: join the active run, or start one. Nothing is activated here."""
    run = session.scalar(select(RecoveryRun).where(
        RecoveryRun.requirement_id == requirement.id, RecoveryRun.status == RecoveryStatus.RUNNING,
    ).with_for_update())
    shortfall = max(requirement.required_quantity_kg - _coverage(session, requirement.id), Decimal("0"))
    if run is None:
        run = RecoveryRun(requirement_id=requirement.id, status=RecoveryStatus.RUNNING, active_key="RUNNING",
                          lost_quantity_kg=lost, cause=cause, remaining_shortfall_kg=shortfall)
        session.add(run)
    else:
        run.lost_quantity_kg += lost
        run.remaining_shortfall_kg = shortfall
    session.flush()
    return run


def dropout(session: Session, allocation_id: UUID, reason: str, key: str) -> dict:
    """Record that a committed supplier can no longer supply. Recorded immediately; recovery is only proposed.

    The loss, the order's at-risk state, the recovery run and a SUPPLIER_DROPOUT exception are written in one
    transaction. The exception's outbox event starts the recovery agent (agents/application/orchestrator.py), which
    proposes options for approval. No standby is activated and no supplier is asked here (R1 WP3, decision 1).
    """
    from src.backend.app.assurance.application.exceptions import open_incident_exception
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.dropout", CommandDeduplication.idempotency_key == key))
    if existing: return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update())
        if allocation is None: raise ValueError("allocation not found")
        # A competing request may have checked the key before it waited on this
        # allocation lock.  Re-check after acquiring the lock so it observes the
        # first command's durable result rather than treating its LOST state as an
        # error.
        existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.dropout", CommandDeduplication.idempotency_key == key))
        if existing: return existing.result
        requirement = session.scalar(select(Requirement).where(Requirement.id == allocation.requirement_id).with_for_update())
        if allocation.status != AllocationStatus.COMMITTED:
            raise ValueError("only an active committed allocation can be dropped")
        allocation.status = AllocationStatus.LOST; allocation.lost_at = datetime.now(timezone.utc)
        correlation = uuid4()
        _event(session, "allocation.lost", requirement.id, correlation, {"allocation_id": str(allocation.id), "quantity_kg": str(allocation.quantity_kg), "reason": reason})
        covered = _coverage(session, requirement.id); shortfall = requirement.required_quantity_kg - covered
        if shortfall > 0:
            requirement.supply_health = SupplyHealth.AT_RISK
            _event(session, "requirement.at_risk", requirement.id, correlation, {"shortfall_kg": str(shortfall)})
        run = _open_recovery_run(session, requirement, allocation.quantity_kg, reason)
        _event(session, "recovery.started", requirement.id, correlation, {"recovery_run_id": str(run.id)})
        exception = open_incident_exception(
            session, requirement, "SUPPLIER_DROPOUT", f"dropout:{allocation.id}", allocation.quantity_kg,
            f"Supplier dropout: {allocation.quantity_kg} kg of committed supply lost",
            {"allocation_id": str(allocation.id), "reason": reason})
        result = {"requirement_id": str(requirement.id), "lost_kg": str(allocation.quantity_kg),
                  "committed_kg": str(_coverage(session, requirement.id)),
                  "supply_health": requirement.supply_health.value,
                  "recovery_status": run.status.value, "standby_activated_kg": "0",
                  "remaining_shortfall_kg": str(run.remaining_shortfall_kg),
                  "exception_id": str(exception.id),
                  "next_step": "the recovery agent will propose options for approval; nothing is activated automatically"}
        session.add(CommandDeduplication(command_type="allocation.dropout", idempotency_key=key, result=result))
        return result


def _free_eligible_kg(session: Session, requirement: Requirement) -> Decimal:
    """Unreserved, eligible stock in the requirement's own organization."""
    return session.scalar(select(func.coalesce(func.sum(
        free_kg_sql()
    ), 0)).where(
        ProductionLot.farmer_id.in_(farmers_in_requirement_organization(requirement.buyer_id)),
        ProductionLot.crop == requirement.crop,
        ProductionLot.quality_grade_estimate == requirement.grade,
        ProductionLot.status == ProductionLotStatus.AVAILABLE,
        ProductionLot.harvest_start <= requirement.delivery_window_end,
        ProductionLot.harvest_end >= requirement.delivery_window_start,
        has_free_stock_sql(),
    )) or Decimal("0")


def _pending_kg(session: Session, requirement: Requirement) -> Decimal:
    return session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
        SupplyAllocation.requirement_id == requirement.id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status.in_([AllocationStatus.PROPOSED, AllocationStatus.SOLICITED]),
    )) or Decimal("0")


def _active_run(session: Session, requirement: Requirement) -> RecoveryRun | None:
    return session.scalar(select(RecoveryRun).where(
        RecoveryRun.requirement_id == requirement.id,
        RecoveryRun.status.in_([RecoveryStatus.RUNNING, RecoveryStatus.ESCALATED]),
    ).order_by(RecoveryRun.created_at.desc()).with_for_update())


def apply_accepted_commitment(session: Session, requirement: Requirement, allocation: SupplyAllocation,
                              correlation: UUID, actor=None) -> None:
    """Coverage and recovery bookkeeping after a supplier's recorded acceptance (supply/application/commitments.py)."""
    run = _active_run(session, requirement)
    covered = _coverage(session, requirement.id)
    if run:
        run.new_supply_accepted_kg += allocation.quantity_kg
        run.remaining_shortfall_kg = max(requirement.required_quantity_kg - covered, Decimal("0"))
    if covered >= requirement.required_quantity_kg:
        if run:
            _create_recovery_snapshot(session, requirement)
            run.status = RecoveryStatus.COMPLETED; run.active_key = None; run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.completed", requirement.id, correlation, {"new_supply_accepted_kg": str(allocation.quantity_kg)})
        else:
            _event(session, "requirement.covered", requirement.id, correlation, {"committed_kg": str(covered)})
        requirement.supply_health = SupplyHealth.COVERED
        if requirement.lifecycle_status == RequirementLifecycleStatus.PLANNING:
            requirement.lifecycle_status = RequirementLifecycleStatus.ACTIVE
    elif run and _pending_kg(session, requirement) <= 0 and _free_eligible_kg(session, requirement) <= 0:
        _escalate(session, requirement, run, correlation)
    elif not run:
        _mark_unresolved_shortfall(session, requirement, covered, correlation)
    if not run:
        settle_initial_plan(session, requirement)


def settle_initial_plan(session: Session, requirement: Requirement) -> None:
    """Once no allocation of the current plan awaits a supplier, freeze its risk snapshot (once)."""
    from src.backend.app.risk.domain.models import RiskSnapshot
    open_count = session.scalar(select(func.count(SupplyAllocation.id)).where(
        SupplyAllocation.requirement_id == requirement.id,
        SupplyAllocation.status.in_([AllocationStatus.PROPOSED, AllocationStatus.SOLICITED]),
    )) or 0
    if open_count:
        return
    plan = session.scalar(select(SupplyPlan).where(SupplyPlan.requirement_id == requirement.id)
                          .order_by(SupplyPlan.plan_version.desc()))
    if plan is None or session.scalar(select(RiskSnapshot.id).where(RiskSnapshot.supply_plan_id == plan.id)) is not None:
        return
    session.flush()
    create_risk_snapshot(session, requirement, plan)


def _mark_unresolved_shortfall(session: Session, requirement: Requirement, covered: Decimal, correlation: UUID) -> None:
    """Outside recovery: once no supplier request is outstanding, an uncovered order is at risk."""
    if covered < requirement.required_quantity_kg and _pending_kg(session, requirement) <= 0             and requirement.supply_health != SupplyHealth.AT_RISK:
        requirement.supply_health = SupplyHealth.AT_RISK
        _event(session, "requirement.at_risk", requirement.id, correlation,
               {"shortfall_kg": str(requirement.required_quantity_kg - covered), "cause": "supplier responses left a shortfall"})


def refresh_after_decline(session: Session, requirement: Requirement, correlation: UUID, actor=None) -> None:
    """A decline during recovery escalates when nothing is pending and no eligible stock remains."""
    run = _active_run(session, requirement)
    if run and run.status == RecoveryStatus.RUNNING and _pending_kg(session, requirement) <= 0             and _free_eligible_kg(session, requirement) <= 0:
        _escalate(session, requirement, run, correlation)
    elif not run:
        _mark_unresolved_shortfall(session, requirement, _coverage(session, requirement.id), correlation)
    if not run:
        settle_initial_plan(session, requirement)


def _escalate(session: Session, requirement: Requirement, run: RecoveryRun, correlation: UUID) -> None:
    run.status = RecoveryStatus.ESCALATED
    run.active_key = None
    run.completed_at = datetime.now(timezone.utc)
    requirement.supply_health = SupplyHealth.ESCALATION_REQUIRED
    _event(session, "recovery.escalated", requirement.id, correlation, {"remaining_shortfall_kg": str(run.remaining_shortfall_kg)})


def record_quality_shortfall(session: Session, requirement_id: UUID, sublot_id: UUID, shortfall: Decimal,
                             cause: str) -> dict:
    """Record produce rejected at the fulfilment node as an actionable recovery incident.

    Grading never waits for recovery: the rejection, the order's at-risk state, the recovery run and a
    QUALITY_REJECTION exception are written with the grade. The rejected sublot stays traceable to its original
    commitment. Replacement supply is only proposed by the recovery agent and needs approval (R1 WP3, decision 1).
    """
    from src.backend.app.assurance.application.exceptions import open_incident_exception
    if shortfall <= 0:
        return {"status": "NOT_REQUIRED", "standby_activated_kg": "0", "remaining_shortfall_kg": "0"}
    with session.begin_nested() if session.in_transaction() else session.begin():
        requirement = session.scalar(select(Requirement).where(Requirement.id == requirement_id).with_for_update())
        if requirement is None:
            raise ValueError("requirement not found")
        correlation = uuid4()
        requirement.supply_health = SupplyHealth.AT_RISK
        _event(session, "requirement.at_risk", requirement.id, correlation,
               {"shortfall_kg": str(shortfall), "cause": cause})
        run = _open_recovery_run(session, requirement, shortfall, cause)
        _event(session, "recovery.started", requirement.id, correlation,
               {"recovery_run_id": str(run.id), "cause": cause})
        exception = open_incident_exception(
            session, requirement, "QUALITY_REJECTION", f"quality:{sublot_id}", shortfall,
            f"Quality rejection: {shortfall} kg rejected at grading",
            {"received_sublot_id": str(sublot_id), "cause": cause})
        return {"recovery_run_id": str(run.id), "status": run.status.value, "standby_activated_kg": "0",
                "remaining_shortfall_kg": str(run.remaining_shortfall_kg), "exception_id": str(exception.id),
                "next_step": "the recovery agent will propose replacement supply for approval"}
