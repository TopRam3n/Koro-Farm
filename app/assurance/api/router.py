from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assurance.application import PlanAlreadyExistsError, PlannerConfig, RequirementNotFoundError, finalize_plan
from app.demand.domain.models import Requirement, RequirementLifecycleStatus, SupplyHealth
from app.economics.domain.models import CostSnapshot
from app.main_dependencies import get_session
from app.supply.domain.models import Farmer, ProductionLot
from app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation, SupplyPlan

router = APIRouter(prefix="/requirements", tags=["assurance"])


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
    required_quantity_kg: Decimal
    lifecycle_status: RequirementLifecycleStatus
    supply_health: SupplyHealth
    plan_version: int


class AssuranceRead(BaseModel):
    requirement: RequirementSummary
    supply_health: SupplyHealth
    committed_quantity_kg: Decimal
    standby_quantity_kg: Decimal
    unfilled_quantity_kg: Decimal
    committed_farmer_count: int
    standby_farmer_count: int
    parish_concentration: dict[str, Decimal]
    total_landed_cost_jmd: Decimal | None
    landed_cost_per_kg_jmd: Decimal | None
    allocations: list[AllocationRead]


def _plan_response(result) -> PlanRead:
    return PlanRead(
        id=result.plan_id, requirement_id=result.requirement_id, plan_version=1, planner_version="deterministic-greedy-v1",
        required_quantity_kg=result.required_quantity_kg, committed_quantity_kg=result.committed_quantity_kg,
        standby_quantity_kg=result.standby_quantity_kg, unfilled_quantity_kg=result.unfilled_quantity_kg,
        supply_health=result.supply_health, total_landed_cost_jmd=result.total_landed_cost_jmd,
        landed_cost_per_kg_jmd=result.landed_cost_per_kg_jmd,
    )


@router.post("/{requirement_id}/plan", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(requirement_id: UUID, session: Session = Depends(get_session)) -> PlanRead:
    try:
        return _plan_response(finalize_plan(session, requirement_id, PlannerConfig()))
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
    plan = session.scalar(
        select(SupplyPlan).where(SupplyPlan.requirement_id == requirement.id).order_by(SupplyPlan.plan_version.desc())
    )
    if plan is None:
        return AssuranceRead(
            requirement=requirement, supply_health=requirement.supply_health, committed_quantity_kg=Decimal("0"), standby_quantity_kg=Decimal("0"),
            unfilled_quantity_kg=requirement.required_quantity_kg, committed_farmer_count=0, standby_farmer_count=0,
            parish_concentration={}, total_landed_cost_jmd=None, landed_cost_per_kg_jmd=None, allocations=[],
        )
    rows = session.execute(
        select(SupplyAllocation, ProductionLot, Farmer)
        .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .where(SupplyAllocation.supply_plan_id == plan.id)
        .order_by(SupplyAllocation.created_at, SupplyAllocation.id)
    ).all()
    allocations = [
        AllocationRead(id=allocation.id, production_lot_id=lot.id, farmer_id=farmer.id, farmer_name=farmer.name,
                       parish=lot.parish, role=allocation.role, status=allocation.status,
                       quantity_kg=allocation.quantity_kg, created_at=allocation.created_at)
        for allocation, lot, farmer in rows
    ]
    committed_rows = [(allocation, lot, farmer) for allocation, lot, farmer in rows if allocation.role == AllocationRole.COMMITTED]
    parish_quantities: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for allocation, lot, _ in committed_rows:
        parish_quantities[lot.parish] += allocation.quantity_kg
    concentration = {parish: quantity / plan.committed_quantity_kg for parish, quantity in parish_quantities.items()} if plan.committed_quantity_kg else {}
    cost = session.scalar(select(CostSnapshot).where(CostSnapshot.supply_plan_id == plan.id))
    return AssuranceRead(
        requirement=requirement, supply_health=requirement.supply_health, committed_quantity_kg=plan.committed_quantity_kg, standby_quantity_kg=plan.standby_quantity_kg,
        unfilled_quantity_kg=plan.unfilled_quantity_kg,
        committed_farmer_count=len({farmer.id for _, _, farmer in committed_rows}),
        standby_farmer_count=len({farmer.id for allocation, _, farmer in rows if allocation.role == AllocationRole.STANDBY}),
        parish_concentration=concentration, total_landed_cost_jmd=cost.total_landed_cost_jmd if cost else None,
        landed_cost_per_kg_jmd=cost.landed_cost_per_kg_jmd if cost else None, allocations=allocations,
    )
