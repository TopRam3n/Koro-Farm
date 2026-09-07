"""Blocking concurrency checks. These are skipped unless a dedicated PostgreSQL URL is supplied."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Barrier, Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.backend.app.assurance.application.recovery import accept, continue_recovery, dropout
from src.backend.app.assurance.domain.models import DomainEvent, RecoveryRun
from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.application.services import grade, receive
from src.backend.app.fulfilment.domain.models import FulfilmentNode, ReceivedSublot
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.reconciliation.api.router import AddSublot, add_sublot
from src.backend.app.reconciliation.domain.models import Shipment, ShipmentSublot
from src.backend.app.supply.application import planner as planner_module
from src.backend.app.supply.application.planner import PlannerConfig, finalize_plan
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="dedicated PostgreSQL test database not configured")


@pytest.fixture()
def pg_factory():
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def requirement(session: Session, quantity: str = "100") -> Requirement:
    buyer = Buyer(name=f"Buyer {uuid4()}", buyer_type="HOTEL", destination="Jamaica")
    session.add(buyer); session.flush()
    return create_requirement(session, Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
        required_quantity_kg=Decimal(quantity), delivery_window_start=date(2026, 9, 8), delivery_window_end=date(2026, 9, 15)))


def lot(session: Session, quantity: str, price: str = "100") -> ProductionLot:
    farmer = Farmer(name=f"Farmer {uuid4()}", parish="Manchester")
    session.add(farmer); session.flush()
    item = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 9, 8),
        harvest_end=date(2026, 9, 15), expected_quantity_kg=Decimal(quantity),
        available_quantity_kg=Decimal(quantity), reserved_quantity_kg=Decimal("0"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
        parish="Manchester", status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
    session.add(item); session.flush()
    session.add(LotCostInput(production_lot_id=item.id, farmgate_price_per_kg_jmd=Decimal(price),
        pickup_cost_jmd=0, handling_grading_cost_per_kg_jmd=0, packaging_cost_per_kg_jmd=0,
        transport_cost_jmd=0, expected_rejection_pct=0)); session.commit()
    return item


def concurrent(factory, functions):
    barrier = Barrier(len(functions))
    def run(fn):
        session = factory()
        try:
            barrier.wait()
            value = fn(session)
            session.commit()
            return ("ok", value)
        except Exception as exc:
            session.rollback()
            return ("error", exc)
        finally:
            session.close()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(run, functions))


def assert_inventory(factory):
    with factory() as session:
        assert not session.scalar(select(func.count()).select_from(ProductionLot).where(
            ProductionLot.reserved_quantity_kg > ProductionLot.available_quantity_kg))


def test_two_requirements_cannot_reserve_the_same_lot(pg_factory):
    with pg_factory() as s:
        first, second = requirement(s), requirement(s); lot(s, "100")
    results = concurrent(pg_factory, [lambda s: finalize_plan(s, first.id), lambda s: finalize_plan(s, second.id)])
    assert sorted(r[1].committed_quantity_kg for r in results if r[0] == "ok") == [Decimal("0"), Decimal("100")]
    assert_inventory(pg_factory)


def test_two_recoveries_activate_standby_once(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100", "10"); lot(s, "100", "20")
        finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("1"), landed_cost_weight=0))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop", auto_recover=False); s.commit()
    results = concurrent(pg_factory, [lambda s: continue_recovery(s, req.id, "recover-a"), lambda s: continue_recovery(s, req.id, "recover-b")])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s:
        assert s.scalar(select(func.sum(SupplyAllocation.quantity_kg)).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED)) == Decimal("100")
    assert_inventory(pg_factory)


def test_two_acceptances_cannot_use_replacement_twice(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100", "10"); lot(s, "100", "20")
        finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop", auto_recover=False); continue_recovery(s, req.id, "recover"); s.commit()
        solicited = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.SOLICITED))
    results = concurrent(pg_factory, [lambda s: accept(s, solicited.id, "accept-a"), lambda s: accept(s, solicited.id, "accept-b")])
    assert sum(result[0] == "ok" for result in results) == 1
    assert_inventory(pg_factory)


def test_two_dropout_commands_do_not_duplicate_loss(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100"); finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id))
    results = concurrent(pg_factory, [lambda s: dropout(s, allocation.id, "loss", "a", False), lambda s: dropout(s, allocation.id, "loss", "b", False)])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s:
        assert s.scalar(select(func.count()).select_from(DomainEvent).where(DomainEvent.event_type == "allocation.lost")) == 1
    assert_inventory(pg_factory)


def test_duplicate_in_progress_command_returns_same_result(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100"); finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id))
    results = concurrent(pg_factory, [lambda s: dropout(s, allocation.id, "loss", "same", False), lambda s: dropout(s, allocation.id, "loss", "same", False)])
    assert all(result[0] == "ok" for result in results) and results[0][1] == results[1][1]
    assert_inventory(pg_factory)


def test_two_receipts_cannot_exceed_allocation(pg_factory):
    with pg_factory() as s:
        req = requirement(s); item = lot(s, "100"); plan = finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        node = FulfilmentNode(name="Hub", node_type="HUB", parish="St. James"); s.add(node); s.commit()
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
    now = datetime.now(timezone.utc)
    results = concurrent(pg_factory, [lambda s: receive(s, allocation.id, node.id, Decimal("60"), now, "r", "r1"), lambda s: receive(s, allocation.id, node.id, Decimal("60"), now, "r", "r2")])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s: assert s.scalar(select(func.sum(ReceivedSublot.received_quantity_kg))) == Decimal("60")
    assert_inventory(pg_factory)


def test_two_shipments_cannot_consume_one_accepted_sublot(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100"); plan = finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        node = FulfilmentNode(name="Hub", node_type="HUB", parish="St. James"); s.add(node); s.commit()
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
        receipt = receive(s, allocation.id, node.id, Decimal("100"), datetime.now(timezone.utc), "r", "r"); grade(s, receipt["received_sublot_id"], Decimal("100"), Decimal("0"), Grade.A, None, "g", "g")
        first = Shipment(requirement_id=req.id, fulfilment_node_id=node.id, reference="S1"); second = Shipment(requirement_id=req.id, fulfilment_node_id=node.id, reference="S2"); s.add_all([first, second]); s.commit()
    payload = AddSublot(received_sublot_id=receipt["received_sublot_id"])
    results = concurrent(pg_factory, [lambda s: add_sublot(first.id, payload, "ship-a", s), lambda s: add_sublot(second.id, payload, "ship-b", s)])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s: assert s.scalar(select(func.count()).select_from(ShipmentSublot)) == 1
    assert_inventory(pg_factory)


def test_availability_change_cannot_invalidate_reservation(pg_factory, monkeypatch):
    with pg_factory() as s: req = requirement(s); item = lot(s, "100")
    planner_has_lock, updater_finished = Event(), Event()
    original = planner_module._choose_allocations
    def paused(*args, **kwargs):
        planner_has_lock.set(); updater_finished.wait(0.3); return original(*args, **kwargs)
    monkeypatch.setattr(planner_module, "_choose_allocations", paused)
    def plan(s): return finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    def update(s):
        planner_has_lock.wait(); row = s.scalar(select(ProductionLot).where(ProductionLot.id == item.id).with_for_update()); row.available_quantity_kg = Decimal("50"); s.flush(); updater_finished.set()
    results = concurrent(pg_factory, [plan, update])
    assert sum(result[0] == "error" and isinstance(result[1], IntegrityError) for result in results) == 1
    assert_inventory(pg_factory)


def test_recovery_and_new_requirement_compete_without_creating_supply(pg_factory):
    with pg_factory() as s:
        recovering, newcomer = requirement(s), requirement(s); lot(s, "100", "10"); discovery = lot(s, "100", "100")
        finalize_plan(s, recovering.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == recovering.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop", False); s.commit()
    concurrent(pg_factory, [lambda s: continue_recovery(s, recovering.id, "recover"), lambda s: finalize_plan(s, newcomer.id, PlannerConfig(standby_target_pct=Decimal("0")))])
    with pg_factory() as s:
        row = s.get(ProductionLot, discovery.id)
        used = s.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(SupplyAllocation.production_lot_id == discovery.id, SupplyAllocation.status.in_([AllocationStatus.COMMITTED, AllocationStatus.SOLICITED, AllocationStatus.STANDBY])))
        assert used <= row.available_quantity_kg
    assert_inventory(pg_factory)
