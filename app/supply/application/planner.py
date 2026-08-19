"""Deterministic, database-backed supply planning. No LLM or external dependency."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demand.domain.models import Requirement, RequirementLifecycleStatus, SupplyHealth
from app.domain.common import AvailabilityConfidence, Grade
from app.economics.domain.calculator import CostBreakdown, allocation_cost, money
from app.economics.domain.models import CostSnapshot, LotCostInput
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation, SupplyPlan, SupplyPlanStatus

PLANNER_VERSION = "deterministic-greedy-v1"
CALCULATION_VERSION = "landed-cost-v1"
DEFAULT_STANDBY_TARGET_PCT = Decimal("0.20")
CONFIDENCE_SCORE = {AvailabilityConfidence.LOW: Decimal("1"), AvailabilityConfidence.MEDIUM: Decimal("2"), AvailabilityConfidence.HIGH: Decimal("3")}


class PlanAlreadyExistsError(ValueError):
    pass


class RequirementNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class PlannerConfig:
    standby_target_pct: Decimal = DEFAULT_STANDBY_TARGET_PCT
    minimum_confidence: AvailabilityConfidence = AvailabilityConfidence.MEDIUM
    availability_confidence_weight: Decimal = Decimal("10")
    grade_fit_weight: Decimal = Decimal("10")
    delivery_window_fit_weight: Decimal = Decimal("10")
    farmer_concentration_penalty: Decimal = Decimal("30")
    parish_concentration_penalty: Decimal = Decimal("12")
    landed_cost_weight: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class Candidate:
    lot: ProductionLot
    farmer: Farmer
    costs: LotCostInput
    free_quantity_kg: Decimal


@dataclass(frozen=True)
class PlannedAllocation:
    candidate: Candidate
    role: AllocationRole
    quantity_kg: Decimal


@dataclass(frozen=True)
class PlanResult:
    plan_id: UUID
    requirement_id: UUID
    required_quantity_kg: Decimal
    committed_quantity_kg: Decimal
    standby_quantity_kg: Decimal
    unfilled_quantity_kg: Decimal
    committed_farmer_count: int
    standby_farmer_count: int
    parishes_used: int
    supply_health: SupplyHealth
    total_landed_cost_jmd: Decimal
    landed_cost_per_kg_jmd: Decimal


def _minimum_confidence_value(confidence: AvailabilityConfidence) -> int:
    return list(AvailabilityConfidence).index(confidence)


def _eligible(requirement: Requirement, lot: ProductionLot, costs: LotCostInput, config: PlannerConfig) -> bool:
    return (
        lot.crop == requirement.crop
        and lot.quality_grade_estimate == requirement.grade == Grade.A
        and lot.harvest_start <= requirement.delivery_window_end
        and lot.harvest_end >= requirement.delivery_window_start
        and lot.status == ProductionLotStatus.AVAILABLE
        and lot.available_quantity_kg > lot.reserved_quantity_kg
        and _minimum_confidence_value(lot.availability_confidence) >= _minimum_confidence_value(config.minimum_confidence)
    )


def _estimated_unit_cost(costs: LotCostInput) -> Decimal:
    # Fixed pickup and transport are normalized to 1kg only for deterministic ranking.
    return (
        costs.farmgate_price_per_kg_jmd + costs.handling_grading_cost_per_kg_jmd + costs.packaging_cost_per_kg_jmd
    ) * (Decimal("1") + costs.expected_rejection_pct) + costs.pickup_cost_jmd + costs.transport_cost_jmd


def _score(candidate: Candidate, farmer_counts: Counter[UUID], parish_counts: Counter[str], config: PlannerConfig) -> Decimal:
    return (
        CONFIDENCE_SCORE[candidate.lot.availability_confidence] * config.availability_confidence_weight
        + config.grade_fit_weight
        + config.delivery_window_fit_weight
        - config.farmer_concentration_penalty * farmer_counts[candidate.farmer.id]
        - config.parish_concentration_penalty * parish_counts[candidate.lot.parish]
        - config.landed_cost_weight * _estimated_unit_cost(candidate.costs)
    )


def _choose_allocations(candidates: list[Candidate], target: Decimal, role: AllocationRole, config: PlannerConfig, free: dict[UUID, Decimal], farmer_counts: Counter[UUID], parish_counts: Counter[str]) -> list[PlannedAllocation]:
    remaining = target
    result: list[PlannedAllocation] = []
    while remaining > 0:
        choices = [candidate for candidate in candidates if free[candidate.lot.id] > 0]
        if not choices:
            break
        chosen = sorted(
            choices,
            key=lambda candidate: (-_score(candidate, farmer_counts, parish_counts, config), str(candidate.lot.id)),
        )[0]
        quantity = min(remaining, free[chosen.lot.id])
        result.append(PlannedAllocation(chosen, role, quantity))
        free[chosen.lot.id] -= quantity
        remaining -= quantity
        farmer_counts[chosen.farmer.id] += 1
        parish_counts[chosen.lot.parish] += 1
    return result


def _cost_snapshot(plan_id: UUID, allocations: list[PlannedAllocation]) -> CostSnapshot:
    breakdown = CostBreakdown()
    for allocation in allocations:
        if allocation.role == AllocationRole.COMMITTED:
            breakdown = breakdown.plus(allocation_cost(allocation.quantity_kg, allocation.candidate.costs))
    committed_quantity = sum((allocation.quantity_kg for allocation in allocations if allocation.role == AllocationRole.COMMITTED), Decimal("0"))
    unit_cost = money(breakdown.total_landed_cost_jmd / committed_quantity) if committed_quantity else Decimal("0.00")
    return CostSnapshot(
        supply_plan_id=plan_id,
        produce_cost_jmd=breakdown.produce_cost_jmd,
        pickup_cost_jmd=breakdown.pickup_cost_jmd,
        handling_cost_jmd=breakdown.handling_cost_jmd,
        packaging_cost_jmd=breakdown.packaging_cost_jmd,
        transport_cost_jmd=breakdown.transport_cost_jmd,
        expected_rejection_cost_jmd=breakdown.expected_rejection_cost_jmd,
        total_landed_cost_jmd=breakdown.total_landed_cost_jmd,
        landed_cost_per_kg_jmd=unit_cost,
        calculation_version=CALCULATION_VERSION,
    )


def finalize_plan(session: Session, requirement_id: UUID, config: PlannerConfig = PlannerConfig()) -> PlanResult:
    """Create exactly one initial, immutable plan under requirement and lot row locks."""
    # API commands arrive without a transaction. A nested transaction keeps the service
    # usable after a caller performed a read (SQLAlchemy autobegins on reads) without
    # weakening the row-locking invariant of the caller's enclosing transaction.
    transaction = session.begin_nested() if session.in_transaction() else session.begin()
    with transaction:
        requirement = session.scalar(select(Requirement).where(Requirement.id == requirement_id).with_for_update())
        if requirement is None:
            raise RequirementNotFoundError("requirement not found")
        if requirement.plan_version != 0:
            raise PlanAlreadyExistsError("an initial plan already exists; replanning is not implemented")

        rows = session.execute(
            select(ProductionLot, Farmer, LotCostInput)
            .join(Farmer, Farmer.id == ProductionLot.farmer_id)
            .join(LotCostInput, LotCostInput.production_lot_id == ProductionLot.id)
            .order_by(ProductionLot.id)
            .with_for_update()
        ).all()
        candidates = [
            Candidate(lot=lot, farmer=farmer, costs=costs, free_quantity_kg=lot.available_quantity_kg - lot.reserved_quantity_kg)
            for lot, farmer, costs in rows if _eligible(requirement, lot, costs, config)
        ]
        free = {candidate.lot.id: candidate.free_quantity_kg for candidate in candidates}
        farmer_counts: Counter[UUID] = Counter()
        parish_counts: Counter[str] = Counter()
        committed = _choose_allocations(candidates, requirement.required_quantity_kg, AllocationRole.COMMITTED, config, free, farmer_counts, parish_counts)
        committed_quantity = sum((allocation.quantity_kg for allocation in committed), Decimal("0"))
        standby_target = requirement.required_quantity_kg * config.standby_target_pct
        standby = _choose_allocations(candidates, standby_target, AllocationRole.STANDBY, config, free, farmer_counts, parish_counts)
        standby_quantity = sum((allocation.quantity_kg for allocation in standby), Decimal("0"))
        allocations = committed + standby
        unfilled = requirement.required_quantity_kg - committed_quantity
        health = SupplyHealth.COVERED if unfilled == 0 else SupplyHealth.AT_RISK
        plan_version = requirement.plan_version + 1
        plan = SupplyPlan(
            requirement_id=requirement.id, plan_version=plan_version, planner_version=PLANNER_VERSION,
            status=SupplyPlanStatus.FINALIZED, required_quantity_kg=requirement.required_quantity_kg,
            committed_quantity_kg=committed_quantity, standby_quantity_kg=standby_quantity, unfilled_quantity_kg=unfilled,
        )
        session.add(plan)
        session.flush()
        for allocation in allocations:
            allocation.candidate.lot.reserved_quantity_kg += allocation.quantity_kg
            session.add(SupplyAllocation(
                requirement_id=requirement.id, supply_plan_id=plan.id, production_lot_id=allocation.candidate.lot.id,
                role=allocation.role,
                status=AllocationStatus.COMMITTED if allocation.role == AllocationRole.COMMITTED else AllocationStatus.STANDBY,
                quantity_kg=allocation.quantity_kg, consent_evidence_id=uuid4(), plan_version=plan_version,
            ))
        snapshot = _cost_snapshot(plan.id, allocations)
        session.add(snapshot)
        requirement.plan_version = plan_version
        requirement.version += 1
        requirement.supply_health = health
        requirement.lifecycle_status = RequirementLifecycleStatus.ACTIVE if health == SupplyHealth.COVERED else RequirementLifecycleStatus.PLANNING
        session.flush()
        return PlanResult(
            plan_id=plan.id, requirement_id=requirement.id, required_quantity_kg=requirement.required_quantity_kg,
            committed_quantity_kg=committed_quantity, standby_quantity_kg=standby_quantity, unfilled_quantity_kg=unfilled,
            committed_farmer_count=len({allocation.candidate.farmer.id for allocation in committed}),
            standby_farmer_count=len({allocation.candidate.farmer.id for allocation in standby}),
            parishes_used=len({allocation.candidate.lot.parish for allocation in allocations}), supply_health=health,
            total_landed_cost_jmd=snapshot.total_landed_cost_jmd, landed_cost_per_kg_jmd=snapshot.landed_cost_per_kg_jmd,
        )
