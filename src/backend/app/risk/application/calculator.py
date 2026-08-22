"""Documented deterministic risk-v1 policy.  Indicators are facts; labels are heuristics."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Requirement
from src.backend.app.domain.common import AvailabilityConfidence
from src.backend.app.risk.domain.models import RiskLabel, RiskSnapshot
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation, SupplyPlan

RISK_CALCULATION_VERSION = "risk-v1"
CONFIDENCE_VALUE = {AvailabilityConfidence.LOW: Decimal("0.33"), AvailabilityConfidence.MEDIUM: Decimal("0.67"), AvailabilityConfidence.HIGH: Decimal("1.00")}


@dataclass(frozen=True)
class RiskPolicy:
    """risk-v1 thresholds; all percentage fields use the 0..100 display scale."""
    high_largest_farmer_share_pct: Decimal = Decimal("35")
    high_largest_parish_share_pct: Decimal = Decimal("70")
    high_parish_standby_coverage_pct: Decimal = Decimal("15")
    high_standby_coverage_pct: Decimal = Decimal("10")
    high_replacement_depth_pct: Decimal = Decimal("20")
    minimum_average_confidence: Decimal = Decimal("0.67")
    medium_largest_farmer_share_pct: Decimal = Decimal("25")
    medium_largest_parish_share_pct: Decimal = Decimal("55")
    medium_standby_coverage_pct: Decimal = Decimal("20")
    medium_replacement_depth_pct: Decimal = Decimal("30")


def _rule(indicator: str, actual: Decimal, threshold: Decimal, message: str) -> dict:
    return {"indicator": indicator, "actual": str(actual), "threshold": str(threshold), "message": message}


def create_risk_snapshot(session: Session, requirement: Requirement, plan: SupplyPlan, policy: RiskPolicy = RiskPolicy()) -> RiskSnapshot:
    """Freeze active supply-plan structure and currently eligible unreserved recovery depth."""
    rows = session.execute(select(SupplyAllocation, ProductionLot, Farmer).join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id).join(Farmer, Farmer.id == ProductionLot.farmer_id).where(SupplyAllocation.requirement_id == requirement.id)).all()
    committed = [(a, lot, farmer) for a, lot, farmer in rows if a.role == AllocationRole.COMMITTED and a.status == AllocationStatus.COMMITTED]
    standby = [(a, lot, farmer) for a, lot, farmer in rows if a.role == AllocationRole.STANDBY and a.status == AllocationStatus.STANDBY and a.consent_evidence_id is not None]
    required = requirement.required_quantity_kg
    committed_qty = sum((a.quantity_kg for a, _, _ in committed), Decimal("0"))
    standby_qty = sum((a.quantity_kg for a, _, _ in standby), Decimal("0"))
    farmer_qty: defaultdict = defaultdict(lambda: Decimal("0")); parish_qty: defaultdict = defaultdict(lambda: Decimal("0"))
    for allocation, lot, farmer in committed:
        farmer_qty[farmer.id] += allocation.quantity_kg; parish_qty[lot.parish] += allocation.quantity_kg
    largest_farmer = max(farmer_qty.values(), default=Decimal("0")) * Decimal("100") / required
    largest_parish = max(parish_qty.values(), default=Decimal("0")) * Decimal("100") / required
    standby_pct = standby_qty * Decimal("100") / required
    confidence = sum((a.quantity_kg * CONFIDENCE_VALUE[lot.availability_confidence] for a, lot, _ in committed), Decimal("0")) / committed_qty if committed_qty else Decimal("0")
    recovery_lots = session.execute(select(ProductionLot, Farmer).join(Farmer, Farmer.id == ProductionLot.farmer_id).where(
        ProductionLot.crop == requirement.crop, ProductionLot.quality_grade_estimate == requirement.grade,
        ProductionLot.status == ProductionLotStatus.AVAILABLE, Farmer.active.is_(True),
        ProductionLot.harvest_start <= requirement.delivery_window_end, ProductionLot.harvest_end >= requirement.delivery_window_start,
        ProductionLot.available_quantity_kg > ProductionLot.reserved_quantity_kg,
        ProductionLot.availability_confidence.in_([AvailabilityConfidence.MEDIUM, AvailabilityConfidence.HIGH]),
    )).all()
    replacement_depth = sum((lot.available_quantity_kg - lot.reserved_quantity_kg for lot, _ in recovery_lots), Decimal("0"))
    rules: list[dict] = []
    if committed_qty < required: rules.append(_rule("committed_coverage_pct", committed_qty * 100 / required, Decimal("100"), "Committed coverage is below the required quantity"))
    if largest_farmer > policy.high_largest_farmer_share_pct: rules.append(_rule("largest_farmer_share_pct", largest_farmer, policy.high_largest_farmer_share_pct, "A single farmer provides more than the high-risk concentration threshold"))
    if largest_parish > policy.high_largest_parish_share_pct and standby_pct < policy.high_parish_standby_coverage_pct: rules.append(_rule("largest_parish_share_pct", largest_parish, policy.high_largest_parish_share_pct, "Parish concentration is high while standby coverage is limited"))
    if standby_pct < policy.high_standby_coverage_pct and replacement_depth < required * policy.high_replacement_depth_pct / 100: rules.append(_rule("replacement_depth_kg", replacement_depth, required * policy.high_replacement_depth_pct / 100, "Both standby coverage and potential replacement depth are low"))
    if confidence < policy.minimum_average_confidence: rules.append(_rule("average_availability_confidence", confidence, policy.minimum_average_confidence, "Committed supply estimate confidence is below the configured minimum"))
    label = RiskLabel.HIGH if rules else RiskLabel.LOW
    if not rules:
        if largest_farmer > policy.medium_largest_farmer_share_pct: rules.append(_rule("largest_farmer_share_pct", largest_farmer, policy.medium_largest_farmer_share_pct, "A single farmer provides more than the medium-risk concentration threshold"))
        if largest_parish > policy.medium_largest_parish_share_pct: rules.append(_rule("largest_parish_share_pct", largest_parish, policy.medium_largest_parish_share_pct, "Parish concentration exceeds the medium-risk threshold"))
        if standby_pct < policy.medium_standby_coverage_pct: rules.append(_rule("standby_coverage_pct", standby_pct, policy.medium_standby_coverage_pct, "Standby capacity is below the medium-risk target"))
        if replacement_depth < required * policy.medium_replacement_depth_pct / 100: rules.append(_rule("replacement_depth_kg", replacement_depth, required * policy.medium_replacement_depth_pct / 100, "Potential replacement depth is below the medium-risk target"))
        if rules: label = RiskLabel.MEDIUM
    snapshot = RiskSnapshot(requirement_id=requirement.id, supply_plan_id=plan.id, plan_version=plan.plan_version,
        committed_farmer_count=len(farmer_qty), standby_farmer_count=len({farmer.id for _, _, farmer in standby}),
        committed_parish_count=len(parish_qty), standby_parish_count=len({lot.parish for _, lot, _ in standby}),
        largest_farmer_share_pct=largest_farmer, largest_parish_share_pct=largest_parish, standby_coverage_pct=standby_pct,
        replacement_depth_kg=replacement_depth, average_availability_confidence=confidence, committed_quantity_kg=committed_qty,
        standby_quantity_kg=standby_qty, required_quantity_kg=required, risk_label=label, rules_triggered=rules,
        calculation_version=RISK_CALCULATION_VERSION)
    session.add(snapshot)
    return snapshot
