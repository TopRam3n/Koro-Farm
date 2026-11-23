"""WP2: supplier capacity reports, exposure, deterministic exceptions, response deadlines and standby expiry."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from two_orgs import add_member, as_user, ensure_roles, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app import worker
from src.backend.app.assurance.domain.exceptions import ExceptionKind, ExceptionStatus, SupplyException
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.demand.domain.models import Requirement
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.supply.application.capacity import free_kg
from src.backend.app.supply.domain.capacity import CapacityReport
from src.backend.app.supply.domain.models import ProductionLot
from src.backend.app.supply.domain.planning_models import AllocationStatus, SupplyAllocation

RELAY = {"original_source": "phone call with farmer", "attestation_method": "verbal", "evidence_reference": "call log 77"}
ATTEST = {"attestation_method": "phone call with farmer"}
NEXT_MONTH = (date.today() + timedelta(days=30)).isoformat()
LATER = (date.today() + timedelta(days=40)).isoformat()


@pytest.fixture()
def org(factory, http):
    with factory() as session:
        ensure_roles(session)
        organization = Organization(id=uuid4(), name="Exception Exports", slug=f"exc-{uuid4().hex[:6]}")
        session.add(organization); session.flush()
        coordinator = add_member(session, organization.id, RoleCode.SUPPLY_COORDINATOR, "coordinator")
        auditor = add_member(session, organization.id, RoleCode.AUDITOR, "auditor")
        session.commit()
    ctx = {"org": organization.id, "coordinator": coordinator.id, "auditor": auditor.id}
    h = as_user(coordinator.id, organization.id)
    ctx["buyer"] = http.post("/buyers", headers=h, json={"name": "Sauce Works", "buyer_type": "PROCESSOR", "destination": "Kingston"}).json()
    farmers, lots = [], []
    for name in ("Ena Gordon", "Paul Reid"):
        farmer = http.post("/farmers", headers=h, json={"name": name, "parish": "St. Ann"}).json()
        lot = http.post("/production-lots", headers=h, json={
            "farmer_id": farmer["id"], "crop": "SCOTCH_BONNET", "harvest_start": date.today().isoformat(), "harvest_end": LATER,
            "expected_quantity_kg": "400", "available_quantity_kg": "300", "quality_grade_estimate": "A",
            "provenance_source": "field visit", "attestation_method": "coordinator observation", "farmgate_price_per_kg_jmd": "600"}).json()
        farmers.append(farmer); lots.append(lot)
    with factory() as session:
        farmer_user = add_member(session, organization.id, RoleCode.FARMER, "ena", farmer_id=UUID(farmers[0]["id"]))
        other_farmer = add_member(session, organization.id, RoleCode.FARMER, "paul", farmer_id=UUID(farmers[1]["id"]))
        session.commit()
    return {**ctx, "farmers": farmers, "lots": lots, "farmer_user": farmer_user.id, "other_farmer": other_farmer.id}


def H(org, who="coordinator", key=None):
    return as_user(org[who], org["org"], key)


def make_order(http, org, quantity: str, start: str = NEXT_MONTH, end: str = LATER) -> dict:
    response = http.post("/requirements", headers=H(org), json={"buyer_id": org["buyer"]["id"], "crop": "SCOTCH_BONNET", "grade": "A",
                                                                "required_quantity_kg": quantity, "delivery_window_start": start,
                                                                "delivery_window_end": end})
    assert response.status_code == 201, response.text
    return response.json()


def supply(http, org, order) -> dict:
    return http.get(f"/requirements/{order['id']}/assurance", headers=H(org)).json()


def commit_all(http, org, order, roles=("COMMITTED",), **solicit):
    assert http.post(f"/requirements/{order['id']}/plan", headers=H(org, key=f"plan-{order['id']}")).status_code == 201
    for allocation in supply(http, org, order)["allocations"]:
        if allocation["role"] not in roles:
            continue
        assert http.post(f"/allocations/{allocation['id']}/solicit", headers=H(org, key=f"s-{allocation['id']}"), json=solicit).status_code == 200
        body = {"decision": "ACCEPTED", **ATTEST}
        if allocation["role"] == "STANDBY":
            body["activation_conditions"] = "only to replace lost supply"
        assert http.post(f"/allocations/{allocation['id']}/responses", headers=H(org, key=f"a-{allocation['id']}"), json=body).status_code == 200
    return supply(http, org, order)


def report(http, org, lot_id, kg, who="coordinator", **extra):
    body = {"reported_capacity_kg": str(kg), **(RELAY if who == "coordinator" else {}), **extra}
    return http.post(f"/production-lots/{lot_id}/capacity-reports", headers=H(org, who), json=body)


def open_exceptions(factory, requirement_id=None, kind=None):
    with factory() as session:
        statement = select(SupplyException).where(SupplyException.status == ExceptionStatus.OPEN)
        if requirement_id:
            statement = statement.where(SupplyException.requirement_id == UUID(requirement_id))
        if kind:
            statement = statement.where(SupplyException.kind == kind)
        return session.scalars(statement).all()


# --- Capacity reports: who may report, and how it is recorded -----------------------------------------------

def test_farmer_reports_own_lot_only_and_coordinator_relay_needs_attestation(http, org, factory) -> None:
    own, other = org["lots"]
    farmer = report(http, org, own["id"], 250, who="farmer_user")
    assert farmer.status_code == 201, farmer.text
    assert farmer.json()["channel"] == "FARMER_PORTAL" and farmer.json()["verification_status"] == "SELF_REPORTED"
    assert report(http, org, other["id"], 100, who="farmer_user").status_code == 403
    bare = http.post(f"/production-lots/{other['id']}/capacity-reports", headers=H(org), json={"reported_capacity_kg": "100"})
    assert bare.status_code == 422
    relayed = report(http, org, other["id"], 280)
    assert relayed.status_code == 201
    assert relayed.json()["channel"] == "COORDINATOR_RELAYED" and relayed.json()["verification_status"] == "COORDINATOR_ATTESTED"
    assert report(http, org, other["id"], 100, who="auditor", **RELAY).status_code == 403
    assert report(http, org, other["id"], 999).status_code == 422  # above the declared harvest
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert report(http, org, other["id"], 100, effective_at=future).status_code == 422
    with factory() as session:
        rows = session.scalars(select(CapacityReport)).all()
        assert len(rows) == 2 and {r.recorded_by_user_id for r in rows} == {org["farmer_user"], org["coordinator"]}
        relay_row = next(r for r in rows if r.channel.value == "COORDINATOR_RELAYED")
        assert (relay_row.original_source, relay_row.attestation_method, relay_row.evidence_reference) == ("phone call with farmer", "verbal", "call log 77")


def test_report_event_and_outbox_message_are_committed_together(http, org, factory) -> None:
    response = report(http, org, org["lots"][0]["id"], 200)
    report_id = response.json()["capacity_report_id"]
    with factory() as session:
        event = session.scalar(select(DomainEvent).where(DomainEvent.event_type == "lot.capacity_reported"))
        assert event.payload["capacity_report_id"] == report_id and event.organization_id == org["org"]
        message = session.scalar(select(OutboxMessage).where(OutboxMessage.event_id == event.id))
        assert message.status == "PENDING"


# --- Exposure and exceptions -----------------------------------------------------------------------------------

def test_a_reduction_that_does_not_threaten_commitments_only_updates_availability(http, org, factory) -> None:
    order = make_order(http, org, "200")
    commit_all(http, org, order)
    lot_id = next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")["production_lot_id"]
    with factory() as session:
        committed = session.get(ProductionLot, UUID(lot_id)).reserved_quantity_kg
    assert report(http, org, lot_id, committed).status_code == 201
    worker.run_once(factory)
    assert open_exceptions(factory, order["id"]) == []
    state = supply(http, org, order)
    assert state["exposed_kg"] in ("0", "0.000") and state["supply_health"] == "COVERED"
    with factory() as session:  # planning availability: nothing more is free for new orders
        lot = session.get(ProductionLot, UUID(lot_id))
        assert free_kg(lot) == 0 and lot.reported_capacity_kg == committed


def test_exposure_opens_one_exception_preserves_the_commitment_and_resolves_on_restore(http, org, factory) -> None:
    order = make_order(http, org, "300")
    commit_all(http, org, order)
    commitment = next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")
    committed = Decimal(commitment["quantity_kg"])
    assert report(http, org, commitment["production_lot_id"], committed - Decimal("40")).status_code == 201
    worker.run_once(factory)
    exceptions = open_exceptions(factory, order["id"])
    assert len(exceptions) == 1 and exceptions[0].kind == ExceptionKind.CAPACITY_SHORTFALL
    assert exceptions[0].shortfall_kg == Decimal("40")
    state = supply(http, org, order)
    assert state["supply_health"] == "AT_RISK"
    assert Decimal(state["committed_quantity_kg"]) == committed  # the original commitment is preserved
    assert Decimal(state["currently_covered_kg"]) == committed - 40 and Decimal(state["exposed_kg"]) == 40
    row = next(a for a in state["allocations"] if a["id"] == commitment["id"])
    assert row["status"] == "COMMITTED" and Decimal(row["exposed_kg"]) == 40
    assert http.post(f"/exceptions/{exceptions[0].id}/resolve", headers=H(org), json={"resolution": "ignore"}).status_code == 409
    assert http.post(f"/exceptions/{exceptions[0].id}/acknowledge", headers=H(org)).status_code == 200

    assert report(http, org, commitment["production_lot_id"], committed).status_code == 201  # capacity restored
    worker.run_once(factory)
    assert open_exceptions(factory, order["id"]) == []
    assert supply(http, org, order)["supply_health"] == "COVERED"


def test_exposure_falls_on_the_most_recently_accepted_commitment(http, org, factory) -> None:
    lot_id = org["lots"][0]["id"]
    with factory() as session:  # one lot only, so both orders share it
        session.get(ProductionLot, UUID(org["lots"][1]["id"])).available_quantity_kg = Decimal("0")
        session.commit()
    first = make_order(http, org, "200")
    commit_all(http, org, first)
    second = make_order(http, org, "100")
    commit_all(http, org, second)
    assert report(http, org, lot_id, 250).status_code == 201
    worker.run_once(factory)
    assert open_exceptions(factory, first["id"]) == []
    later = open_exceptions(factory, second["id"])
    assert len(later) == 1 and later[0].shortfall_kg == Decimal("50")
    assert Decimal(supply(http, org, first)["exposed_kg"]) == 0


def test_duplicate_events_do_not_duplicate_exceptions(http, org, factory) -> None:
    order = make_order(http, org, "300")
    commit_all(http, org, order)
    commitment = next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")
    report(http, org, commitment["production_lot_id"], 100)
    worker.run_once(factory)
    with factory() as session:  # replay every message as if delivered again
        for message in session.scalars(select(OutboxMessage)):
            message.status, message.processed_at = "PENDING", None
        session.commit()
    worker.run_once(factory)
    worker.run_once(factory)
    assert len(open_exceptions(factory, order["id"])) == 1


def test_a_stale_report_is_kept_but_changes_nothing(http, org, factory) -> None:
    lot_id = org["lots"][0]["id"]
    assert report(http, org, lot_id, 280).status_code == 201
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    stale = report(http, org, lot_id, 10, effective_at=stale_time)
    assert stale.status_code == 201 and stale.json()["applied"] is False
    with factory() as session:
        lot = session.get(ProductionLot, UUID(lot_id))
        assert lot.reported_capacity_kg == Decimal("280")
        assert session.query(CapacityReport).count() == 2


def test_after_a_reduction_no_new_reservation_can_exceed_capacity(http, org, factory) -> None:
    order = make_order(http, org, "500")
    plan = http.post(f"/requirements/{order['id']}/plan", headers=H(org, key="p")).status_code
    assert plan == 201
    proposal = next(a for a in supply(http, org, order)["allocations"] if a["role"] == "COMMITTED")
    http.post(f"/allocations/{proposal['id']}/solicit", headers=H(org, key="s"), json={})
    assert report(http, org, proposal["production_lot_id"], 10).status_code == 201
    refused = http.post(f"/allocations/{proposal['id']}/responses", headers=H(org, key="a"), json={"decision": "ACCEPTED", **ATTEST})
    assert refused.status_code == 409
    lot = http.get(f"/production-lots/{proposal['production_lot_id']}", headers=H(org)).json()
    assert Decimal(lot["free_kg"]) >= 0 and Decimal(lot["reserved_quantity_kg"]) == 0


# --- Response deadlines, reminders and escalation ------------------------------------------------------------

def _solicited(factory, allocation_id):
    with factory() as session:
        return session.get(SupplyAllocation, UUID(allocation_id))


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def test_default_urgent_and_custom_deadlines(http, org, factory) -> None:
    normal = make_order(http, org, "100")
    http.post(f"/requirements/{normal['id']}/plan", headers=H(org, key="pn"))
    a = supply(http, org, normal)["allocations"][0]
    http.post(f"/allocations/{a['id']}/solicit", headers=H(org, key="sn"), json={})
    row = _solicited(factory, a["id"])
    assert abs((_aware(row.response_due_at) - _aware(row.solicited_at)) - timedelta(hours=24)) < timedelta(seconds=5)

    soon = make_order(http, org, "100", start=(date.today() + timedelta(days=1)).isoformat())
    http.post(f"/requirements/{soon['id']}/plan", headers=H(org, key="pu"))
    u = supply(http, org, soon)["allocations"][0]
    http.post(f"/allocations/{u['id']}/solicit", headers=H(org, key="su"), json={})
    row = _solicited(factory, u["id"])
    assert abs((_aware(row.response_due_at) - _aware(row.solicited_at)) - timedelta(hours=4)) < timedelta(seconds=5)

    custom = supply(http, org, normal)["allocations"][1]
    http.post(f"/allocations/{custom['id']}/solicit", headers=H(org, key="sc"), json={"respond_within_hours": 72})
    row = _solicited(factory, custom["id"])
    assert abs((_aware(row.response_due_at) - _aware(row.solicited_at)) - timedelta(hours=72)) < timedelta(seconds=5)
    new_due = (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()
    changed = http.patch(f"/allocations/{custom['id']}/deadline", headers=H(org), json={"respond_by": new_due, "reason": "farmer travelling"})
    assert changed.status_code == 200
    history = http.get(f"/requirements/{normal['id']}/history", headers=H(org)).json()["events"]
    change = next(e for e in history if e["event_type"] == "solicitation.deadline_changed")
    assert change["payload"]["reason"] == "farmer travelling" and change["actor_id"] == str(org["coordinator"])
    assert http.patch(f"/allocations/{custom['id']}/deadline", headers=H(org, "auditor"),
                      json={"respond_by": new_due, "reason": "x x x"}).status_code == 403


def test_silence_leads_to_reminder_then_expiry_and_an_overdue_exception(http, org, factory) -> None:
    order = make_order(http, org, "100")
    http.post(f"/requirements/{order['id']}/plan", headers=H(org, key="p"))
    a = supply(http, org, order)["allocations"][0]
    http.post(f"/allocations/{a['id']}/solicit", headers=H(org, key="s"), json={})
    asked = _aware(_solicited(factory, a["id"]).solicited_at)

    assert worker.run_timers(factory, asked + timedelta(hours=11))["reminders"] == 0  # before half-way
    assert worker.run_timers(factory, asked + timedelta(hours=13))["reminders"] == 1
    assert worker.run_timers(factory, asked + timedelta(hours=14))["reminders"] == 0  # once only
    assert _solicited(factory, a["id"]).status == AllocationStatus.SOLICITED  # silence is not an answer

    worker.run_timers(factory, asked + timedelta(hours=24, minutes=1))
    row = _solicited(factory, a["id"])
    assert row.status == AllocationStatus.EXPIRED and row.holds_reservation is False and row.consent_status.value == "NONE"
    overdue = open_exceptions(factory, order["id"], ExceptionKind.RESPONSE_OVERDUE)
    assert len(overdue) == 1
    late = http.post(f"/allocations/{a['id']}/responses", headers=H(org, key="late"), json={"decision": "ACCEPTED", **ATTEST})
    assert late.status_code == 409
    again = http.post(f"/allocations/{a['id']}/solicit", headers=H(org, key="again"), json={"respond_within_hours": 8})
    assert again.status_code == 200 and again.json()["status"] == "SOLICITED"
    worker.run_timers(factory, asked + timedelta(hours=25))
    assert len(open_exceptions(factory, order["id"], ExceptionKind.RESPONSE_OVERDUE)) == 1  # not duplicated


def test_a_late_response_is_refused_even_before_the_worker_runs(http, org, factory) -> None:
    order = make_order(http, org, "100")
    http.post(f"/requirements/{order['id']}/plan", headers=H(org, key="p"))
    a = supply(http, org, order)["allocations"][0]
    http.post(f"/allocations/{a['id']}/solicit", headers=H(org, key="s"), json={})
    with factory() as session:
        session.get(SupplyAllocation, UUID(a["id"])).response_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
    assert http.post(f"/allocations/{a['id']}/responses", headers=H(org, key="r"), json={"decision": "ACCEPTED", **ATTEST}).status_code == 409


# --- Standby expiry ----------------------------------------------------------------------------------------

def _authorize_standby(http, org, order, valid_until: str) -> dict:
    commit_all(http, org, order)
    standby = next(a for a in supply(http, org, order)["allocations"] if a["role"] == "STANDBY")
    http.post(f"/allocations/{standby['id']}/solicit", headers=H(org, key="sb"), json={})
    accepted = http.post(f"/allocations/{standby['id']}/responses", headers=H(org, key="sba"), json={
        "decision": "ACCEPTED", "activation_conditions": "only to replace lost supply", "valid_until": valid_until, **ATTEST})
    assert accepted.status_code == 200, accepted.text
    return standby


def test_expired_standby_is_released_and_flagged_without_an_exception_when_recovery_is_unaffected(http, org, factory) -> None:
    order = make_order(http, org, "200")
    standby = _authorize_standby(http, org, order, date.today().isoformat())
    worker.run_timers(factory, datetime.now(timezone.utc) + timedelta(days=1))
    row = _solicited(factory, standby["id"])
    assert row.status == AllocationStatus.EXPIRED and row.holds_reservation is False
    state = supply(http, org, order)
    assert Decimal(state["expired_standby_kg"]) == Decimal(standby["quantity_kg"])
    assert state["standby_quantity_kg"] in ("0", "0.000") and state["supply_health"] == "COVERED"  # commitments untouched
    assert open_exceptions(factory, order["id"]) == []
    events = [e["event_type"] for e in http.get(f"/requirements/{order['id']}/history", headers=H(org)).json()["events"]]
    assert "standby.expired" in events


def test_expired_standby_opens_an_exception_when_an_active_shortfall_needs_it(http, org, factory) -> None:
    order = make_order(http, org, "200")
    standby = _authorize_standby(http, org, order, date.today().isoformat())
    commitment = next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")
    report(http, org, commitment["production_lot_id"], Decimal(commitment["quantity_kg"]) - Decimal("30"))
    worker.run_once(factory)
    assert len(open_exceptions(factory, order["id"], ExceptionKind.CAPACITY_SHORTFALL)) == 1
    worker.run_timers(factory, datetime.now(timezone.utc) + timedelta(days=1))
    expired = open_exceptions(factory, order["id"], ExceptionKind.STANDBY_EXPIRED)
    assert len(expired) == 1 and expired[0].shortfall_kg == Decimal("30")


# --- Worker retry -----------------------------------------------------------------------------------------

def test_failing_handler_retries_then_dead_letters_without_partial_changes(http, org, factory, monkeypatch) -> None:
    order = make_order(http, org, "300")
    commit_all(http, org, order)
    commitment = next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")
    report(http, org, commitment["production_lot_id"], 100)

    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(worker, "reevaluate_lot", broken)
    clock = datetime.now(timezone.utc)
    for attempt in range(worker.MAX_ATTEMPTS):
        worker.run_once(factory, clock)
        clock += timedelta(minutes=5)  # past the backoff
    with factory() as session:
        message = session.scalar(select(OutboxMessage).where(OutboxMessage.topic == "lot.capacity_reported"))
        assert message.status == "DEAD" and message.attempts == worker.MAX_ATTEMPTS and "simulated failure" in message.last_error
    assert open_exceptions(factory, order["id"]) == []


def test_exceptions_are_visible_only_to_their_organization(http, org, factory) -> None:
    order = make_order(http, org, "300")
    commit_all(http, org, order)
    commitment = next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")
    report(http, org, commitment["production_lot_id"], 100)
    worker.run_once(factory)
    assert len(http.get("/exceptions", headers=H(org)).json()) == 1
    with factory() as session:
        other = Organization(id=uuid4(), name="Other Org", slug=f"other-{uuid4().hex[:6]}")
        session.add(other); session.flush()
        outsider = add_member(session, other.id, RoleCode.SUPPLY_COORDINATOR, "outsider")
        session.commit()
    assert http.get("/exceptions", headers=as_user(outsider.id, other.id)).json() == []
