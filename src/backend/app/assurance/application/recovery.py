from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage, RecoveryRun, RecoveryStatus
from src.backend.app.demand.domain.models import Requirement, SupplyHealth
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation
from src.backend.app.supply.domain.planning_models import SupplyPlan, SupplyPlanStatus
from src.backend.app.economics.domain.calculator import CostBreakdown, allocation_cost, money
from src.backend.app.economics.domain.models import CostSnapshot, LotCostInput
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.risk.application.calculator import create_risk_snapshot


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
    )).all()
    return sum((allocation.quantity_kg for allocation in allocations), Decimal("0"))


def _coverage(session: Session, requirement_id: UUID) -> Decimal:
    """Assured Grade-A coverage used by recovery, kept separate from commitment truth."""
    allocations = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == requirement_id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
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
    )))
    version = requirement.plan_version + 1
    committed = _coverage(session, requirement.id)
    standby = session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
        SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.STANDBY,
        SupplyAllocation.status == AllocationStatus.STANDBY,
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


def dropout(session: Session, allocation_id: UUID, reason: str, key: str, auto_recover: bool = True) -> dict:
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
        run = RecoveryRun(requirement_id=requirement.id, status=RecoveryStatus.RUNNING, active_key="RUNNING", lost_quantity_kg=allocation.quantity_kg, cause=reason, remaining_shortfall_kg=max(shortfall, Decimal("0")))
        session.add(run); session.flush(); _event(session, "recovery.started", requirement.id, correlation, {"recovery_run_id": str(run.id)})
        if not auto_recover:
            result = {"requirement_id": str(requirement.id), "lost_kg": str(allocation.quantity_kg),
                      "committed_kg": str(_coverage(session, requirement.id)),
                      "supply_health": requirement.supply_health.value,
                      "recovery_status": run.status.value, "standby_activated_kg": "0",
                      "remaining_shortfall_kg": str(run.remaining_shortfall_kg)}
            session.add(CommandDeduplication(command_type="allocation.dropout", idempotency_key=key, result=result))
            return result
        # Activate only the exact required amount from pre-authorized standby reservations.
        for standby in session.scalars(select(SupplyAllocation).join(ProductionLot).where(
            SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.STANDBY,
            SupplyAllocation.status == AllocationStatus.STANDBY).order_by(ProductionLot.parish, ProductionLot.harvest_start,
            ProductionLot.expected_quantity_kg, ProductionLot.id, SupplyAllocation.created_at).with_for_update()):
            if shortfall <= 0: break
            activated = min(shortfall, standby.quantity_kg)
            if activated == standby.quantity_kg:
                standby.status = AllocationStatus.ACTIVATED
            else:
                standby.quantity_kg -= activated
            session.add(SupplyAllocation(requirement_id=requirement.id, supply_plan_id=standby.supply_plan_id, production_lot_id=standby.production_lot_id, role=AllocationRole.COMMITTED, status=AllocationStatus.COMMITTED, quantity_kg=activated, consent_evidence_id=standby.consent_evidence_id, plan_version=standby.plan_version))
            run.standby_activated_kg += activated; shortfall -= activated
            _event(session, "allocation.standby_activated", requirement.id, correlation, {"source_allocation_id": str(standby.id), "quantity_kg": str(activated)})
        run.remaining_shortfall_kg = max(shortfall, Decimal("0"))
        if shortfall <= 0:
            _create_recovery_snapshot(session, requirement)
            requirement.supply_health = SupplyHealth.COVERED; run.status = RecoveryStatus.COMPLETED; run.active_key = None; run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.completed", requirement.id, correlation, {"standby_activated_kg": str(run.standby_activated_kg)})
        else:
            # Solicitation reserves eligible free stock but deliberately does not improve coverage.
            # A farmer must explicitly accept it through `accept` before it becomes committed.
            solicitation_needed = shortfall
            for lot in session.scalars(select(ProductionLot).where(
                ProductionLot.crop == requirement.crop,
                ProductionLot.quality_grade_estimate == requirement.grade,
                ProductionLot.status == ProductionLotStatus.AVAILABLE,
                ProductionLot.harvest_start <= requirement.delivery_window_end,
                ProductionLot.harvest_end >= requirement.delivery_window_start,
                ProductionLot.available_quantity_kg > ProductionLot.reserved_quantity_kg,
            ).order_by(ProductionLot.id).with_for_update()):
                if solicitation_needed <= 0:
                    break
                quantity = min(solicitation_needed, lot.available_quantity_kg - lot.reserved_quantity_kg)
                lot.reserved_quantity_kg += quantity
                session.add(SupplyAllocation(requirement_id=requirement.id, supply_plan_id=allocation.supply_plan_id,
                    production_lot_id=lot.id, role=AllocationRole.COMMITTED, status=AllocationStatus.SOLICITED,
                    quantity_kg=quantity, plan_version=requirement.plan_version))
                _event(session, "allocation.solicited", requirement.id, correlation,
                       {"production_lot_id": str(lot.id), "quantity_kg": str(quantity)})
                solicitation_needed -= quantity
            requirement.supply_health = SupplyHealth.RECOVERING if solicitation_needed <= 0 else SupplyHealth.ESCALATION_REQUIRED
            run.status = RecoveryStatus.RUNNING if solicitation_needed <= 0 else RecoveryStatus.ESCALATED
            run.active_key = "RUNNING" if solicitation_needed <= 0 else None
            if run.status == RecoveryStatus.ESCALATED:
                run.completed_at = datetime.now(timezone.utc)
            _event(
                session,
                "recovery.awaiting_acceptance" if run.status == RecoveryStatus.RUNNING else "recovery.escalated",
                requirement.id,
                correlation,
                {"remaining_shortfall_kg": str(max(shortfall, Decimal("0")))},
            )
        result = {"requirement_id": str(requirement.id), "lost_kg": str(allocation.quantity_kg), "committed_kg": str(_coverage(session, requirement.id)), "supply_health": requirement.supply_health.value, "recovery_status": run.status.value, "standby_activated_kg": str(run.standby_activated_kg), "remaining_shortfall_kg": str(run.remaining_shortfall_kg)}
        session.add(CommandDeduplication(command_type="allocation.dropout", idempotency_key=key, result=result))
        return result


