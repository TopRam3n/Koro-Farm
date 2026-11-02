"""Deterministic read tools and bounded recovery options for one order (no language model).

`gather` reads the order's current position; `build_options` turns it into a short list of complete options.
Every quantity, cost and eligibility decision is computed here. The decision layer (agents/application/decision.py)
may only pick one of these options by id and explain the choice; it cannot add, remove or resize an action.

Shortfall arithmetic (all for one order):
* assured  = committed coverage (accepted commitments less rejected produce) - exposed commitments
             (committed kilograms the suppliers' latest capacity reports no longer support, WP2);
* gap      = max(0, required - assured);
* in flight = kilograms requested from suppliers and still awaiting an answer;
* net need = max(0, gap - in flight). Replacement actions never exceed the net need.
Exposed commitments are released in the same proposal that replaces them, so the order is never counted twice.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.recovery import _coverage, authorized_standby
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence
from src.backend.app.economics.domain.calculator import CostBreakdown, allocation_cost, money
from src.backend.app.economics.domain.models import CostSnapshot, LotCostInput
from src.backend.app.supply.application.capacity import free_kg, lot_exposure, requirement_exposure
from src.backend.app.supply.application.commitments import default_response_hours
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, SupplierConsent, SupplyAllocation, SupplyPlan,
)

ZERO = Decimal("0")
ACTIVATE_STANDBY = "ACTIVATE_STANDBY"
SOLICIT_SUPPLY = "SOLICIT_SUPPLY"
RELEASE_EXPOSED = "RELEASE_EXPOSED"
CONFIDENCE_RANK = {AvailabilityConfidence.HIGH: 0, AvailabilityConfidence.MEDIUM: 1, AvailabilityConfidence.LOW: 2}


def kg(value: Decimal) -> str:
    """Canonical decimal text for proposals, so hashing never depends on trailing zeros."""
    text = format(Decimal(value).normalize(), "f")
    return text if text != "-0" else "0"


@dataclass(frozen=True)
class Basis:
    required_kg: Decimal
    committed_cover_kg: Decimal
    exposed_kg: Decimal
    assured_kg: Decimal
    gap_kg: Decimal
    in_flight_kg: Decimal
    net_need_kg: Decimal

    def as_dict(self) -> dict:
        return {name: kg(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class StandbyCandidate:
    allocation: SupplyAllocation
    lot: ProductionLot
    farmer: Farmer
    consent: SupplierConsent | None
    activatable_kg: Decimal
    costs: LotCostInput | None


@dataclass(frozen=True)
class SupplyCandidate:
    lot: ProductionLot
    farmer: Farmer
    free_kg: Decimal
    costs: LotCostInput | None


@dataclass(frozen=True)
class Release:
    allocation: SupplyAllocation
    lot: ProductionLot
    farmer: Farmer
    exposed_kg: Decimal
    cause: str = "capacity"
    detail: str = ""


@dataclass
class Evidence:
    requirement: Requirement
    organization_id: UUID
    basis: Basis
    releases: list[Release]
    standby: list[StandbyCandidate]
    supply: list[SupplyCandidate]
    baseline_cost_per_kg: Decimal | None
    response_hours: int
    labels: dict[UUID, str] = field(default_factory=dict)  # farmer id -> pseudonym (S1, S2, ...) for the model


def _in_flight(session: Session, requirement_id: UUID) -> Decimal:
    return session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
        SupplyAllocation.requirement_id == requirement_id, SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.SOLICITED)) or ZERO


@dataclass(frozen=True)
class Exposure:
    allocation: SupplyAllocation
    exposed_kg: Decimal
    cause: str  # "capacity" or "eligibility"
    detail: str


def ineligible_commitments(session: Session, requirement: Requirement) -> dict:
    """Undelivered commitments on lots that no longer match the order or are withdrawn or past viability (P7, P9)."""
    from src.backend.app.assurance.application.exceptions import eligibility_problems, unavailability
    from src.backend.app.supply.application.release import received_kg
    today = datetime.now(timezone.utc).date()
    found = {}
    for allocation in session.scalars(select(SupplyAllocation).where(
            SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.COMMITTED,
            SupplyAllocation.status == AllocationStatus.COMMITTED)).all():
        lot = session.get(ProductionLot, allocation.production_lot_id)
        problems = eligibility_problems(lot, requirement, today)
        unusable = unavailability(lot, requirement, today)
        if problems or unusable:
            undelivered = max(allocation.obligation_kg - received_kg(session, allocation.id), ZERO)
            if undelivered > 0:
                found[allocation.id] = Exposure(allocation, undelivered, "eligibility", "; ".join(problems + ([unusable] if unusable else [])))
    return found


def basis_of(session: Session, requirement: Requirement) -> tuple[Basis, dict]:
    """The order's position. Exposure combines capacity cuts (WP2) and commitments on lots no longer eligible."""
    capacity_total, by_capacity, _ = requirement_exposure(session, requirement.id)
    by_allocation = {k: Exposure(v.allocation, v.exposed_kg, "capacity", "capacity report") for k, v in by_capacity.items() if v.exposed_kg > 0}
    for key, item in ineligible_commitments(session, requirement).items():
        if key not in by_allocation or item.exposed_kg > by_allocation[key].exposed_kg:
            by_allocation[key] = item
    exposed = sum((item.exposed_kg for item in by_allocation.values()), ZERO)
    cover = _coverage(session, requirement.id)
    assured = cover - exposed
    gap = max(requirement.required_quantity_kg - assured, ZERO)
    in_flight = _in_flight(session, requirement.id)
    return Basis(required_kg=requirement.required_quantity_kg, committed_cover_kg=cover, exposed_kg=exposed,
                 assured_kg=assured, gap_kg=gap, in_flight_kg=in_flight,
                 net_need_kg=max(gap - in_flight, ZERO)), by_allocation


