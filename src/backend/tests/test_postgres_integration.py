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

from src.backend.app.agents.application.approvals import decide
from src.backend.app.agents.application.decision import DeterministicDecider
from src.backend.app.agents.application.orchestrator import advance_task
from src.backend.app.agents.domain.models import ProposalStatus, RecoveryExecution, RecoveryProposal, RecoveryTask, TaskStatus
from src.backend.app.assurance.application.recovery import dropout
from consent_support import TEST_ACTOR, plan_and_confirm, accept
from recovery_support import agent_round, approve, member, pending
from src.backend.app.supply.application.commitments import CommitmentError, solicit
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage, RecoveryRun
from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.application.services import grade, receive
from src.backend.app.fulfilment.domain.models import FulfilmentNode, ReceivedSublot
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.identity.domain.models import DEFAULT_ORGANIZATION_ID, Organization
from src.backend.app.infrastructure.database.seed import SEED_CONTEXT
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
    # Rows created without an explicit organization default to DEFAULT_ORGANIZATION_ID (migration 0011).
    with factory() as setup:
        setup.add(Organization(id=DEFAULT_ORGANIZATION_ID, name="Default test organization", slug="default-test"))
        setup.commit()
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


def advance_once(session: Session, task_id) -> str:
    """One worker's attempt at a task, exactly as advance_due does it (row lock, SKIP LOCKED)."""
    task = session.scalar(select(RecoveryTask).where(RecoveryTask.id == task_id).with_for_update(skip_locked=True))
    if task is None:
        return "skipped: another worker holds the task"
    advance_task(session, task, DeterministicDecider(), datetime.now(timezone.utc))
    return task.status.value


def approved_task(factory, req_id, *roles):
    """Plan the order's recovery and record approvals, leaving execution to whichever worker runs next."""
    from src.backend.app.identity.domain.permissions import RoleCode
    with factory() as s:
        agent_round(s)
        actors = [member(s, role) for role in (roles or (RoleCode.SUPPLY_COORDINATOR,))]
        approve(s, req_id, *actors, run=False)
        return s.scalar(select(RecoveryTask.id).where(RecoveryTask.requirement_id == req_id))


def assert_inventory(factory):
    with factory() as session:
        assert not session.scalar(select(func.count()).select_from(ProductionLot).where(
            ProductionLot.reserved_quantity_kg > ProductionLot.available_quantity_kg))


def test_two_requirements_cannot_reserve_the_same_lot(pg_factory):
    """Two orders race for one 100 kg lot, each planning and recording its supplier's acceptance.

    Planning reserves nothing, so either interleaving is legitimate: the later order may find no free
    stock to propose, or both may be proposed the lot and the later acceptance is refused as stale.
    The invariant checked is the same either way: exactly 100 kg committed, held by one order.
    """
    with pg_factory() as s:
        first, second = requirement(s), requirement(s); item = lot(s, "100")
    results = concurrent(pg_factory, [lambda s: plan_and_confirm(s, first.id), lambda s: plan_and_confirm(s, second.id)])
    assert all(isinstance(r[1], CommitmentError) for r in results if r[0] == "error"), results
    with pg_factory() as s:
        committed = s.scalars(select(SupplyAllocation).where(SupplyAllocation.status == AllocationStatus.COMMITTED)).all()
        assert sum((a.quantity_kg for a in committed), Decimal("0")) == Decimal("100")
        assert len({a.requirement_id for a in committed}) == 1
        assert all(a.consent_status.value == "RECORDED" for a in committed)
        assert s.get(ProductionLot, item.id).reserved_quantity_kg == Decimal("100")
    assert_inventory(pg_factory)


def test_two_workers_executing_one_approved_proposal_activate_standby_once(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100", "10"); lot(s, "100", "10")
        plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("1"), landed_cost_weight=0))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop"); s.commit()
    task_id = approved_task(pg_factory, req.id)
    results = concurrent(pg_factory, [lambda s: advance_once(s, task_id), lambda s: advance_once(s, task_id)])
    assert all(result[0] == "ok" for result in results), results
    with pg_factory() as s:
        assert s.scalar(select(func.sum(SupplyAllocation.quantity_kg)).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED)) == Decimal("100")
        assert s.scalar(select(func.count()).select_from(RecoveryExecution)) == 1
        assert s.scalar(select(func.count()).select_from(DomainEvent).where(DomainEvent.event_type == "allocation.standby_activated")) == 1
    assert_inventory(pg_factory)


def test_two_acceptances_cannot_use_replacement_twice(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100", "10"); lot(s, "100", "10")
        plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop"); s.commit()
    task_id = approved_task(pg_factory, req.id)
    with pg_factory() as s:
        advance_once(s, task_id); s.commit()
        solicited = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.SOLICITED))
    results = concurrent(pg_factory, [lambda s: accept(s, solicited.id, "accept-a"), lambda s: accept(s, solicited.id, "accept-b")])
    assert sum(result[0] == "ok" for result in results) == 1
    assert_inventory(pg_factory)