def continue_recovery(session: Session, requirement_id: UUID, key: str) -> dict:
    """Advance a persisted recovery run under PostgreSQL row locks."""
    existing = session.scalar(select(CommandDeduplication).where(
        CommandDeduplication.command_type == "requirement.recovery",
        CommandDeduplication.idempotency_key == key,
    ))
    if existing:
        return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        requirement = session.scalar(select(Requirement).where(Requirement.id == requirement_id).with_for_update())
        if requirement is None:
            raise ValueError("requirement not found")
        run = session.scalar(select(RecoveryRun).where(
            RecoveryRun.requirement_id == requirement_id,
            RecoveryRun.status == RecoveryStatus.RUNNING,
        ).order_by(RecoveryRun.created_at.desc()).with_for_update())
        existing = session.scalar(select(CommandDeduplication).where(
            CommandDeduplication.command_type == "requirement.recovery",
            CommandDeduplication.idempotency_key == key,
        ))
        if existing:
            return existing.result
        if run is None:
            raise ValueError("no recovery is pending")
        correlation = uuid4()
        shortfall = max(requirement.required_quantity_kg - _coverage(session, requirement.id), Decimal("0"))
        for standby in session.scalars(select(SupplyAllocation).join(ProductionLot).where(
            SupplyAllocation.requirement_id == requirement.id,
            SupplyAllocation.role == AllocationRole.STANDBY,
            SupplyAllocation.status == AllocationStatus.STANDBY,
        ).order_by(ProductionLot.parish, ProductionLot.harvest_start,
                   ProductionLot.expected_quantity_kg, ProductionLot.id, SupplyAllocation.created_at).with_for_update()):
            if shortfall <= 0:
                break
            activated = min(shortfall, standby.quantity_kg)
            if activated == standby.quantity_kg:
                standby.status = AllocationStatus.ACTIVATED
            else:
                standby.quantity_kg -= activated
            session.add(SupplyAllocation(
                requirement_id=requirement.id, supply_plan_id=standby.supply_plan_id,
                production_lot_id=standby.production_lot_id, role=AllocationRole.COMMITTED,
                status=AllocationStatus.COMMITTED, quantity_kg=activated,
                consent_evidence_id=standby.consent_evidence_id, plan_version=standby.plan_version,
            ))
            run.standby_activated_kg += activated
            shortfall -= activated
            _event(session, "allocation.standby_activated", requirement.id, correlation,
                   {"source_allocation_id": str(standby.id), "quantity_kg": str(activated)})
        run.remaining_shortfall_kg = max(shortfall, Decimal("0"))
        if shortfall <= 0:
            _create_recovery_snapshot(session, requirement)
            requirement.supply_health = SupplyHealth.COVERED
            run.status = RecoveryStatus.COMPLETED
            run.active_key = None
            run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.completed", requirement.id, correlation,
                   {"standby_activated_kg": str(run.standby_activated_kg)})
        else:
            source_plan = session.scalar(select(SupplyPlan).where(
                SupplyPlan.requirement_id == requirement.id
            ).order_by(SupplyPlan.plan_version.desc()))
            remaining_to_solicit = shortfall
            for lot in session.scalars(select(ProductionLot).where(
                ProductionLot.crop == requirement.crop,
                ProductionLot.quality_grade_estimate == requirement.grade,
                ProductionLot.status == ProductionLotStatus.AVAILABLE,
                ProductionLot.harvest_start <= requirement.delivery_window_end,
                ProductionLot.harvest_end >= requirement.delivery_window_start,
                ProductionLot.available_quantity_kg > ProductionLot.reserved_quantity_kg,
            ).order_by(ProductionLot.id).with_for_update()):
                if remaining_to_solicit <= 0:
                    break
                quantity = min(remaining_to_solicit, lot.available_quantity_kg - lot.reserved_quantity_kg)
                lot.reserved_quantity_kg += quantity
                session.add(SupplyAllocation(
                    requirement_id=requirement.id, supply_plan_id=source_plan.id,
                    production_lot_id=lot.id, role=AllocationRole.COMMITTED,
                    status=AllocationStatus.SOLICITED, quantity_kg=quantity,
                    plan_version=requirement.plan_version,
                ))
                _event(session, "allocation.solicited", requirement.id, correlation,
                       {"production_lot_id": str(lot.id), "quantity_kg": str(quantity)})
                remaining_to_solicit -= quantity
            if remaining_to_solicit <= 0:
                requirement.supply_health = SupplyHealth.RECOVERING
                _event(session, "recovery.awaiting_acceptance", requirement.id, correlation,
                       {"remaining_shortfall_kg": str(shortfall)})
            else:
                requirement.supply_health = SupplyHealth.ESCALATION_REQUIRED
                run.status = RecoveryStatus.ESCALATED
                run.active_key = None
                run.completed_at = datetime.now(timezone.utc)
                _event(session, "recovery.escalated", requirement.id, correlation,
                       {"remaining_shortfall_kg": str(shortfall)})
        result = {"recovery_run_id": str(run.id), "status": run.status.value,
                  "committed_kg": str(_coverage(session, requirement.id)),
                  "supply_health": requirement.supply_health.value,
                  "standby_activated_kg": str(run.standby_activated_kg),
                  "remaining_shortfall_kg": str(run.remaining_shortfall_kg)}
        session.add(CommandDeduplication(command_type="requirement.recovery", idempotency_key=key, result=result))
        return result


