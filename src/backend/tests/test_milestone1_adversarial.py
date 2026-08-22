"""Milestone 1 adversarial checks: reservations, recovery, consent, and audit history."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.backend.app.assurance.application import recovery
from src.backend.app.assurance.application.recovery import accept, decline, dropout
from src.backend.app.assurance.domain.models import DomainEvent, RecoveryRun, RecoveryStatus
from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, Requirement, SupplyHealth
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import CostSnapshot, LotCostInput
from src.backend.app.supply.application.planner import PlannerConfig, finalize_plan
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation
from src.backend.app.risk.domain.models import RiskLabel, RiskSnapshot


def requirement(session, quantity="500"):
    buyer = Buyer(name="Hotel", buyer_type="HOTEL", destination="Jamaica")
    session.add(buyer); session.flush()
    return create_requirement(session, Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
        required_quantity_kg=Decimal(quantity), delivery_window_start=date(2026, 9, 1), delivery_window_end=date(2026, 9, 10)))


def lot(session, quantity, price="300", confidence=AvailabilityConfidence.HIGH):
    farmer = Farmer(name=f"F-{uuid4()}", parish="Clarendon")
    session.add(farmer); session.flush()
    item = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 9, 1), harvest_end=date(2026, 9, 10),
        expected_quantity_kg=Decimal(quantity), available_quantity_kg=Decimal(quantity), reserved_quantity_kg=Decimal("0"),
        quality_grade_estimate=Grade.A, availability_confidence=confidence, parish="Clarendon",
        status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
    session.add(item); session.flush()
    session.add(LotCostInput(production_lot_id=item.id, farmgate_price_per_kg_jmd=Decimal(price), pickup_cost_jmd=Decimal("0"),
        handling_grading_cost_per_kg_jmd=Decimal("20"), packaging_cost_per_kg_jmd=Decimal("10"), transport_cost_jmd=Decimal("0"), expected_rejection_pct=Decimal("0")))
    session.commit()
    return item


def test_dropout_is_idempotent_restores_exact_coverage_and_audits(session):
    req = requirement(session)
    for _ in range(8): lot(session, "80")
    plan = finalize_plan(session, req.id)
    assert (plan.committed_quantity_kg, plan.standby_quantity_kg) == (Decimal("500"), Decimal("100"))
    lost = session.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id,
        SupplyAllocation.role == AllocationRole.COMMITTED, SupplyAllocation.quantity_kg == Decimal("80")))
    result = dropout(session, lost.id, "crop_failure", "same-command")
    duplicate = dropout(session, lost.id, "crop_failure", "same-command")
    assert result == duplicate
    assert result["committed_kg"] == "500.000"
    session.refresh(req); assert req.supply_health == SupplyHealth.COVERED
    events = list(session.scalars(select(DomainEvent).where(DomainEvent.aggregate_id == req.id).order_by(DomainEvent.occurred_at)))
    names = [event.event_type for event in events]
    assert [event.occurred_at for event in events] == sorted(event.occurred_at for event in events)
    for expected in ("plan.created", "allocation.lost", "requirement.at_risk", "recovery.started", "allocation.standby_activated", "recovery.completed"):
        assert expected in names
    snapshots = list(session.scalars(select(RiskSnapshot).where(RiskSnapshot.requirement_id == req.id).order_by(RiskSnapshot.plan_version)))
    assert len(snapshots) == 2
    assert snapshots[0].supply_plan_id != snapshots[1].supply_plan_id


def test_partial_standby_solicitation_and_explicit_acceptance(session):
    req = requirement(session, "100")
    # 100 committed, 8 standby, then 92 unallocated capacity available for solicitation.
    for quantity, price in (("100", "100"), ("8", "350"), ("92", "350")):
        lot(session, quantity, price)
    finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0.08")))
    committed = session.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id,
        SupplyAllocation.role == AllocationRole.COMMITTED, SupplyAllocation.status == AllocationStatus.COMMITTED))
    outcome = dropout(session, committed.id, "crop_failure", "partial")
    assert outcome["supply_health"] == SupplyHealth.ESCALATION_REQUIRED
    solicited = list(session.scalars(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.SOLICITED)))
    assert solicited
    assert outcome["committed_kg"] == "8.000"  # solicitation never masquerades as coverage
    for number, allocation in enumerate(solicited):
        accepted = accept(session, allocation.id, f"accept-{number}")
    assert accepted["committed_kg"] == "100.000"
    assert accept(session, solicited[-1].id, f"accept-{len(solicited) - 1}") == accepted
    session.refresh(req); assert req.supply_health == SupplyHealth.COVERED
    events = list(session.scalars(select(DomainEvent).where(DomainEvent.aggregate_id == req.id).order_by(
        DomainEvent.occurred_at, DomainEvent.id)))
    names = [event.event_type for event in events]
    assert [event.occurred_at for event in events] == sorted(event.occurred_at for event in events)
    for expected in ("allocation.solicited", "allocation.accepted", "recovery.escalated", "recovery.completed"):
        assert expected in names


def test_second_requirement_cannot_consume_reserved_standby(session):
    first, second = requirement(session, "100"), requirement(session, "100")
    for _ in range(2): lot(session, "60")
    first_plan = finalize_plan(session, first.id)
    assert first_plan.committed_quantity_kg == Decimal("100")
    second_plan = finalize_plan(session, second.id)
    assert second_plan.committed_quantity_kg == Decimal("0")
    assert second_plan.standby_quantity_kg == Decimal("0")


def test_database_rejects_invalid_reservation(session):
    item = lot(session, "10")
    item.reserved_quantity_kg = Decimal("10.001")
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_decline_releases_solicited_stock_without_calling_it_coverage(session):
    req = requirement(session, "100")
    for quantity, price in (("100", "100"), ("20", "350"), ("80", "350")):
        lot(session, quantity, price)
    finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0.20")))
    committed = session.scalar(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == req.id, SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED))
    dropout(session, committed.id, "crop_failure", "decline-dropout")
    solicited = session.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id,
        SupplyAllocation.status == AllocationStatus.SOLICITED))
    source = session.get(ProductionLot, solicited.production_lot_id)
    reserved_before = source.reserved_quantity_kg
    result = decline(session, solicited.id, "decline")
    session.refresh(source)
    assert result["committed_kg"] == "20.000"
    assert source.reserved_quantity_kg == reserved_before - solicited.quantity_kg
    assert decline(session, solicited.id, "decline") == result


@pytest.mark.parametrize(("standby_price", "expect_positive"), [("500", True), ("50", False)])
def test_recovery_snapshot_is_new_immutable_decimal_cost_record(session, standby_price, expect_positive):
    req = requirement(session, "100")
    # A 100kg standby lot supplies the entire loss, so no solicited quantity is
    # ever counted as committed in this economic test.
    lot(session, "100", "300", AvailabilityConfidence.HIGH)
    lot(session, "100", standby_price, AvailabilityConfidence.MEDIUM)
    plan = finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("1"), landed_cost_weight=Decimal("0")))
    original = session.scalar(select(CostSnapshot).where(CostSnapshot.supply_plan_id == plan.plan_id))
    committed = session.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id,
        SupplyAllocation.role == AllocationRole.COMMITTED, SupplyAllocation.status == AllocationStatus.COMMITTED))
    dropout(session, committed.id, "crop_failure", f"cost-{standby_price}")
    snapshots = list(session.scalars(select(CostSnapshot).order_by(CostSnapshot.created_at)))
    assert len(snapshots) == 2
    assert original.total_landed_cost_jmd == Decimal("33000.00")
    delta = snapshots[-1].total_landed_cost_jmd - original.total_landed_cost_jmd
    assert (delta > 0) is expect_positive
    assert all(isinstance(snapshot.total_landed_cost_jmd, Decimal) for snapshot in snapshots)


def test_intentional_recovery_failure_rolls_back_all_writes(session, monkeypatch):
    req = requirement(session, "100")
    lot(session, "100")
    plan = finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    committed = session.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
    original_event = recovery._event

    def fail_on_recovery_start(*args, **kwargs):
        if args[1] == "recovery.started":
            raise RuntimeError("intentional mid-command failure")
        return original_event(*args, **kwargs)

    monkeypatch.setattr(recovery, "_event", fail_on_recovery_start)
    with pytest.raises(RuntimeError, match="intentional"):
        dropout(session, committed.id, "crop_failure", "rollback")
    session.rollback()
    session.refresh(committed); session.refresh(req)
    assert committed.status == AllocationStatus.COMMITTED
    assert req.supply_health == SupplyHealth.COVERED
    assert not list(session.scalars(select(RecoveryRun).where(RecoveryRun.requirement_id == req.id)))


def test_database_rejects_non_positive_allocation_quantity(session):
    req = requirement(session, "10")
    lot(session, "10")
    plan = finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
    allocation.quantity_kg = Decimal("0")
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_risk_snapshot_aggregates_farmer_lots_and_is_immutable(session):
    req = requirement(session, "100")
    farmer = Farmer(name="One farmer", parish="Manchester")
    session.add(farmer); session.flush()
    # Two lots deliberately belong to the same farmer, proving shares aggregate
    # by farmer rather than counting individual production lots.
    for quantity, confidence in (("60", AvailabilityConfidence.HIGH), ("40", AvailabilityConfidence.MEDIUM)):
        item = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 9, 1), harvest_end=date(2026, 9, 10),
            expected_quantity_kg=Decimal(quantity), available_quantity_kg=Decimal(quantity), reserved_quantity_kg=Decimal("0"),
            quality_grade_estimate=Grade.A, availability_confidence=confidence, parish="Manchester", status=ProductionLotStatus.AVAILABLE,
            last_verified_at=datetime.now(timezone.utc))
        session.add(item); session.flush(); session.add(LotCostInput(production_lot_id=item.id, farmgate_price_per_kg_jmd=Decimal("100"), pickup_cost_jmd=Decimal("0"), handling_grading_cost_per_kg_jmd=Decimal("0"), packaging_cost_per_kg_jmd=Decimal("0"), transport_cost_jmd=Decimal("0"), expected_rejection_pct=Decimal("0")))
    session.commit()
    plan = finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    snapshot = session.scalar(select(RiskSnapshot).where(RiskSnapshot.supply_plan_id == plan.plan_id))
    assert snapshot.risk_label == RiskLabel.HIGH
    assert snapshot.committed_farmer_count == snapshot.committed_parish_count == 1
    assert snapshot.largest_farmer_share_pct == snapshot.largest_parish_share_pct == Decimal("100.000")
    assert snapshot.standby_coverage_pct == snapshot.replacement_depth_kg == Decimal("0.000")
    assert snapshot.average_availability_confidence == Decimal("0.868")
    original = snapshot.largest_farmer_share_pct
    item.status = ProductionLotStatus.UNAVAILABLE
    session.commit(); session.refresh(snapshot)
    assert snapshot.largest_farmer_share_pct == original
