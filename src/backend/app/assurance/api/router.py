from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.app.assurance.application import PlanAlreadyExistsError, PlannerConfig, RequirementNotFoundError, finalize_plan
from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.economics.domain.models import CostSnapshot
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation, SupplyPlan
from src.backend.app.assurance.domain.models import CommandDeduplication, RecoveryRun
from src.backend.app.risk.domain.models import RiskSnapshot
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.assurance.application.recovery import _coverage, committed_quantity
from src.backend.app.assurance.application.recovery import continue_recovery
from src.backend.app.assurance.domain.models import DomainEvent

router = APIRouter(prefix="/requirements", tags=["assurance"])


@router.post("/{requirement_id}/recovery")
def run_recovery(requirement_id: UUID, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                 session: Session = Depends(get_session)) -> dict:
    """Advance the single persisted recovery run."""
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        result = continue_recovery(session, requirement_id, idempotency_key)
        session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class PlanRead(BaseModel):
    id: UUID
    requirement_id: UUID
    plan_version: int
    planner_version: str
    required_quantity_kg: Decimal
    committed_quantity_kg: Decimal
    standby_quantity_kg: Decimal
    unfilled_quantity_kg: Decimal
    supply_health: SupplyHealth
    total_landed_cost_jmd: Decimal
    landed_cost_per_kg_jmd: Decimal


class AllocationRead(BaseModel):
    id: UUID
    production_lot_id: UUID
    farmer_id: UUID
    farmer_name: str
    parish: str
    role: AllocationRole
    status: AllocationStatus
    quantity_kg: Decimal
    created_at: datetime


class RequirementSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    crop: str
    grade: str
    required_quantity_kg: Decimal
    lifecycle_status: RequirementLifecycleStatus
    supply_health: SupplyHealth
    plan_version: int
    buyer_name: str
    buyer_type: str
    destination: str
    delivery_window_start: str
    delivery_window_end: str


class AssuranceRead(BaseModel):
    requirement: RequirementSummary
    supply_health: SupplyHealth
    committed_quantity_kg: Decimal
    assured_coverage_quantity_kg: Decimal
    standby_quantity_kg: Decimal
    unfilled_quantity_kg: Decimal
    committed_farmer_count: int
    standby_farmer_count: int
    parish_concentration: dict[str, Decimal]
    total_landed_cost_jmd: Decimal | None
    landed_cost_per_kg_jmd: Decimal | None
    allocations: list[AllocationRead]
    latest_disruption: dict | None = None
    latest_recovery: dict | None = None
    economics: dict | None = None
    risk: dict | None = None


