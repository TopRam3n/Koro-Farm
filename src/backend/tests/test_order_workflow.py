"""WP1 workflow: a coordinator creates a buyer, a supplier, a declared lot and an unfamiliar order,
edits within policy, and every step is persisted and attributable."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from two_orgs import add_member, as_user, ensure_roles, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app.assurance.domain.models import DomainEvent
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.supply.domain.models import ProductionLot


@pytest.fixture()
def org(factory):
    with factory() as session:
        ensure_roles(session)
        organization = Organization(id=uuid4(), name="Blue Mountain Exports", slug=f"bme-{uuid4().hex[:6]}")
        session.add(organization); session.flush()
        coordinator = add_member(session, organization.id, RoleCode.SUPPLY_COORDINATOR, "coordinator")
        colleague = add_member(session, organization.id, RoleCode.PROCUREMENT_MANAGER, "colleague")
        auditor = add_member(session, organization.id, RoleCode.AUDITOR, "auditor")
        session.commit()
        return {"org": organization.id, "coordinator": coordinator.id, "colleague": colleague.id, "auditor": auditor.id}


def _as(org, who="coordinator", key=None):
    return as_user(org[who], org["org"], key)


LOT = {"crop": "scotch bonnet", "harvest_start": "2026-11-20", "harvest_end": "2026-12-10",
       "expected_quantity_kg": "400", "available_quantity_kg": "350", "quality_grade_estimate": "A",
       "provenance_source": "phone call with farmer", "attestation_method": "verbal", "farmgate_price_per_kg_jmd": "620"}
ORDER = {"crop": "SCOTCH_BONNET", "grade": "A", "required_quantity_kg": "730", "delivery_window_start": "2026-12-01",
         "delivery_window_end": "2026-12-12", "product_form": "Fresh, whole", "origin": "St. Elizabeth, Jamaica",
         "destination": "Kingston processing plant", "delivery_terms": "Delivered to buyer dock", "currency": "JMD"}


def _setup(http, org):
    buyer = http.post("/buyers", headers=_as(org), json={"name": "Caribbean Sauce Co.", "buyer_type": "PROCESSOR", "destination": "Kingston"})
    assert buyer.status_code == 201, buyer.text
    farmer = http.post("/farmers", headers=_as(org), json={"name": "Marcia Ellis", "parish": "St. Elizabeth", "contact_phone": "876-555-0142"})
    assert farmer.status_code == 201, farmer.text
    lot = http.post("/production-lots", headers=_as(org), json={**LOT, "farmer_id": farmer.json()["id"]})
    assert lot.status_code == 201, lot.text
    order = http.post("/requirements", headers=_as(org), json={**ORDER, "buyer_id": buyer.json()["id"]})
    assert order.status_code == 201, order.text
    return buyer.json(), farmer.json(), lot.json(), order.json()


def test_coordinator_creates_unfamiliar_order_with_supply_and_a_colleague_sees_the_same(http, org, factory) -> None:
    buyer, farmer, lot, order = _setup(http, org)
    assert order["crop"] == "SCOTCH_BONNET" and order["required_quantity_kg"] in {"730", "730.000"}
    assert order["buyer_name"] == "Caribbean Sauce Co." and order["currency"] == "JMD" and order["quantity_unit"] == "kg"
    assert lot["capacity_verification"] == "DECLARED" and lot["availability_confidence"] == "LOW"
    assert lot["provenance_source"] == "phone call with farmer" and lot["crop"] == "SCOTCH_BONNET"
    # A second authenticated user of the same organization reads the persisted records.
    seen = http.get(f"/requirements/{order['id']}", headers=_as(org, "colleague")).json()
    assert seen["id"] == order["id"] and seen["destination"] == "Kingston processing plant"
    assert [b["id"] for b in http.get("/buyers", headers=_as(org, "colleague")).json()] == [buyer["id"]]
    assert lot["id"] in {l["id"] for l in http.get("/production-lots", headers=_as(org, "colleague")).json()}
    with factory() as session:
        events = session.scalars(select(DomainEvent).where(DomainEvent.organization_id == org["org"])).all()
        kinds = {e.event_type for e in events}
        assert {"buyer.created", "farmer.created", "production_lot.declared", "requirement.created"} <= kinds
        assert all(e.actor_id == str(org["coordinator"]) for e in events)


def test_validation_failures_are_reported_and_nothing_is_stored(http, org, factory) -> None:
    buyer, farmer, _, _ = _setup(http, org)
    bad = [
        ("/production-lots", {**LOT, "farmer_id": farmer["id"], "available_quantity_kg": "500"}),
        ("/production-lots", {key: value for key, value in {**LOT, "farmer_id": farmer["id"]}.items() if key != "provenance_source"}),
        ("/production-lots", {**LOT, "farmer_id": farmer["id"], "harvest_end": "2026-11-01"}),
        ("/requirements", {**ORDER, "buyer_id": buyer["id"], "quantity_unit": "lb"}),
        ("/requirements", {**ORDER, "buyer_id": buyer["id"], "required_quantity_kg": "0"}),
        ("/requirements", {**ORDER, "buyer_id": buyer["id"], "delivery_window_end": "2026-11-01"}),
        ("/requirements", {**ORDER, "buyer_id": str(uuid4())}),
    ]
    for path, body in bad:
        assert http.post(path, headers=_as(org), json=body).status_code in {404, 422}, (path, body)
    with factory() as session:
        assert session.query(ProductionLot).count() == 1 and session.query(Requirement).count() == 1


def test_order_edits_are_versioned_and_recorded(http, org) -> None:
    _, _, _, order = _setup(http, org)
    path = f"/requirements/{order['id']}"
    updated = http.patch(path, headers=_as(org), json={"expected_version": 1, "required_quantity_kg": "750", "notes": "Buyer confirmed by email"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2 and updated.json()["required_quantity_kg"] in {"750", "750.000"}
    stale = http.patch(path, headers=_as(org, "colleague"), json={"expected_version": 1, "required_quantity_kg": "760"})
    assert stale.status_code == 409
    history = http.get(f"{path}/history", headers=_as(org, "colleague")).json()["events"]
    assert [e["event_type"] for e in history] == ["requirement.created", "requirement.updated"]
    assert history[1]["payload"]["changes"]["required_quantity_kg"] == ["730.000", "750"] or \
        history[1]["payload"]["changes"]["required_quantity_kg"][1] == "750"
    assert history[1]["actor_id"] == str(org["coordinator"])


def test_cancelled_orders_cannot_be_edited(http, org) -> None:
    _, _, _, order = _setup(http, org)
    path = f"/requirements/{order['id']}"
    cancelled = http.post(f"{path}/cancel", headers=_as(org), json={"reason": "Buyer withdrew the tender"})
    assert cancelled.status_code == 200 and cancelled.json()["lifecycle_status"] == "CANCELLED"
    assert http.patch(path, headers=_as(org), json={"expected_version": cancelled.json()["version"], "notes": "x"}).status_code == 409
    assert http.post(f"{path}/cancel", headers=_as(org), json={"reason": "again"}).status_code == 409


def test_creates_are_idempotent_per_key(http, org, factory) -> None:
    body = {"name": "Negril Resorts", "buyer_type": "HOTEL", "destination": "Negril"}
    first = http.post("/buyers", headers=_as(org, key="buyer-once"), json=body)
    again = http.post("/buyers", headers=_as(org, key="buyer-once"), json=body)
    assert first.status_code == again.status_code == 201 and first.json()["id"] == again.json()["id"]
    with factory() as session:
        assert session.query(Buyer).filter(Buyer.organization_id == org["org"]).count() == 1
    assert http.post("/buyers", headers=_as(org), json=body).status_code == 409


def test_lot_reductions_below_reserved_supply_are_not_silently_applied(http, org, factory) -> None:
    _, _, lot, _ = _setup(http, org)
    with factory() as session:
        row = session.scalar(select(ProductionLot))
        row.reserved_quantity_kg = 200
        session.commit()
    response = http.patch(f"/production-lots/{lot['id']}", headers=_as(org), json={
        "expected_version": lot["version"], "available_quantity_kg": "120",
        "provenance_source": "farmer called", "attestation_method": "verbal"})
    assert response.status_code == 409


def test_read_only_roles_cannot_create(http, org) -> None:
    for path, body in [("/buyers", {"name": "X Ltd", "buyer_type": "HOTEL", "destination": "Y"}),
                       ("/farmers", {"name": "Z Farmer", "parish": "Clarendon"})]:
        assert http.post(path, headers=_as(org, "auditor"), json=body).status_code == 403