def decline(session: Session, allocation_id: UUID, key: str) -> dict:
    """Record a replacement farmer decline and release the previously solicited reservation."""
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.decline", CommandDeduplication.idempotency_key == key))
    if existing:
        return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update())
        existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.decline", CommandDeduplication.idempotency_key == key))
        if existing: return existing.result
        if allocation is None or allocation.status != AllocationStatus.SOLICITED:
            raise ValueError("allocation is not awaiting a farmer response")
        lot = session.scalar(select(ProductionLot).where(ProductionLot.id == allocation.production_lot_id).with_for_update())
        requirement = session.scalar(select(Requirement).where(Requirement.id == allocation.requirement_id).with_for_update())
        allocation.status = AllocationStatus.RELEASED
        lot.reserved_quantity_kg -= allocation.quantity_kg
        correlation = uuid4()
        _event(session, "allocation.declined", requirement.id, correlation, {"allocation_id": str(allocation.id)})
        result = {"allocation_id": str(allocation.id), "status": allocation.status.value,
                  "committed_kg": str(_coverage(session, requirement.id))}
        session.add(CommandDeduplication(command_type="allocation.decline", idempotency_key=key, result=result))
        return result


def accept(session: Session, allocation_id: UUID, key: str) -> dict:
    """A farmer's explicit response is the only path from solicitation to commitment."""
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.accept", CommandDeduplication.idempotency_key == key))
    if existing:
        return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update())
        existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "allocation.accept", CommandDeduplication.idempotency_key == key))
        if existing: return existing.result
        if allocation is None or allocation.status != AllocationStatus.SOLICITED:
            raise ValueError("allocation is not awaiting acceptance")
        requirement = session.scalar(select(Requirement).where(Requirement.id == allocation.requirement_id).with_for_update())
        allocation.status = AllocationStatus.COMMITTED
        allocation.role = AllocationRole.COMMITTED
        # Coverage is calculated with SQL below.  Flush explicitly because API
        # and test sessions may deliberately disable SQLAlchemy autoflush.
        session.flush()
        correlation = uuid4()
        _event(session, "allocation.accepted", requirement.id, correlation, {"allocation_id": str(allocation.id), "quantity_kg": str(allocation.quantity_kg)})
        run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id, RecoveryRun.status.in_([RecoveryStatus.RUNNING, RecoveryStatus.ESCALATED])).order_by(RecoveryRun.created_at.desc()).with_for_update())
        covered = _coverage(session, requirement.id)
        if run:
            run.new_supply_accepted_kg += allocation.quantity_kg
            run.remaining_shortfall_kg = max(requirement.required_quantity_kg - covered, Decimal("0"))
        if covered >= requirement.required_quantity_kg:
            _create_recovery_snapshot(session, requirement)
            requirement.supply_health = SupplyHealth.COVERED
            if run:
                run.status = RecoveryStatus.COMPLETED; run.active_key = None; run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.completed", requirement.id, correlation, {"new_supply_accepted_kg": str(allocation.quantity_kg)})
        elif run:
            pending = session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
                SupplyAllocation.requirement_id == requirement.id,
                SupplyAllocation.status == AllocationStatus.SOLICITED,
            )) or Decimal("0")
            free = session.scalar(select(func.coalesce(func.sum(
                ProductionLot.available_quantity_kg - ProductionLot.reserved_quantity_kg
            ), 0)).where(
                ProductionLot.crop == requirement.crop,
                ProductionLot.quality_grade_estimate == requirement.grade,
                ProductionLot.status == ProductionLotStatus.AVAILABLE,
                ProductionLot.harvest_start <= requirement.delivery_window_end,
                ProductionLot.harvest_end >= requirement.delivery_window_start,
                ProductionLot.available_quantity_kg > ProductionLot.reserved_quantity_kg,
            )) or Decimal("0")
            if pending <= 0 and free <= 0:
                run.status = RecoveryStatus.ESCALATED
                run.active_key = None
                run.completed_at = datetime.now(timezone.utc)
                requirement.supply_health = SupplyHealth.ESCALATION_REQUIRED
                _event(session, "recovery.escalated", requirement.id, correlation,
                       {"remaining_shortfall_kg": str(run.remaining_shortfall_kg)})
        result = {"allocation_id": str(allocation.id), "committed_kg": str(covered), "supply_health": requirement.supply_health.value}
        session.add(CommandDeduplication(command_type="allocation.accept", idempotency_key=key, result=result))
        return result


