"""Marketplace fulfilment API: accepted offer -> receipt -> exact inspection.

Run: python3 -m pytest tests/test_marketplace_fulfilment.py -q
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.domain.common import AvailabilityConfidence, Crop, Grade
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.models import Organization
from app.identity.domain.permissions import ROLE_PERMISSIONS, RoleCode
from app.main import app
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.marketplace.fulfilment.models import MarketplaceReceipt
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus

ORG_A = UUID("00000000-0000-0000-0000-000000000900")
ORG_B = UUID("00000000-0000-0000-0000-000000000901")


def as_role(role, org=ORG_A, buyer_id=None, farmer_id=None):
    app.dependency_overrides[get_authorization_context] = lambda: AuthorizationContext(
        user_id=uuid4(), organization_id=org, membership_id=uuid4(),
        role=role, permissions=ROLE_PERMISSIONS[role], buyer_id=buyer_id, farmer_id=farmer_id,
    )


def seeded(session):
    session.add_all([Organization(id=ORG_A, name="Org A", slug="fulfilment-a"),
                     Organization(id=ORG_B, name="Org B", slug="fulfilment-b")])
    buyer_a = Buyer(organization_id=ORG_A, name="Bath Fountain Hotel", buyer_type="HOTEL", destination="Bath")
    buyer_a2 = Buyer(organization_id=ORG_A, name="Another Hotel", buyer_type="HOTEL", destination="Kingston")
    buyer_b = Buyer(organization_id=ORG_B, name="Other Hotel", buyer_type="HOTEL", destination="Montego Bay")
    farmer_a = Farmer(organization_id=ORG_A, name="St Thomas Grower", parish="St Thomas")
    farmer_b = Farmer(organization_id=ORG_B, name="Other Grower", parish="Clarendon")
    session.add_all([buyer_a, buyer_a2, buyer_b, farmer_a, farmer_b])
    session.flush()
    begin = date.today() + timedelta(days=7)
    end = begin + timedelta(days=5)
    req_a = Requirement(buyer_id=buyer_a.id, crop=Crop.GINGER, grade=Grade.A,
                        required_quantity_kg=Decimal("500"), delivery_window_start=begin,
                        delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    req_other = Requirement(buyer_id=buyer_a2.id, crop=Crop.GINGER, grade=Grade.A,
                            required_quantity_kg=Decimal("50"), delivery_window_start=begin,
                            delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    req_b = Requirement(buyer_id=buyer_b.id, crop=Crop.GINGER, grade=Grade.A,
                        required_quantity_kg=Decimal("1000"), delivery_window_start=begin,
                        delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    session.add_all([req_a, req_other, req_b])
    session.flush()
    lot = ProductionLot(farmer_id=farmer_a.id, crop=Crop.GINGER, harvest_start=begin, harvest_end=end,
                        expected_quantity_kg=Decimal("700"), available_quantity_kg=Decimal("700"),
                        reserved_quantity_kg=Decimal("0"), quality_grade_estimate=Grade.A,
                        availability_confidence=AvailabilityConfidence.HIGH, parish=farmer_a.parish,
                        status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
    session.add(lot); session.flush()
    offer = FarmerOffer(organization_id=ORG_A, requirement_id=req_a.id, farmer_id=farmer_a.id,
                        production_lot_id=lot.id, quantity_kg=Decimal("300"), status=OfferStatus.PENDING)
    session.add(offer); session.commit()
    return buyer_a, buyer_a2, buyer_b, farmer_a, req_a, offer


def create_node(client):
    as_role(RoleCode.ORGANIZATION_ADMIN)
    response = client.post("/marketplace/fulfilment/nodes", json={
        "name": "Kingston Collection Depot", "node_type": "WAREHOUSE", "parish": "Kingston",
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def accept(client, offer, buyer):
    as_role(RoleCode.BUYER, buyer_id=buyer.id)
    response = client.post(f"/marketplace/requests/offers/{offer.id}/accept")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACCEPTED"


def record_receipt(client, offer, node_id, amount="200", key="receipt-1", org=ORG_A):
    as_role(RoleCode.WAREHOUSE_OPERATOR, org=org)
    return client.post(f"/marketplace/fulfilment/offers/{offer.id}/receipts",
                       headers={"Idempotency-Key": key}, json={
                           "fulfilment_node_id": node_id, "received_quantity_kg": amount,
                           "receipt_evidence_reference": "DOCKET-2026-001",
                       })


def inspect(client, receipt_id, accepted="180", rejected="20", key="inspect-1", grade="A", reason="Bruising"):
    as_role(RoleCode.WAREHOUSE_OPERATOR)
    return client.post(f"/marketplace/fulfilment/receipts/{receipt_id}/inspect",
                       headers={"Idempotency-Key": key}, json={
                           "accepted_quantity_kg": accepted, "rejected_quantity_kg": rejected,
                           "assigned_grade": grade, "rejection_reason": reason,
                           "inspection_evidence_reference": "CHECK-2026-001",
                       })


def test_end_to_end_offer_receipt_inspection_and_idempotency(client, session):
    buyer, _, _, farmer, request, offer = seeded(session)
    node_id = create_node(client)
    as_role(RoleCode.WAREHOUSE_OPERATOR)
    assert client.post(f"/marketplace/fulfilment/offers/{offer.id}/receipts", headers={"Idempotency-Key": "no-accept"}, json={
        "fulfilment_node_id": node_id, "received_quantity_kg": "1", "receipt_evidence_reference": "DOCKET-01",
    }).status_code == 404
    accept(client, offer, buyer)
    as_role(RoleCode.BUYER, buyer_id=buyer.id)
    before = client.get("/marketplace/fulfilment")
    assert before.status_code == 200, before.text
    assert Decimal(before.json()["totals"]["accepted_offer_kg"]) == 300
    assert Decimal(before.json()["totals"]["received_kg"]) == 0
    assert Decimal(before.json()["totals"]["awaiting_receipt_kg"]) == 300

    received = record_receipt(client, offer, node_id)
    assert received.status_code == 201, received.text
    receipt_id = received.json()["id"]
    assert received.json()["inspection_status"] == "PENDING_INSPECTION"
    assert received.json()["evidence_verified"] is False
    repeated = record_receipt(client, offer, node_id)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == receipt_id
    assert session.query(MarketplaceReceipt).count() == 1
    assert record_receipt(client, offer, node_id, "250", key="receipt-1").status_code == 409
    assert record_receipt(client, offer, node_id, "101", key="receipt-2").status_code == 409

    inspected = inspect(client, receipt_id)
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["inspection_status"] == "PARTIALLY_ACCEPTED"
    assert inspected.json()["assigned_grade"] == "A"
    second = inspect(client, receipt_id)
    assert second.status_code == 200
    assert second.json()["id"] == receipt_id
    assert inspect(client, receipt_id, "200", "0", "inspect-2", reason="").status_code == 409

    as_role(RoleCode.BUYER, buyer_id=buyer.id)
    final = client.get("/marketplace/fulfilment")
    assert final.status_code == 200, final.text
    totals = final.json()["totals"]
    assert Decimal(totals["received_kg"]) == 200
    assert Decimal(totals["inspected_accepted_kg"]) == 180
    assert Decimal(totals["inspected_rejected_kg"]) == 20
    assert Decimal(totals["awaiting_receipt_kg"]) == 100
    assert Decimal(totals["pending_inspection_kg"]) == 0
    assert final.json()["receipts"][0]["receipt_evidence_reference"] == "DOCKET-2026-001"
    assert final.json()["receipts"][0]["evidence_verified"] is False
    # Marketplace procurement coverage remains unchanged by physical inspection;
    # a later recovery workflow must explicitly reconcile quality losses.
    dashboard = client.get("/marketplace/command-center/summary")
    assert dashboard.status_code == 200
    assert Decimal(dashboard.json()["totals"]["accepted_offer_kg"]) == 300
    assert Decimal(dashboard.json()["totals"]["remaining_offer_kg"]) == 200
    session.refresh(request)
    assert request.lifecycle_status == RequirementLifecycleStatus.ACTIVE  # no invented delivery
    as_role(RoleCode.WAREHOUSE_OPERATOR)
    nodes = client.get("/marketplace/fulfilment/nodes")
    assert nodes.status_code == 200 and nodes.json()["items"][0]["id"] == node_id


def test_inspection_requires_exact_quantities_and_rejection_reason(client, session):
    buyer, _, _, _, _, offer = seeded(session)
    node_id = create_node(client)
    accept(client, offer, buyer)
    receipt_id = record_receipt(client, offer, node_id).json()["id"]
    assert inspect(client, receipt_id, "170", "20").status_code == 422
    assert inspect(client, receipt_id, "180", "20", reason="").status_code == 422
    assert inspect(client, receipt_id, "180", "20", grade=None).status_code == 422
    assert inspect(client, receipt_id, "220", "0").status_code == 422
    assert inspect(client, receipt_id, "200", "0", reason="").status_code == 200


def test_buyers_farmers_and_other_org_cannot_write_or_see_others(client, session):
    buyer, another, _, farmer, _, offer = seeded(session)
    node_id = create_node(client)
    accept(client, offer, buyer)
    as_role(RoleCode.BUYER, buyer_id=buyer.id)
    assert client.post(f"/marketplace/fulfilment/offers/{offer.id}/receipts", headers={"Idempotency-Key": "write-buyer"}, json={
        "fulfilment_node_id": node_id, "received_quantity_kg": "1", "receipt_evidence_reference": "DCK-001",
    }).status_code == 403
    assert client.post("/marketplace/fulfilment/nodes", json={"name":"Unauthorized node","node_type":"WH","parish":"Kingston"}).status_code == 403
    assert client.get("/marketplace/fulfilment").json()["offers_count"] == 1
    as_role(RoleCode.BUYER, buyer_id=another.id)
    assert client.get("/marketplace/fulfilment").json()["offers_count"] == 0
    as_role(RoleCode.FARMER, farmer_id=farmer.id)
    assert client.get("/marketplace/fulfilment").json()["offers_count"] == 1
    assert client.post("/marketplace/fulfilment/nodes", json={"name":"Unauthorized node","node_type":"WH","parish":"Kingston"}).status_code == 403
    as_role(RoleCode.BUYER, buyer_id=uuid4())
    assert client.get("/marketplace/fulfilment").status_code == 403
    as_role(RoleCode.WAREHOUSE_OPERATOR, org=ORG_B)
    assert client.get("/marketplace/fulfilment").json()["offers_count"] == 0
    assert record_receipt(client, offer, node_id, "1", key="cross-org-write", org=ORG_B).status_code == 404


def test_receiving_node_must_belong_to_org_and_be_active(client, session):
    buyer, _, _, _, _, offer = seeded(session)
    node_id = create_node(client)
    as_role(RoleCode.ORGANIZATION_ADMIN, org=ORG_B)
    foreign_node = client.post("/marketplace/fulfilment/nodes", json={"name":"Other Depot","node_type":"WAREHOUSE","parish":"Clarendon"})
    assert foreign_node.status_code == 201, foreign_node.text
    accept(client, offer, buyer)
    assert record_receipt(client, offer, foreign_node.json()["id"], "10", key="foreign-node").status_code == 404
    assert record_receipt(client, offer, node_id, "10", key="ok-node").status_code == 201


def test_role_scope_invalid_commands_and_repeat_limits(client, session):
    buyer, _, _, _, _, offer = seeded(session)
    node_id = create_node(client)
    accept(client, offer, buyer)
    as_role(RoleCode.WAREHOUSE_OPERATOR)
    url = f"/marketplace/fulfilment/offers/{offer.id}/receipts"
    payload = {"fulfilment_node_id": node_id, "received_quantity_kg": "300", "receipt_evidence_reference": "DCK-001"}
    assert client.post(url, json=payload).status_code == 400  # key required
    assert client.post(url, headers={"Idempotency-Key": "valid-key"}, json={**payload, "received_quantity_kg": "0"}).status_code == 422
    one = client.post(url, headers={"Idempotency-Key": "valid-key"}, json=payload)
    assert one.status_code == 201, one.text
    assert client.post(url, headers={"Idempotency-Key": "another-key"}, json={**payload, "received_quantity_kg": "1"}).status_code == 409
    as_role(RoleCode.WAREHOUSE_OPERATOR, org=ORG_B)
    assert client.post(f"/marketplace/fulfilment/receipts/{one.json()['id']}/inspect", headers={"Idempotency-Key": "org-b-inspection"}, json={
        "accepted_quantity_kg": "300", "rejected_quantity_kg": "0", "assigned_grade": "A", "inspection_evidence_reference": "CHECK-01"
    }).status_code == 404
    as_role(RoleCode.BUYER, buyer_id=buyer.id)
    assert client.get("/marketplace/fulfilment").json()["totals"]["pending_inspection_kg"] == "300.000"


def test_fulfilment_receipts_not_merged_with_legacy_allocation_ledger(client, session):
    buyer, _, _, _, _, offer = seeded(session)
    node_id = create_node(client)
    accept(client, offer, buyer)
    record_receipt(client, offer, node_id, "100")
    as_role(RoleCode.BUYER, buyer_id=buyer.id)
    response = client.get("/marketplace/fulfilment")
    assert response.status_code == 200
    assert "not independently verified" in response.json()["note"]
    assert response.json()["receipts_count"] == 1
    assert response.json()["truncated"] is False
