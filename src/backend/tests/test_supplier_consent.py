"""Supplier consent is recorded, never inferred.

Planning proposes; a solicitation asks; only a recorded ACCEPTED response turns a proposal into committed
coverage (or authorized standby). Legacy planner-generated consent ids are never accepted as evidence.
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from two_orgs import add_member, as_user, ensure_roles, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app.assurance.application.recovery import dropout
from src.backend.app.assurance.domain.models import DomainEvent
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, ConsentStatus, SupplierConsent, SupplyAllocation,
)

ATTEST = {"attestation_method": "phone call with farmer", "evidence_reference": "call log 2026-11-02 10:14"}


@pytest.fixture()
def org(factory, http):
    with factory() as session:
        ensure_roles(session)
        organization = Organization(id=uuid4(), name="Pepper Exporters", slug=f"pepper-{uuid4().hex[:6]}")
        session.add(organization); session.flush()
        coordinator = add_member(session, organization.id, RoleCode.SUPPLY_COORDINATOR, "coordinator")
        session.commit()
    ctx = {"org": organization.id, "coordinator": coordinator.id}
    h = as_user(coordinator.id, organization.id)
    buyer = http.post("/buyers", headers=h, json={"name": "Sauce Works", "buyer_type": "PROCESSOR", "destination": "Kingston"}).json()
    farmers, lots = [], []
    for name, parish, qty in (("Marcia Ellis", "St. Elizabeth", "400"), ("Devon Brown", "Manchester", "400"), ("Andre Clarke", "Clarendon", "200")):
        farmer = http.post("/farmers", headers=h, json={"name": name, "parish": parish}).json()
        lot = http.post("/production-lots", headers=h, json={
            "farmer_id": farmer["id"], "crop": "SCOTCH_BONNET", "harvest_start": "2026-11-20", "harvest_end": "2026-12-10",
            "expected_quantity_kg": qty, "available_quantity_kg": qty, "quality_grade_estimate": "A",
            "provenance_source": "field visit", "attestation_method": "coordinator observation", "farmgate_price_per_kg_jmd": "600"}).json()
        farmers.append(farmer); lots.append(lot)
    order = http.post("/requirements", headers=h, json={
        "buyer_id": buyer["id"], "crop": "SCOTCH_BONNET", "grade": "A", "required_quantity_kg": "730",
        "delivery_window_start": "2026-12-01", "delivery_window_end": "2026-12-12"}).json()
    with factory() as session:
        farmer_user = add_member(session, organization.id, RoleCode.FARMER, "marcia", farmer_id=UUID(farmers[0]["id"]))
        other_farmer_user = add_member(session, organization.id, RoleCode.FARMER, "devon", farmer_id=UUID(farmers[1]["id"]))
        session.commit()
    return {**ctx, "buyer": buyer, "farmers": farmers, "lots": lots, "order": order,
            "farmer_user": farmer_user.id, "other_farmer_user": other_farmer_user.id}


def _h(org, who="coordinator", key=None):
    return as_user(org[who], org["org"], key)


def _assurance(http, org):
    return http.get(f"/requirements/{org['order']['id']}/assurance", headers=_h(org)).json()


def _plan(http, org):
    response = http.post(f"/requirements/{org['order']['id']}/plan", headers=_h(org, key="plan"))
    assert response.status_code == 201, response.text
    return _assurance(http, org)


def _lot(factory, lot_id):
    with factory() as session:
        return session.get(ProductionLot, UUID(str(lot_id)))


def _solicit(http, org, allocation_id):
    response = http.post(f"/allocations/{allocation_id}/solicit", headers=_h(org, key=f"sol-{allocation_id}"), json={"message": "Can you supply?"})
    assert response.status_code == 200, response.text


def test_planning_only_proposes_and_reserves_nothing(http, org, factory) -> None:
    assurance = _plan(http, org)
    assert assurance["committed_quantity_kg"] == "0" and assurance["standby_quantity_kg"] == "0"
    assert Decimal(assurance["proposed_quantity_kg"]) == Decimal("730")
    assert assurance["supply_health"] == "UNPLANNED"
    assert {a["status"] for a in assurance["allocations"]} == {"PROPOSED"}
    assert {a["consent_status"] for a in assurance["allocations"]} == {"NONE"}
    for lot in org["lots"]:
        assert _lot(factory, lot["id"]).reserved_quantity_kg == 0


def test_acceptance_requires_a_solicitation_and_an_attestation(http, org, factory) -> None:
    proposal = next(a for a in _plan(http, org)["allocations"] if a["role"] == "COMMITTED")
    path = f"/allocations/{proposal['id']}/responses"
    assert http.post(path, headers=_h(org, key="early"), json={"decision": "ACCEPTED", **ATTEST}).status_code == 409
    _solicit(http, org, proposal["id"])
    solicited = _assurance(http, org)
    assert solicited["committed_quantity_kg"] == "0" and Decimal(solicited["solicited_quantity_kg"]) > 0
    assert http.post(path, headers=_h(org, key="bare"), json={"decision": "ACCEPTED"}).status_code == 422
    accepted = http.post(path, headers=_h(org, key="ok"), json={"decision": "ACCEPTED", **ATTEST})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "COMMITTED" and accepted.json()["channel"] == "COORDINATOR_RELAYED"
    with factory() as session:
        consent = session.get(SupplierConsent, UUID(accepted.json()["consent_id"]))
        assert consent.decision.value == "ACCEPTED" and consent.attestation_method == "phone call with farmer"
        assert consent.evidence_reference == "call log 2026-11-02 10:14" and consent.recorded_by_user_id == org["coordinator"]
        allocation = session.get(SupplyAllocation, UUID(str(proposal["id"])))
        assert allocation.consent_status == ConsentStatus.RECORDED and allocation.consent_evidence_id == consent.id
        lot = session.get(ProductionLot, UUID(str(allocation.production_lot_id)))
        assert lot.reserved_quantity_kg == allocation.quantity_kg
        assert "supplier.accepted" in {e.event_type for e in session.scalars(select(DomainEvent).where(DomainEvent.aggregate_id == UUID(org["order"]["id"])))}
    assert Decimal(_assurance(http, org)["committed_quantity_kg"]) == Decimal(proposal["quantity_kg"])


def test_partial_acceptance_commits_and_reserves_only_what_was_agreed(http, org, factory) -> None:
    proposal = max((a for a in _plan(http, org)["allocations"] if a["role"] == "COMMITTED"),
                   key=lambda a: Decimal(a["quantity_kg"]))  # >= 200 kg, so a 150 kg partial acceptance is valid
    _solicit(http, org, proposal["id"])
    response = http.post(f"/allocations/{proposal['id']}/responses", headers=_h(org, key="part"),
                         json={"decision": "ACCEPTED", "accepted_quantity_kg": "150", **ATTEST})
    assert response.status_code == 200 and Decimal(response.json()["quantity_kg"]) == Decimal("150")
    assert _lot(factory, proposal["production_lot_id"]).reserved_quantity_kg == Decimal("150")


def test_standby_needs_activation_conditions_and_a_valid_expiry(http, org) -> None:
    standby = next(a for a in _plan(http, org)["allocations"] if a["role"] == "STANDBY")
    _solicit(http, org, standby["id"])
    path = f"/allocations/{standby['id']}/responses"
    assert http.post(path, headers=_h(org, key="s1"), json={"decision": "ACCEPTED", **ATTEST}).status_code == 409
    past = str(date.today() - timedelta(days=1))
    assert http.post(path, headers=_h(org, key="s2"), json={"decision": "ACCEPTED", "activation_conditions": "Only if a committed farmer drops out",
                                                           "valid_until": past, **ATTEST}).status_code == 409
    ok = http.post(path, headers=_h(org, key="s3"), json={"decision": "ACCEPTED", "activation_conditions": "Only if a committed farmer drops out",
                                                         "valid_until": "2026-12-12", **ATTEST})
    assert ok.status_code == 200 and ok.json()["status"] == "STANDBY"
    row = next(a for a in _assurance(http, org)["allocations"] if a["id"] == standby["id"])
    assert row["consent_status"] == "RECORDED" and row["activation_conditions"] == "Only if a committed farmer drops out"
    assert row["authorization_valid_until"] == "2026-12-12"


def test_decline_and_withdraw_leave_no_reservation(http, org, factory) -> None:
    allocations = [a for a in _plan(http, org)["allocations"] if a["role"] == "COMMITTED"]
    first, second = allocations[0], allocations[1]
    _solicit(http, org, first["id"])
    declined = http.post(f"/allocations/{first['id']}/responses", headers=_h(org, key="d"), json={"decision": "DECLINED", **ATTEST})
    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED"
    withdrawn = http.post(f"/allocations/{second['id']}/withdraw", headers=_h(org, key="w"), json={"reason": "Buyer reduced volume"})
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "WITHDRAWN"
    for allocation in (first, second):
        assert _lot(factory, allocation["production_lot_id"]).reserved_quantity_kg == 0
    with factory() as session:
        decisions = [c.decision.value for c in session.scalars(select(SupplierConsent).where(SupplierConsent.allocation_id == UUID(first["id"])))]
        assert decisions == ["DECLINED"]


def test_farmers_answer_only_their_own_requests_and_cannot_solicit(http, org) -> None:
    allocations = _plan(http, org)["allocations"]
    lot_owner = {lot["id"]: farmer["id"] for lot, farmer in zip(org["lots"], org["farmers"])}
    mine = next(a for a in allocations if a["role"] == "COMMITTED" and lot_owner[a["production_lot_id"]] == org["farmers"][0]["id"])
    theirs = next(a for a in allocations if a["role"] == "COMMITTED" and lot_owner[a["production_lot_id"]] == org["farmers"][1]["id"])
    assert http.post(f"/allocations/{mine['id']}/solicit", headers=_h(org, "farmer_user", "f-sol"), json={}).status_code == 403
    _solicit(http, org, mine["id"]); _solicit(http, org, theirs["id"])
    inbox = http.get("/allocations/solicitations/mine", headers=_h(org, "farmer_user")).json()
    assert [row["allocation_id"] for row in inbox] == [mine["id"]]
    assert http.post(f"/allocations/{theirs['id']}/responses", headers=_h(org, "farmer_user", "f-other"),
                     json={"decision": "ACCEPTED", "attestation_method": "farmer portal"}).status_code == 403
    own = http.post(f"/allocations/{mine['id']}/responses", headers=_h(org, "farmer_user", "f-own"),
                    json={"decision": "ACCEPTED", "attestation_method": "farmer portal"})
    assert own.status_code == 200 and own.json()["channel"] == "FARMER_PORTAL"


def test_acceptance_is_refused_when_the_stock_has_gone_elsewhere(http, org, factory) -> None:
    proposal = next(a for a in _plan(http, org)["allocations"] if a["role"] == "COMMITTED")
    _solicit(http, org, proposal["id"])
    with factory() as session:  # another order's accepted commitment consumed this lot meanwhile
        lot = session.get(ProductionLot, UUID(str(proposal["production_lot_id"])))
        lot.reserved_quantity_kg = lot.available_quantity_kg
        session.commit()
    response = http.post(f"/allocations/{proposal['id']}/responses", headers=_h(org, key="stale"), json={"decision": "ACCEPTED", **ATTEST})
    assert response.status_code == 409 and "no longer has" in response.json()["detail"]
    row = next(a for a in _assurance(http, org)["allocations"] if a["id"] == proposal["id"])
    assert row["status"] == "SOLICITED" and row["consent_status"] == "NONE"


def test_legacy_consent_ids_are_not_evidence(http, org, factory) -> None:
    """Rows written by the old planner (random consent id) are kept but never counted or activated."""
    allocations = _plan(http, org)["allocations"]
    committed = [a for a in allocations if a["role"] == "COMMITTED"]
    standby = next(a for a in allocations if a["role"] == "STANDBY")
    with factory() as session:  # reproduce the pre-R1 shape exactly
        for row in committed + [standby]:
            allocation = session.get(SupplyAllocation, UUID(str(row["id"])))
            allocation.status = AllocationStatus.COMMITTED if allocation.role == AllocationRole.COMMITTED else AllocationStatus.STANDBY
            allocation.consent_evidence_id, allocation.consent_status, allocation.holds_reservation = uuid4(), ConsentStatus.UNSUPPORTED_LEGACY, True
            lot = session.get(ProductionLot, UUID(str(allocation.production_lot_id)))
            lot.reserved_quantity_kg += allocation.quantity_kg
        session.commit()
    assurance = _assurance(http, org)
    assert assurance["committed_quantity_kg"] == "0" and assurance["standby_quantity_kg"] == "0"
    assert Decimal(assurance["unsupported_legacy_kg"]) > 0
    with factory() as session:
        dropout(session, UUID(committed[0]["id"]), "legacy loss", "legacy-drop", auto_recover=True)
        session.commit()
        activated = session.scalars(select(SupplyAllocation).where(
            SupplyAllocation.requirement_id == UUID(org["order"]["id"]), SupplyAllocation.status == AllocationStatus.ACTIVATED)).all()
        assert activated == []  # the legacy standby was not treated as authorized