def _baseline_cost_per_kg(session: Session, requirement_id: UUID) -> Decimal | None:
    value = session.scalar(select(CostSnapshot.landed_cost_per_kg_jmd).join(SupplyPlan, SupplyPlan.id == CostSnapshot.supply_plan_id)
                           .where(SupplyPlan.requirement_id == requirement_id).order_by(SupplyPlan.plan_version.desc()).limit(1))
    return value if value and value > 0 else None


def gather(session: Session, requirement: Requirement, now: datetime | None = None) -> Evidence:
    now = now or datetime.now(timezone.utc)
    organization_id = session.scalar(select(Buyer.organization_id).where(Buyer.id == requirement.buyer_id))
    basis, by_allocation = basis_of(session, requirement)

    releases: list[Release] = []
    for item in sorted(by_allocation.values(), key=lambda x: str(x.allocation.id)):
        if item.exposed_kg > 0:
            lot = session.get(ProductionLot, item.allocation.production_lot_id)
            releases.append(Release(item.allocation, lot, session.get(Farmer, lot.farmer_id), item.exposed_kg, item.cause, item.detail))

    standby: list[StandbyCandidate] = []
    rows = session.execute(select(SupplyAllocation, ProductionLot, Farmer)
                           .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
                           .join(Farmer, Farmer.id == ProductionLot.farmer_id)
                           .where(SupplyAllocation.requirement_id == requirement.id,
                                  SupplyAllocation.role == AllocationRole.STANDBY, *authorized_standby())
                           .order_by(ProductionLot.parish, ProductionLot.harvest_start, ProductionLot.expected_quantity_kg,
                                     ProductionLot.id, SupplyAllocation.created_at)).all()
    exposures: dict[UUID, object] = {}
    for allocation, lot, farmer in rows:
        if lot.reverification_required or lot.status == ProductionLotStatus.EXHAUSTED:
            continue  # excluded from new commitments until capacity is re-verified (P2, P9)
        if lot.id not in exposures:
            exposures[lot.id] = lot_exposure(session, lot)
        activatable = allocation.obligation_kg - exposures[lot.id].standby_uncovered.get(allocation.id, ZERO)
        if activatable <= 0:
            continue
        consent = session.get(SupplierConsent, allocation.consent_evidence_id) if allocation.consent_evidence_id else None
        costs = session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == lot.id))
        standby.append(StandbyCandidate(allocation, lot, farmer, consent, activatable, costs))

    # Not asked again for this order: lots with an open request, and lots whose supplier declined this order or
    # whose request a coordinator withdrew. (An expired request may be asked again by a person.) Free stock on a lot
    # that also holds standby for the order may still be requested: it is not part of the standby reservation.
    busy_lots = set(session.scalars(select(SupplyAllocation.production_lot_id).where(
        SupplyAllocation.requirement_id == requirement.id,
        SupplyAllocation.status.in_([AllocationStatus.PROPOSED, AllocationStatus.SOLICITED,
                                     AllocationStatus.DECLINED, AllocationStatus.WITHDRAWN]))).all())
    exposed_lots = {release.lot.id for release in releases}
    supply: list[SupplyCandidate] = []
    # Lots needing re-verification are UNAVAILABLE (capacity.refresh_lot_status), so they are never offered here.
    lots = session.execute(select(ProductionLot, Farmer).join(Farmer, Farmer.id == ProductionLot.farmer_id).where(
        Farmer.organization_id == organization_id, ProductionLot.crop == requirement.crop,
        ProductionLot.quality_grade_estimate == requirement.grade, ProductionLot.status == ProductionLotStatus.AVAILABLE,
        ProductionLot.harvest_start <= requirement.delivery_window_end,
        ProductionLot.harvest_end >= requirement.delivery_window_start)).all()
    for lot, farmer in lots:
        free = free_kg(lot)
        if free <= 0 or lot.id in busy_lots or lot.id in exposed_lots:
            continue
        supply.append(SupplyCandidate(lot, farmer, free, session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == lot.id))))
    supply.sort(key=lambda c: (_unit_cost(c.costs) is None, _unit_cost(c.costs) or ZERO,
                               CONFIDENCE_RANK.get(c.lot.availability_confidence, 3), c.farmer.name, str(c.lot.id)))

    labels: dict[UUID, str] = {}
    for farmer in [r.farmer for r in releases] + [c.farmer for c in standby] + [c.farmer for c in supply]:
        labels.setdefault(farmer.id, f"S{len(labels) + 1}")
    return Evidence(requirement=requirement, organization_id=organization_id, basis=basis, releases=releases,
                    standby=standby, supply=supply, baseline_cost_per_kg=_baseline_cost_per_kg(session, requirement.id),
                    response_hours=default_response_hours(requirement, now), labels=labels)


