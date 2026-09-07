from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from src.backend.app.compliance.domain.models import ComplianceRule
from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.supply.application.planner import PlannerConfig, finalize_plan
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import SupplyAllocation


def execution_state(session):
    buyer = Buyer(name="Hotel", buyer_type="HOTEL", destination="Jamaica")
    node = FulfilmentNode(name="Hub", node_type="HUB", parish="St. James")
    farmer = Farmer(name="Farmer", parish="Manchester")
    session.add_all([buyer, node, farmer]); session.flush()
    req = create_requirement(session, Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
        required_quantity_kg=Decimal("100"), delivery_window_start=date(2026, 9, 8), delivery_window_end=date(2026, 9, 15)))
    lot = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 9, 8),
        harvest_end=date(2026, 9, 15), expected_quantity_kg=100, available_quantity_kg=100,
        reserved_quantity_kg=0, quality_grade_estimate=Grade.A,
        availability_confidence=AvailabilityConfidence.HIGH, parish=farmer.parish,
        status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
    session.add(lot); session.flush()
    session.add(LotCostInput(production_lot_id=lot.id, farmgate_price_per_kg_jmd=300,
        pickup_cost_jmd=100, handling_grading_cost_per_kg_jmd=20, packaging_cost_per_kg_jmd=10,
        transport_cost_jmd=100, expected_rejection_pct=Decimal("0.02"))); session.commit()
    plan = finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
    return req, node, farmer, lot, allocation


def test_execution_traceability_reconciliation_and_passport_are_evidence_gated(client, session):
    req, node, farmer, lot, allocation = execution_state(session)
    received = client.post("/sublots/receive", headers={"Idempotency-Key": "receive"}, json={
        "allocation_id": str(allocation.id), "fulfilment_node_id": str(node.id),
        "received_quantity_kg": "100", "received_at": "2026-09-10T12:00:00Z",
        "receipt_evidence_reference": "receipt-001",
    })
    assert received.status_code == 200
    sublot_id = received.json()["received_sublot_id"]
    graded = client.post(f"/sublots/{sublot_id}/grade", headers={"Idempotency-Key": "grade"}, json={
        "accepted_quantity_kg": "100", "rejected_quantity_kg": "0", "assigned_grade": "A",
        "inspection_evidence_reference": "inspection-001",
    })
    assert graded.status_code == 200
    assert client.get(f"/farmers/{farmer.id}/trade-performance-passport").json()["completed_institutional_trades"] == 0

    headers = {"Idempotency-Key": "shipment-create"}
    created = client.post(f"/requirements/{req.id}/shipments", headers=headers,
                          json={"fulfilment_node_id": str(node.id), "reference": "SHIP-001"})
    assert created.status_code == 200
    assert client.post(f"/requirements/{req.id}/shipments", headers=headers,
                       json={"fulfilment_node_id": str(node.id), "reference": "SHIP-001"}).json() == created.json()
    shipment_id = created.json()["shipment_id"]
    add_headers = {"Idempotency-Key": "shipment-add"}
    added = client.post(f"/shipments/{shipment_id}/sublots", headers=add_headers, json={"received_sublot_id": sublot_id})
    assert added.status_code == 200
    assert client.post(f"/shipments/{shipment_id}/sublots", headers=add_headers, json={"received_sublot_id": sublot_id}).json() == added.json()
    dispatch_headers = {"Idempotency-Key": "dispatch"}
    dispatched = client.post(f"/shipments/{shipment_id}/dispatch", headers=dispatch_headers, json={"evidence_reference": "dispatch-001"})
    assert dispatched.json()["status"] == "DISPATCHED"
    assert client.post(f"/shipments/{shipment_id}/dispatch", headers=dispatch_headers, json={"evidence_reference": "dispatch-001"}).json() == dispatched.json()
    delivery_headers = {"Idempotency-Key": "delivery"}
    delivered = client.post(f"/shipments/{shipment_id}/delivery", headers=delivery_headers, json={
        "delivered_quantity_kg": "100", "delivered_at": "2026-09-12T12:00:00Z",
        "delivery_evidence_reference": "pod-001", "buyer_confirmed": True,
        "buyer_confirmation_evidence": "buyer-signoff-001",
    })
    assert delivered.status_code == 200
    assert client.post(f"/shipments/{shipment_id}/delivery", headers=delivery_headers, json={
        "delivered_quantity_kg": "100", "delivered_at": "2026-09-12T12:00:00Z",
        "delivery_evidence_reference": "pod-001", "buyer_confirmed": True,
        "buyer_confirmation_evidence": "buyer-signoff-001",
    }).json() == delivered.json()
    recon_headers = {"Idempotency-Key": "reconcile"}
    reconciled = client.post(f"/requirements/{req.id}/reconcile", headers=recon_headers,
                             json={"verification_evidence_reference": "coordinator-check-001"})
    assert reconciled.status_code == 200 and reconciled.json()["verification_status"] == "verified"
    assert client.post(f"/requirements/{req.id}/reconcile", headers=recon_headers,
                       json={"verification_evidence_reference": "coordinator-check-001"}).json() == reconciled.json()
    passport = client.get(f"/farmers/{farmer.id}/trade-performance-passport").json()
    assert passport["completed_institutional_trades"] == 1
    assert passport["history_maturity"] == "BUILDING_HISTORY"
    assert passport["financing_eligibility"] == "NOT_ASSESSED"
    assert client.get(f"/shipments/{shipment_id}/traceability").json()["sources"][0]["production_lot_id"] == str(lot.id)
    assert client.get(f"/production-lots/{lot.id}/shipments").json()["shipments"][0]["shipment_id"] == shipment_id