def test_stock_taken_between_approval_and_execution_is_refused_not_over_reserved(pg_factory):
    """The approved request's lot is consumed by another order before the gateway runs: the gateway refuses the
    stale approval (nothing applied), and the task re-plans from current facts."""
    with pg_factory() as s:
        req, rival = requirement(s), requirement(s); lot(s, "100", "10"); spare = lot(s, "100", "10")
        plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop"); s.commit()
    task_id = approved_task(pg_factory, req.id)
    # The rival order takes the spare lot while the approval waits for execution, racing the gateway.
    results = concurrent(pg_factory, [lambda s: advance_once(s, task_id),
                                      lambda s: plan_and_confirm(s, rival.id, PlannerConfig(standby_target_pct=Decimal("0")))])
    assert all(result[0] == "ok" for result in results), results
    with pg_factory() as s:
        proposal = s.scalar(select(RecoveryProposal).where(RecoveryProposal.version == 1))
        rival_committed = s.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
            SupplyAllocation.requirement_id == rival.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        if proposal.status == ProposalStatus.STALE:  # the rival won: nothing was requested from the spare lot
            assert rival_committed == Decimal("100")
            assert s.scalar(select(func.count()).select_from(RecoveryExecution)) == 0
            assert s.get(RecoveryTask, task_id).status == TaskStatus.ESCALATED
        else:  # the gateway won: a request was issued; the rival's acceptance and that request cannot both hold stock
            assert proposal.status == ProposalStatus.EXECUTED
        assert s.get(ProductionLot, spare.id).reserved_quantity_kg <= Decimal("100")
    assert_inventory(pg_factory)


def test_two_dropout_commands_do_not_duplicate_loss(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100"); plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id))
    results = concurrent(pg_factory, [lambda s: dropout(s, allocation.id, "loss", "a"), lambda s: dropout(s, allocation.id, "loss", "b")])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s:
        assert s.scalar(select(func.count()).select_from(DomainEvent).where(DomainEvent.event_type == "allocation.lost")) == 1
    assert_inventory(pg_factory)


def test_duplicate_in_progress_command_returns_same_result(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100"); plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id))
    results = concurrent(pg_factory, [lambda s: dropout(s, allocation.id, "loss", "same"), lambda s: dropout(s, allocation.id, "loss", "same")])
    assert all(result[0] == "ok" for result in results) and results[0][1] == results[1][1]
    assert_inventory(pg_factory)


def test_two_receipts_cannot_exceed_allocation(pg_factory):
    with pg_factory() as s:
        req = requirement(s); item = lot(s, "100"); plan = plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        node = FulfilmentNode(name="Hub", node_type="HUB", parish="St. James"); s.add(node); s.commit()
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
    now = datetime.now(timezone.utc)
    results = concurrent(pg_factory, [lambda s: receive(s, allocation.id, node.id, Decimal("60"), now, "r", "r1"), lambda s: receive(s, allocation.id, node.id, Decimal("60"), now, "r", "r2")])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s: assert s.scalar(select(func.sum(ReceivedSublot.received_quantity_kg))) == Decimal("60")
    assert_inventory(pg_factory)


def test_two_shipments_cannot_consume_one_accepted_sublot(pg_factory):
    with pg_factory() as s:
        req = requirement(s); lot(s, "100"); plan = plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        node = FulfilmentNode(name="Hub", node_type="HUB", parish="St. James"); s.add(node); s.commit()
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
        receipt = receive(s, allocation.id, node.id, Decimal("100"), datetime.now(timezone.utc), "r", "r"); grade(s, receipt["received_sublot_id"], Decimal("100"), Decimal("0"), Grade.A, None, "g", "g")
        first = Shipment(requirement_id=req.id, fulfilment_node_id=node.id, reference="S1"); second = Shipment(requirement_id=req.id, fulfilment_node_id=node.id, reference="S2"); s.add_all([first, second]); s.commit()
    payload = AddSublot(received_sublot_id=receipt["received_sublot_id"])
    results = concurrent(pg_factory, [lambda s: add_sublot(first.id, payload, "ship-a", s, SEED_CONTEXT), lambda s: add_sublot(second.id, payload, "ship-b", s, SEED_CONTEXT)])
    assert sum(result[0] == "ok" for result in results) == 1
    with pg_factory() as s: assert s.scalar(select(func.count()).select_from(ShipmentSublot)) == 1
    assert_inventory(pg_factory)


def test_availability_change_cannot_invalidate_reservation(pg_factory):
    """Planning only proposes; stock is reserved when the supplier's acceptance is recorded.

    A supplier acceptance (reserves 100 kg) races a capacity edit (available -> 50 kg) on the same lot.
    Whichever wins, the other must fail: the edit with an IntegrityError (reserved <= available), or the
    acceptance with a CommitmentError (not enough free stock). Never both succeed.
    """
    with pg_factory() as s:
        req = requirement(s); item = lot(s, "100")
        finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
        proposal = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id))
        solicit(s, TEST_ACTOR, proposal.id, None, "solicit-race"); s.commit()
    def accept_it(s): return accept(s, proposal.id, "accept-race")
    def shrink(s):
        row = s.scalar(select(ProductionLot).where(ProductionLot.id == item.id).with_for_update())
        row.available_quantity_kg = Decimal("50"); s.flush()
    results = concurrent(pg_factory, [accept_it, shrink])
    assert sum(result[0] == "ok" for result in results) == 1, results
    assert all(isinstance(result[1], (IntegrityError, CommitmentError)) for result in results if result[0] == "error")
    assert_inventory(pg_factory)