def _unit_cost(costs: LotCostInput | None) -> Decimal | None:
    if costs is None:
        return None
    return (costs.farmgate_price_per_kg_jmd + costs.handling_grading_cost_per_kg_jmd + costs.packaging_cost_per_kg_jmd) \
        * (Decimal("1") + costs.expected_rejection_pct)


# --- Options ------------------------------------------------------------------------------------------------

def _release_action(r: Release, labels: dict) -> dict:
    return {"type": RELEASE_EXPOSED, "allocation_id": str(r.allocation.id), "production_lot_id": str(r.lot.id),
            "farmer_id": str(r.farmer.id), "farmer_name": r.farmer.name, "supplier_label": labels[r.farmer.id],
            "parish": r.lot.parish, "quantity_kg": kg(r.exposed_kg), "cause": r.cause,
            "reason": ("the supplier's latest capacity report no longer supports this part of the commitment" if r.cause == "capacity"
                       else f"the lot no longer meets this order: {r.detail}")}


def _standby_action(c: StandbyCandidate, quantity: Decimal, labels: dict) -> dict:
    return {"type": ACTIVATE_STANDBY, "allocation_id": str(c.allocation.id), "production_lot_id": str(c.lot.id),
            "farmer_id": str(c.farmer.id), "farmer_name": c.farmer.name, "supplier_label": labels[c.farmer.id],
            "parish": c.lot.parish, "quantity_kg": kg(quantity),
            "consent_id": str(c.allocation.consent_evidence_id) if c.allocation.consent_evidence_id else None,
            "consent_channel": c.consent.channel.value if c.consent else None,
            "activation_conditions": c.allocation.activation_conditions,
            "authorization_valid_until": c.allocation.authorization_valid_until.isoformat() if c.allocation.authorization_valid_until else None}


def _solicit_action(c: SupplyCandidate, quantity: Decimal, hours: int, labels: dict) -> dict:
    return {"type": SOLICIT_SUPPLY, "production_lot_id": str(c.lot.id), "farmer_id": str(c.farmer.id),
            "farmer_name": c.farmer.name, "supplier_label": labels[c.farmer.id], "parish": c.lot.parish,
            "quantity_kg": kg(quantity), "respond_within_hours": hours,
            "availability_confidence": c.lot.availability_confidence.value, "message": None}