def _risk_response(snapshot: RiskSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {"label": snapshot.risk_label.value, "committed_farmer_count": snapshot.committed_farmer_count,
            "standby_farmer_count": snapshot.standby_farmer_count, "committed_parish_count": snapshot.committed_parish_count,
            "standby_parish_count": snapshot.standby_parish_count, "largest_farmer_share_pct": snapshot.largest_farmer_share_pct,
            "largest_parish_share_pct": snapshot.largest_parish_share_pct, "standby_coverage_pct": snapshot.standby_coverage_pct,
            "replacement_depth_kg": snapshot.replacement_depth_kg, "average_availability_confidence": snapshot.average_availability_confidence,
            "rules_triggered": snapshot.rules_triggered, "calculation_version": snapshot.calculation_version}


def _plan_response(result) -> PlanRead:
    return PlanRead(
        id=result.plan_id, requirement_id=result.requirement_id, plan_version=1, planner_version="deterministic-greedy-v1",
        required_quantity_kg=result.required_quantity_kg, committed_quantity_kg=result.committed_quantity_kg,
        standby_quantity_kg=result.standby_quantity_kg, unfilled_quantity_kg=result.unfilled_quantity_kg,
        supply_health=result.supply_health, total_landed_cost_jmd=result.total_landed_cost_jmd,
        landed_cost_per_kg_jmd=result.landed_cost_per_kg_jmd,
    )


@router.post("/{requirement_id}/plan", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(requirement_id: UUID,
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                session: Session = Depends(get_session)) -> PlanRead:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    existing = session.scalar(select(CommandDeduplication).where(
        CommandDeduplication.command_type == "requirement.plan",
        CommandDeduplication.idempotency_key == idempotency_key,
    ))
    if existing:
        return PlanRead.model_validate(existing.result)
    try:
        response = _plan_response(finalize_plan(session, requirement_id, PlannerConfig()))
        session.add(CommandDeduplication(command_type="requirement.plan", idempotency_key=idempotency_key,
                                         result=response.model_dump(mode="json")))
        session.commit()
        return response
    except RequirementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        # PostgreSQL row locking normally turns this into PlanAlreadyExistsError;
        # the unique plan-version constraint is the final race-condition backstop.
        raise HTTPException(status_code=409, detail="concurrent plan creation conflict") from exc


@router.get("/{requirement_id}/assurance", response_model=AssuranceRead)
def get_assurance(requirement_id: UUID, session: Session = Depends(get_session)) -> AssuranceRead:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    buyer = session.get(Buyer, requirement.buyer_id)
    requirement_summary = RequirementSummary(
        id=requirement.id, crop=requirement.crop.value, grade=requirement.grade.value,
        required_quantity_kg=requirement.required_quantity_kg,
        lifecycle_status=requirement.lifecycle_status, supply_health=requirement.supply_health,
        plan_version=requirement.plan_version, buyer_name=buyer.name, buyer_type=buyer.buyer_type,
        destination=buyer.destination, delivery_window_start=str(requirement.delivery_window_start),
        delivery_window_end=str(requirement.delivery_window_end),
    )
    plan = session.scalar(
        select(SupplyPlan).where(SupplyPlan.requirement_id == requirement.id).order_by(SupplyPlan.plan_version.desc())
    )
    if plan is None:
        return AssuranceRead(
            requirement=requirement_summary, supply_health=requirement.supply_health, committed_quantity_kg=Decimal("0"), standby_quantity_kg=Decimal("0"),
            assured_coverage_quantity_kg=Decimal("0"),
            unfilled_quantity_kg=requirement.required_quantity_kg, committed_farmer_count=0, standby_farmer_count=0,
            parish_concentration={}, total_landed_cost_jmd=None, landed_cost_per_kg_jmd=None, allocations=[],
        )
    risk = session.scalar(select(RiskSnapshot).where(RiskSnapshot.supply_plan_id == plan.id))
    rows = session.execute(
        select(SupplyAllocation, ProductionLot, Farmer)
        .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .where(SupplyAllocation.requirement_id == requirement.id)
        .order_by(SupplyAllocation.created_at, SupplyAllocation.id)
    ).all()
    allocations = [
        AllocationRead(id=allocation.id, production_lot_id=lot.id, farmer_id=farmer.id, farmer_name=farmer.name,
                       parish=lot.parish, role=allocation.role, status=allocation.status,
                       quantity_kg=allocation.quantity_kg, created_at=allocation.created_at)
        for allocation, lot, farmer in rows
    ]
    committed_rows = [(allocation, lot, farmer) for allocation, lot, farmer in rows if allocation.role == AllocationRole.COMMITTED and allocation.status == AllocationStatus.COMMITTED]
    parish_quantities: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for allocation, lot, _ in committed_rows:
        parish_quantities[lot.parish] += allocation.quantity_kg
    rejected_by_allocation = {
        allocation_id: rejected for allocation_id, rejected in session.execute(
            select(ReceivedSublot.allocation_id, func.coalesce(func.sum(ReceivedSublot.rejected_quantity_kg), 0))
            .group_by(ReceivedSublot.allocation_id)
        )
    }
    committed_kg = committed_quantity(session, requirement.id)
    assured_kg = _coverage(session, requirement.id)
    standby_kg = sum((a.quantity_kg for a, _, _ in rows if a.role == AllocationRole.STANDBY and a.status == AllocationStatus.STANDBY), Decimal("0"))
    concentration = {parish: quantity / committed_kg for parish, quantity in parish_quantities.items()} if committed_kg else {}
    initial_plan = session.scalar(select(SupplyPlan).where(SupplyPlan.requirement_id == requirement.id).order_by(SupplyPlan.plan_version))
    original_cost = session.scalar(select(CostSnapshot).where(CostSnapshot.supply_plan_id == initial_plan.id)) if initial_plan else None
    cost = session.scalar(select(CostSnapshot).join(SupplyPlan).where(SupplyPlan.requirement_id == requirement.id).order_by(SupplyPlan.plan_version.desc()))
    run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id).order_by(RecoveryRun.created_at.desc()))
    economics = None
    if original_cost and cost:
        economics = {"original_landed_cost_jmd": str(original_cost.total_landed_cost_jmd), "recovered_landed_cost_jmd": str(cost.total_landed_cost_jmd),
                     "recovery_premium_jmd": str(cost.total_landed_cost_jmd - original_cost.total_landed_cost_jmd),
                     "recovery_premium_per_kg_jmd": str((cost.total_landed_cost_jmd - original_cost.total_landed_cost_jmd) / requirement.required_quantity_kg),
                     "recovery_premium_pct": str(((cost.total_landed_cost_jmd - original_cost.total_landed_cost_jmd) * Decimal("100") / original_cost.total_landed_cost_jmd) if original_cost.total_landed_cost_jmd else Decimal("0"))}
    return AssuranceRead(
        requirement=requirement_summary, supply_health=requirement.supply_health, committed_quantity_kg=committed_kg,
        assured_coverage_quantity_kg=assured_kg, standby_quantity_kg=standby_kg,
        unfilled_quantity_kg=max(requirement.required_quantity_kg - assured_kg, Decimal("0")),
        committed_farmer_count=len({farmer.id for _, _, farmer in committed_rows}),
        standby_farmer_count=len({farmer.id for allocation, _, farmer in rows if allocation.role == AllocationRole.STANDBY}),
        parish_concentration=concentration, total_landed_cost_jmd=cost.total_landed_cost_jmd if cost else None,
        landed_cost_per_kg_jmd=cost.landed_cost_per_kg_jmd if cost else None, allocations=allocations,
        latest_disruption={"lost_kg": str(run.lost_quantity_kg), "cause": run.cause} if run else None,
        latest_recovery={"status": run.status.value.lower(), "standby_activated_kg": str(run.standby_activated_kg), "new_supply_accepted_kg": str(run.new_supply_accepted_kg), "remaining_shortfall_kg": str(run.remaining_shortfall_kg)} if run else None,
        economics=economics,
        risk=_risk_response(risk),
    )


@router.get("/{requirement_id}/risk")
def get_risk(requirement_id: UUID, session: Session = Depends(get_session)) -> dict:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    snapshot = session.scalar(select(RiskSnapshot).where(RiskSnapshot.requirement_id == requirement_id).order_by(RiskSnapshot.plan_version.desc()))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="no supply-plan risk snapshot exists")
    return _risk_response(snapshot)


@router.get("/{requirement_id}/events")
def get_events(requirement_id: UUID, session: Session = Depends(get_session)) -> list[dict]:
    if session.get(Requirement, requirement_id) is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    events = session.scalars(select(DomainEvent).where(
        DomainEvent.aggregate_id == requirement_id
    ).order_by(DomainEvent.occurred_at, DomainEvent.id)).all()
    return [{
        "id": str(event.id), "event_type": event.event_type,
        "actor_type": event.actor_type, "payload": event.payload,
        "occurred_at": event.occurred_at,
    } for event in events]
