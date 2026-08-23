from datetime import date, datetime, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from src.backend.app.demand.domain.models import Buyer, Requirement, SupplyHealth
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.calculator import allocation_cost
from src.backend.app.economics.domain.models import CostSnapshot, LotCostInput
from src.backend.app.supply.application.planner import PlanAlreadyExistsError, PlannerConfig, finalize_plan
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, SupplyAllocation, SupplyPlan
from src.backend.app.infrastructure.database.base import Base


def make_requirement(session, quantity: str = "500") -> Requirement:
    buyer = Buyer(name="Buyer", buyer_type="HOTEL", destination="Montego Bay")
    session.add(buyer)
    session.flush()
    requirement = Requirement(
        buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A, required_quantity_kg=Decimal(quantity),
        delivery_window_start=date(2026, 9, 10), delivery_window_end=date(2026, 9, 12),
    )
    session.add(requirement)
    session.commit()
    return requirement


def make_lot(session, name: str, parish: str, quantity: str, *, grade=Grade.A, confidence=AvailabilityConfidence.HIGH,
             start=date(2026, 9, 8), end=date(2026, 9, 13), reserved="0", farmgate="300", pickup="100", transport="100") -> ProductionLot:
    farmer = Farmer(name=name, parish=parish)
    session.add(farmer)
    session.flush()
    lot = ProductionLot(
        farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=start, harvest_end=end,
        expected_quantity_kg=Decimal(quantity), available_quantity_kg=Decimal(quantity), reserved_quantity_kg=Decimal(reserved),
        quality_grade_estimate=grade, availability_confidence=confidence, parish=parish,
        status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc),
    )
    session.add(lot)
    session.flush()
    session.add(LotCostInput(
        production_lot_id=lot.id, farmgate_price_per_kg_jmd=Decimal(farmgate), pickup_cost_jmd=Decimal(pickup),
        handling_grading_cost_per_kg_jmd=Decimal("20"), packaging_cost_per_kg_jmd=Decimal("10"),
        transport_cost_jmd=Decimal(transport), expected_rejection_pct=Decimal("0.02"),
    ))
    session.commit()
    return lot


def test_exact_500kg_fill_and_20_percent_standby(session) -> None:
    requirement = make_requirement(session)
    for number, parish in enumerate(["Manchester", "St. Elizabeth", "Clarendon", "St. Ann", "Manchester", "Clarendon"]):
        make_lot(session, f"Farmer {number}", parish, "100")
    result = finalize_plan(session, requirement.id)
    assert result.committed_quantity_kg == Decimal("500")
    assert result.standby_quantity_kg == Decimal("100")
    assert result.unfilled_quantity_kg == Decimal("0")
    assert result.supply_health == SupplyHealth.COVERED


def test_insufficient_committed_supply_is_at_risk(session) -> None:
    requirement = make_requirement(session)
    make_lot(session, "A", "Manchester", "300")
    result = finalize_plan(session, requirement.id)
    assert result.committed_quantity_kg == Decimal("300")
    assert result.unfilled_quantity_kg == Decimal("200")
    assert result.supply_health == SupplyHealth.AT_RISK


def test_insufficient_standby_is_truthful(session) -> None:
    requirement = make_requirement(session)
    make_lot(session, "A", "Manchester", "500")
    make_lot(session, "B", "Clarendon", "50")
    result = finalize_plan(session, requirement.id)
    assert result.committed_quantity_kg == Decimal("500")
    assert result.standby_quantity_kg == Decimal("50")


def test_no_eligible_lots(session) -> None:
    requirement = make_requirement(session)
    make_lot(session, "A", "Manchester", "500", confidence=AvailabilityConfidence.LOW)
    result = finalize_plan(session, requirement.id)
    assert result.committed_quantity_kg == Decimal("0")
    assert result.unfilled_quantity_kg == Decimal("500")


def test_harvest_window_and_grade_mismatch_are_excluded(session) -> None:
    requirement = make_requirement(session)
    make_lot(session, "Too Early", "Manchester", "500", end=date(2026, 9, 9))
    make_lot(session, "Grade B", "Clarendon", "500", grade=Grade.B)
    result = finalize_plan(session, requirement.id)
    assert result.committed_quantity_kg == Decimal("0")