def recover_quality_shortfall(session: Session, requirement_id: UUID, shortfall: Decimal, cause: str) -> dict:
    """Start a recovery run for produce rejected at the fulfilment node.

    A quality result is a physical exception, not a farmer dropout.  The
    rejected sublot stays traceable to its original commitment; this function
    only reserves and activates replacement capacity for the accepted-quantity
    gap.  It deliberately never turns a solicitation into coverage.
    """
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
        run = RecoveryRun(requirement_id=requirement.id, status=RecoveryStatus.RUNNING, active_key="RUNNING",
                          lost_quantity_kg=shortfall, cause=cause, remaining_shortfall_kg=shortfall)
        session.add(run)
        session.flush()
        _event(session, "recovery.started", requirement.id, correlation,
               {"recovery_run_id": str(run.id), "cause": cause})

        remaining = shortfall
        for standby in session.scalars(select(SupplyAllocation).join(ProductionLot).where(
            SupplyAllocation.requirement_id == requirement.id,
            SupplyAllocation.role == AllocationRole.STANDBY,
            SupplyAllocation.status == AllocationStatus.STANDBY,
        ).order_by(ProductionLot.parish, ProductionLot.harvest_start, ProductionLot.expected_quantity_kg, ProductionLot.id,
                   SupplyAllocation.created_at).with_for_update()):
            if remaining <= 0:
                break
            activated = min(remaining, standby.quantity_kg)
            if activated == standby.quantity_kg:
                standby.status = AllocationStatus.ACTIVATED
            else:
                standby.quantity_kg -= activated
            session.add(SupplyAllocation(requirement_id=requirement.id, supply_plan_id=standby.supply_plan_id,
                production_lot_id=standby.production_lot_id, role=AllocationRole.COMMITTED,
                status=AllocationStatus.COMMITTED, quantity_kg=activated,
                consent_evidence_id=standby.consent_evidence_id, plan_version=standby.plan_version))
            run.standby_activated_kg += activated
            remaining -= activated
            _event(session, "allocation.standby_activated", requirement.id, correlation,
                   {"source_allocation_id": str(standby.id), "quantity_kg": str(activated), "cause": cause})

        run.remaining_shortfall_kg = max(remaining, Decimal("0"))
        if remaining <= 0:
            _create_recovery_snapshot(session, requirement)
            requirement.supply_health = SupplyHealth.COVERED
            run.status = RecoveryStatus.COMPLETED
            run.active_key = None
            run.completed_at = datetime.now(timezone.utc)
            _event(session, "recovery.completed", requirement.id, correlation,
                   {"standby_activated_kg": str(run.standby_activated_kg), "cause": cause})
        else:
            source_plan = session.scalar(select(SupplyPlan).where(
                SupplyPlan.requirement_id == requirement.id
            ).order_by(SupplyPlan.plan_version.desc()))
            if source_plan is None:
                raise ValueError("requirement has no supply plan")
            for lot in session.scalars(select(ProductionLot).where(
                ProductionLot.crop == requirement.crop,
                ProductionLot.quality_grade_estimate == requirement.grade,
                ProductionLot.status == ProductionLotStatus.AVAILABLE,
                ProductionLot.harvest_start <= requirement.delivery_window_end,
                ProductionLot.harvest_end >= requirement.delivery_window_start,
                ProductionLot.available_quantity_kg > ProductionLot.reserved_quantity_kg,
            ).order_by(ProductionLot.id).with_for_update()):
                if remaining <= 0:
                    break
                quantity = min(remaining, lot.available_quantity_kg - lot.reserved_quantity_kg)
                lot.reserved_quantity_kg += quantity
                session.add(SupplyAllocation(requirement_id=requirement.id, supply_plan_id=source_plan.id,
                    production_lot_id=lot.id, role=AllocationRole.COMMITTED, status=AllocationStatus.SOLICITED,
                    quantity_kg=quantity, plan_version=requirement.plan_version))
                _event(session, "allocation.solicited", requirement.id, correlation,
                       {"production_lot_id": str(lot.id), "quantity_kg": str(quantity), "cause": cause})
                remaining -= quantity
            if remaining <= 0:
                run.status = RecoveryStatus.RUNNING
                requirement.supply_health = SupplyHealth.RECOVERING
                _event(session, "recovery.awaiting_acceptance", requirement.id, correlation,
                       {"remaining_shortfall_kg": str(run.remaining_shortfall_kg), "cause": cause})
            else:
                run.status = RecoveryStatus.ESCALATED
                run.active_key = None
                run.completed_at = datetime.now(timezone.utc)
                requirement.supply_health = SupplyHealth.ESCALATION_REQUIRED
                _event(session, "recovery.escalated", requirement.id, correlation,
                       {"remaining_shortfall_kg": str(run.remaining_shortfall_kg), "cause": cause})
        return {"recovery_run_id": str(run.id), "status": run.status.value,
                "standby_activated_kg": str(run.standby_activated_kg),
                "remaining_shortfall_kg": str(run.remaining_shortfall_kg)}