def test_recovery_and_new_requirement_compete_without_creating_supply(pg_factory):
    with pg_factory() as s:
        recovering, newcomer = requirement(s), requirement(s); lot(s, "100", "10"); discovery = lot(s, "100", "100")
        plan_and_confirm(s, recovering.id, PlannerConfig(standby_target_pct=Decimal("0")))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == recovering.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop"); s.commit()
    task_id = approved_task(pg_factory, recovering.id)
    concurrent(pg_factory, [lambda s: advance_once(s, task_id), lambda s: plan_and_confirm(s, newcomer.id, PlannerConfig(standby_target_pct=Decimal("0")))])
    with pg_factory() as s:
        row = s.get(ProductionLot, discovery.id)
        used = s.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(SupplyAllocation.production_lot_id == discovery.id, SupplyAllocation.status.in_([AllocationStatus.COMMITTED, AllocationStatus.SOLICITED, AllocationStatus.STANDBY])))
        assert used <= row.available_quantity_kg
    assert_inventory(pg_factory)


def test_two_orders_accepting_against_the_same_lot_cannot_over_reserve(pg_factory):
    """Planning reserves nothing, so two orders may both be proposed the same 100 kg lot.

    When both suppliers' acceptances race, exactly one reserves the stock; the other is refused as stale.
    """
    with pg_factory() as s:
        first, second = requirement(s), requirement(s); item = lot(s, "100")
        proposals = []
        for order in (first, second):
            finalize_plan(s, order.id, PlannerConfig(standby_target_pct=Decimal("0")))
            proposal = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == order.id))
            solicit(s, TEST_ACTOR, proposal.id, None, f"solicit-{proposal.id}")
            proposals.append(proposal.id)
        s.commit()
    results = concurrent(pg_factory, [lambda s: accept(s, proposals[0], "race-1"), lambda s: accept(s, proposals[1], "race-2")])
    assert sum(result[0] == "ok" for result in results) == 1, results
    assert all(isinstance(result[1], CommitmentError) for result in results if result[0] == "error")
    with pg_factory() as s:
        assert s.get(ProductionLot, item.id).reserved_quantity_kg == Decimal("100")
        committed = s.scalars(select(SupplyAllocation).where(SupplyAllocation.status == AllocationStatus.COMMITTED)).all()
        assert len(committed) == 1 and committed[0].consent_status.value == "RECORDED"
    assert_inventory(pg_factory)


RELAYED = dict(effective_at=None, original_source="phone call with farmer", attestation_method="verbal", evidence_reference=None)


def _solicited_proposal(s, quantity="100"):
    req = requirement(s, quantity); item = lot(s, quantity)
    finalize_plan(s, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    proposal = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id))
    solicit(s, TEST_ACTOR, proposal.id, None, f"solicit-{proposal.id}"); s.commit()
    return req, item, proposal


def test_capacity_report_and_acceptance_serialize_without_over_reservation(pg_factory):
    """Either the acceptance lands first (then the report exposes it) or the report lands first (then the
    acceptance is refused). Never over-reserved, never negative free stock, never an integrity failure."""
    from src.backend.app.supply.application.capacity import free_kg, lot_exposure, record_capacity_report
    with pg_factory() as s:
        req, item, proposal = _solicited_proposal(s)
    results = concurrent(pg_factory, [
        lambda s: accept(s, proposal.id, "race-accept"),
        lambda s: record_capacity_report(s, TEST_ACTOR, item.id, Decimal("40"), key="race-report", **RELAYED),
    ])
    assert not any(isinstance(r[1], IntegrityError) for r in results if r[0] == "error"), results
    accepted, reported = results[0][0] == "ok", results[1][0] == "ok"
    assert reported
    with pg_factory() as s:
        row = s.get(ProductionLot, item.id)
        assert row.reported_capacity_kg == Decimal("40") and free_kg(row) >= 0
        if accepted:  # acceptance won the lock: the commitment stands and is reported as exposed
            assert row.reserved_quantity_kg == Decimal("100")
            assert lot_exposure(s, row).exposed_kg == Decimal("60")
        else:         # the report won: the acceptance was refused as stale
            assert isinstance(results[0][1], CommitmentError) and row.reserved_quantity_kg == 0
    assert_inventory(pg_factory)