def _take(candidates, need: Decimal, amount) -> list[tuple[object, Decimal]]:
    chosen = []
    for candidate in candidates:
        if need <= 0:
            break
        quantity = min(need, amount(candidate))
        if quantity > 0:
            chosen.append((candidate, quantity))
            need -= quantity
    return chosen


def _costs_for(evidence: Evidence, picks: list[tuple[object, Decimal]]) -> dict:
    total, replacement, unknown = CostBreakdown(), ZERO, []
    for candidate, quantity in picks:
        replacement += quantity
        if candidate.costs is None:
            unknown.append(str(candidate.lot.id))
        else:
            total = total.plus(allocation_cost(quantity, candidate.costs))
    baseline = evidence.baseline_cost_per_kg
    known = not unknown and baseline is not None
    if replacement == 0:
        return {"known": True, "replacement_kg": "0", "total_landed_cost_jmd": "0.00", "baseline_cost_per_kg_jmd":
                str(baseline) if baseline is not None else None, "increase_jmd": "0.00", "increase_pct": "0", "unknown_cost_lots": []}
    increase = money(total.total_landed_cost_jmd - baseline * replacement) if known else None
    pct = (increase / money(baseline * replacement)).quantize(Decimal("0.0001")) if known else None
    return {"known": known, "replacement_kg": kg(replacement), "total_landed_cost_jmd": str(total.total_landed_cost_jmd) if not unknown else None,
            "baseline_cost_per_kg_jmd": str(baseline) if baseline is not None else None,
            "increase_jmd": str(increase) if increase is not None else None, "increase_pct": str(pct) if pct is not None else None,
            "unknown_cost_lots": unknown, "missing_baseline": baseline is None}


def build_options(evidence: Evidence, excluded: set[str] | None = None) -> list[dict]:
    """Complete, mutually exclusive options. Each has an id, its exact actions, cost and residual escalation.

    excluded: allocation or lot ids a reviewer rejected; they are left out of new options.
    """
    excluded = excluded or set()
    need = evidence.basis.net_need_kg
    if need <= 0:
        return []
    labels = evidence.labels
    releases = [_release_action(r, labels) for r in evidence.releases]
    standby = [c for c in evidence.standby if str(c.allocation.id) not in excluded]
    supply = [c for c in evidence.supply if str(c.lot.id) not in excluded]
    hours = evidence.response_hours

    def option(option_id: str, title: str, standby_picks, supply_picks) -> dict:
        actions = releases + [_standby_action(c, q, labels) for c, q in standby_picks] \
            + [_solicit_action(c, q, hours, labels) for c, q in supply_picks]
        covered = sum((q for _, q in standby_picks), ZERO)
        requested = sum((q for _, q in supply_picks), ZERO)
        return {"id": option_id, "title": title, "actions": actions, "standby_activated_kg": kg(covered),
                "requested_kg": kg(requested), "escalation_kg": kg(need - covered - requested),
                "cost": _costs_for(evidence, list(standby_picks) + list(supply_picks))}

    standby_picks = _take(standby, need, lambda c: c.activatable_kg)
    standby_kg = sum((q for _, q in standby_picks), ZERO)
    options = []
    if standby_picks:
        rest = _take(supply, need - standby_kg, lambda c: c.free_kg)
        options.append(option("A", "Activate authorized standby, then ask new suppliers for the rest", standby_picks, rest))
        if rest:
            options.append(option("C", "Activate authorized standby only; escalate the rest", standby_picks, []))
    supply_picks = _take(supply, need, lambda c: c.free_kg)
    if supply_picks:
        options.append(option("B", "Ask new suppliers only; keep standby in reserve", [], supply_picks))
    options.append(option("D", "Escalate the whole shortfall to a coordinator", [], []))
    return options


def expiry_for(evidence: Evidence, option: dict, now: datetime) -> datetime:
    """An approval is valid until the earliest of: 24 hours, a bound standby authorization ending, delivery starting."""
    limit = now + timedelta(hours=24)
    for action in option["actions"]:
        if action["type"] == ACTIVATE_STANDBY and action["authorization_valid_until"]:
            end = datetime.combine(date.fromisoformat(action["authorization_valid_until"]), datetime.max.time(), tzinfo=timezone.utc)
            limit = min(limit, end)
    start = datetime.combine(evidence.requirement.delivery_window_start, datetime.min.time(), tzinfo=timezone.utc)
    if start > now:
        limit = min(limit, start)
    return max(limit, now + timedelta(hours=1))