def test_partially_reserved_lot_uses_only_free_quantity(session) -> None:
    requirement = make_requirement(session)
    lot = make_lot(session, "A", "Manchester", "500", reserved="200")
    make_lot(session, "B", "Clarendon", "300")
    result = finalize_plan(session, requirement.id)
    session.refresh(lot)
    assert result.committed_quantity_kg == Decimal("500")
    assert Decimal("200") <= lot.reserved_quantity_kg <= Decimal("500")


def test_second_attempt_cannot_double_allocate(session) -> None:
    requirement = make_requirement(session, "100")
    lot = make_lot(session, "A", "Manchester", "200")
    finalize_plan(session, requirement.id)
    with pytest.raises(PlanAlreadyExistsError):
        finalize_plan(session, requirement.id)
    session.refresh(lot)
    assert lot.reserved_quantity_kg == Decimal("120.000")  # 100 committed + 20 standby


def test_concurrent_planning_attempts_create_only_one_plan() -> None:
    database_path = Path.cwd() / f"planner_concurrency_{uuid4()}.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    setup = factory()
    requirement = make_requirement(setup, "100")
    lot = make_lot(setup, "A", "Manchester", "120")
    setup.close()
    barrier = Barrier(2)

    def attempt():
        session = factory()
        try:
            barrier.wait()
            return finalize_plan(session, requirement.id)
        except (PlanAlreadyExistsError, IntegrityError, OperationalError):
            return None
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    verify = factory()
    try:
        assert sum(result is not None for result in results) == 1
        assert len(list(verify.scalars(select(SupplyPlan)))) == 1
        assert verify.get(ProductionLot, lot.id).reserved_quantity_kg <= Decimal("120")
    finally:
        verify.close()
        engine.dispose()
        database_path.unlink(missing_ok=True)


def test_cost_arithmetic_and_decimal_precision(session) -> None:
    requirement = make_requirement(session, "1.5")
    lot = make_lot(session, "A", "Manchester", "2", farmgate="100.11", pickup="10.01", transport="20.02")
    inputs = session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == lot.id))
    cost = allocation_cost(Decimal("1.5"), inputs)
    assert cost.produce_cost_jmd == Decimal("150.17")
    assert cost.expected_rejection_cost_jmd == Decimal("3.00")
    result = finalize_plan(session, requirement.id, PlannerConfig(standby_target_pct=Decimal("0")))
    assert result.total_landed_cost_jmd == Decimal("228.20")


def test_cost_snapshots_remain_immutable_when_inputs_change(session) -> None:
    requirement = make_requirement(session, "100")
    lot = make_lot(session, "A", "Manchester", "100")
    result = finalize_plan(session, requirement.id, PlannerConfig(standby_target_pct=Decimal("0")))
    snapshot = session.scalar(select(CostSnapshot).where(CostSnapshot.supply_plan_id == result.plan_id))
    original_total = snapshot.total_landed_cost_jmd
    inputs = session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == lot.id))
    inputs.farmgate_price_per_kg_jmd = Decimal("999")
    session.commit()
    session.refresh(snapshot)
    assert snapshot.total_landed_cost_jmd == original_total


def test_concentration_weight_can_prefer_more_diverse_lot_over_cheapest(session) -> None:
    requirement = make_requirement(session, "150")
    cheap_one = make_lot(session, "Cheap One", "Manchester", "100", farmgate="100", pickup="0", transport="0")
    cheap_two = make_lot(session, "Cheap Two", "Manchester", "100", farmgate="100", pickup="0", transport="0")
    diverse = make_lot(session, "Diverse", "Clarendon", "100", farmgate="500", pickup="0", transport="0")
    # After the first Manchester lot, its parish penalty outweighs the J$400/kg cost advantage.
    result = finalize_plan(session, requirement.id, PlannerConfig(standby_target_pct=Decimal("0"), landed_cost_weight=Decimal("0.01")))
    allocated_lot_ids = set(session.scalars(select(SupplyAllocation.production_lot_id).where(SupplyAllocation.supply_plan_id == result.plan_id)))
    assert diverse.id in allocated_lot_ids
    assert len({cheap_one.id, cheap_two.id} & allocated_lot_ids) == 1


def test_plan_and_allocation_snapshots_are_persisted(session) -> None:
    requirement = make_requirement(session, "100")
    make_lot(session, "A", "Manchester", "120")
    result = finalize_plan(session, requirement.id)
    assert session.get(SupplyPlan, result.plan_id).status.value == "FINALIZED"
    assert len(list(session.scalars(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == result.plan_id)))) == 2