def test_concurrent_workers_open_exactly_one_exception(pg_factory):
    from src.backend.app import worker
    from src.backend.app.assurance.domain.exceptions import SupplyException
    from src.backend.app.supply.application.capacity import record_capacity_report
    with pg_factory() as s:
        req, item, proposal = _solicited_proposal(s)
        accept(s, proposal.id, "accept-1"); s.commit()
        record_capacity_report(s, TEST_ACTOR, item.id, Decimal("30"), key="report-1", **RELAYED); s.commit()
        record_capacity_report(s, TEST_ACTOR, item.id, Decimal("20"), key="report-2", **RELAYED); s.commit()
    concurrent(pg_factory, [lambda s: worker.run_once(pg_factory), lambda s: worker.run_once(pg_factory),
                            lambda s: worker.run_once(pg_factory)])
    with pg_factory() as s:
        rows = s.scalars(select(SupplyException).where(SupplyException.requirement_id == req.id)).all()
        assert len(rows) == 1 and rows[0].shortfall_kg == Decimal("80")
        assert s.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.status != "PROCESSED")) == 0
        # Three concurrent workers saw the exception: one recovery task, one proposal.
        assert s.scalar(select(func.count()).select_from(RecoveryTask).where(RecoveryTask.requirement_id == req.id)) == 1
        assert s.scalar(select(func.count()).select_from(RecoveryProposal).where(RecoveryProposal.requirement_id == req.id)) <= 1


def test_concurrent_capacity_reports_on_one_lot_both_recorded_and_consistent(pg_factory):
    from src.backend.app.supply.application.capacity import record_capacity_report
    from src.backend.app.supply.domain.capacity import CapacityReport
    with pg_factory() as s:
        req, item, proposal = _solicited_proposal(s)
    results = concurrent(pg_factory, [
        lambda s: record_capacity_report(s, TEST_ACTOR, item.id, Decimal("70"), key="r-a", **RELAYED),
        lambda s: record_capacity_report(s, TEST_ACTOR, item.id, Decimal("90"), key="r-b", **RELAYED),
    ])
    assert all(r[0] == "ok" for r in results), results
    with pg_factory() as s:
        reports = s.scalars(select(CapacityReport).where(CapacityReport.production_lot_id == item.id)).all()
        assert len(reports) == 2
        applied = [r for r in reports if r.applied]
        assert s.get(ProductionLot, item.id).reported_capacity_kg in {r.reported_capacity_kg for r in applied}
    assert_inventory(pg_factory)


class SlowExternalDecider:
    """An external decider stand-in: counts calls and takes long enough for two workers to overlap."""
    mode, external, provider, model = "model", True, "scripted", "scripted-model"

    def __init__(self):
        from types import SimpleNamespace
        self.config = SimpleNamespace(timeout=5.0, profile=SimpleNamespace(structured=("json_schema",)))
        self.calls = 0

    def decide(self, context):
        import time
        self.calls += 1
        time.sleep(0.5)
        decision = DeterministicDecider().decide(context)
        decision.mode, decision.model = "model", self.model
        return decision


def test_two_workers_racing_for_one_task_make_one_model_call_and_one_proposal(pg_factory):
    from src.backend.app.agents.application.orchestrator import advance_due
    with pg_factory() as s:
        req = requirement(s); lot(s, "100", "10"); lot(s, "100", "10")
        plan_and_confirm(s, req.id, PlannerConfig(standby_target_pct=Decimal("1"), landed_cost_weight=0))
        allocation = s.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == req.id, SupplyAllocation.status == AllocationStatus.COMMITTED))
        dropout(s, allocation.id, "loss", "drop"); s.commit()
    from src.backend.app import worker
    while worker.process_next_message(pg_factory):  # turn the exception into a task, without advancing it
        pass
    decider = SlowExternalDecider()
    barrier = Barrier(2)

    def race(_session):
        barrier.wait()
        return advance_due(pg_factory, decider=decider)

    results = concurrent(pg_factory, [race, race])
    assert all(result[0] == "ok" for result in results), results
    assert decider.calls == 1  # the second worker skipped the locked or leased task
    with pg_factory() as s:
        assert s.scalar(select(func.count()).select_from(RecoveryProposal)) == 1
        assert s.scalar(select(RecoveryTask)).planning_lease_id is None