def test_reconciliation_refuses_missing_buyer_confirmation(client, session):
    req, node, _, _, allocation = execution_state(session)
    received = client.post("/sublots/receive", headers={"Idempotency-Key": "r2"}, json={
        "allocation_id": str(allocation.id), "fulfilment_node_id": str(node.id), "received_quantity_kg": "100",
        "received_at": "2026-09-10T12:00:00Z", "receipt_evidence_reference": "receipt",
    }).json()
    client.post(f"/sublots/{received['received_sublot_id']}/grade", headers={"Idempotency-Key": "g2"}, json={"accepted_quantity_kg": "100", "rejected_quantity_kg": "0", "assigned_grade": "A", "inspection_evidence_reference": "inspection"})
    shipment = client.post(f"/requirements/{req.id}/shipments", headers={"Idempotency-Key": "sc2"}, json={"fulfilment_node_id": str(node.id), "reference": "SHIP-002"}).json()
    client.post(f"/shipments/{shipment['shipment_id']}/sublots", headers={"Idempotency-Key": "sa2"}, json={"received_sublot_id": received["received_sublot_id"]})
    client.post(f"/shipments/{shipment['shipment_id']}/dispatch", headers={"Idempotency-Key": "sd2"}, json={"evidence_reference": "dispatch"})
    client.post(f"/shipments/{shipment['shipment_id']}/delivery", headers={"Idempotency-Key": "del2"}, json={"delivered_quantity_kg": "100", "delivered_at": "2026-09-12T12:00:00Z", "delivery_evidence_reference": "pod", "buyer_confirmed": False})
    response = client.post(f"/requirements/{req.id}/reconcile", headers={"Idempotency-Key": "rec2"}, json={"verification_evidence_reference": "check"})
    assert response.status_code == 409


def test_compliance_filters_unverified_expired_future_and_wrong_context(client, session):
    req, _, _, _, _ = execution_state(session)
    now = datetime.now(timezone.utc)
    rules = [
        ComplianceRule(origin="Jamaica", destination="Jamaica", crop=Crop.GINGER, product_form="FRESH", rule_name="Valid A", issuing_body="Verified body", description="Stored rule", required_before="DISPATCH", lead_time="1 day", effective_from=date(2026, 1, 1), source_citation="source-a", source_version="1", last_verified_at=now, verified_by="Officer"),
        ComplianceRule(origin="Jamaica", destination="Jamaica", crop=Crop.GINGER, product_form="FRESH", rule_name="Valid B", issuing_body="Verified body", description="Stored overlap", required_before="DISPATCH", lead_time="1 day", effective_from=date(2026, 2, 1), source_citation="source-b", source_version="2", last_verified_at=now, verified_by="Officer"),
        ComplianceRule(origin="Jamaica", destination="Jamaica", crop=Crop.GINGER, product_form="FRESH", rule_name="Expired", issuing_body="Body", description="Old", required_before="DISPATCH", lead_time="1 day", effective_from=date(2025, 1, 1), effective_until=date(2025, 2, 1), source_citation="old", source_version="1", last_verified_at=now, verified_by="Officer"),
        ComplianceRule(origin="Barbados", destination="Jamaica", crop=Crop.GINGER, product_form="FRESH", rule_name="Wrong origin", issuing_body="Body", description="Wrong", required_before="DISPATCH", lead_time="1 day", effective_from=date(2026, 1, 1), source_citation="wrong", source_version="1", last_verified_at=now, verified_by="Officer"),
        ComplianceRule(origin="Jamaica", destination="Jamaica", crop=Crop.GINGER, product_form="FRESH", rule_name="Malformed", issuing_body="Body", description="No citation", required_before="DISPATCH", lead_time="1 day", effective_from=date(2026, 1, 1), source_citation="", source_version="1", last_verified_at=now, verified_by="Officer"),
    ]
    session.add_all(rules); session.commit()
    response = client.get(f"/requirements/{req.id}/compliance")
    assert response.status_code == 200
    assert [rule["rule_name"] for rule in response.json()["rules"]] == ["Valid A", "Valid B"]
    assert client.get(f"/requirements/{req.id}/compliance?product_form=DRIED").json()["status"] == "no_verified_rule_on_file"
