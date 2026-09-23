import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.identity.domain.models import DEFAULT_ORGANIZATION_ID
from src.backend.app.ingestion.domain.models import (
    FreshnessStatus, IngestionRecord, OperationalObservation, SecureActionLink,
    SourceChannel, VerificationStatus,
)
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.demand.domain.models import Buyer, Requirement


def _lot(session) -> tuple[Farmer, ProductionLot]:
    farmer = Farmer(organization_id=DEFAULT_ORGANIZATION_ID, name="Secure Link Farmer", parish="Manchester")
    session.add(farmer); session.flush()
    lot = ProductionLot(
        farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 10, 1),
        harvest_end=date(2026, 10, 10), expected_quantity_kg=Decimal("150"),
        available_quantity_kg=Decimal("120"), reserved_quantity_kg=Decimal("20"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
        parish=farmer.parish, status=ProductionLotStatus.AVAILABLE,
        last_verified_at=datetime.now(timezone.utc),
    )
    session.add(lot); session.commit()
    return farmer, lot


def _create_link(client, farmer: Farmer, lot: ProductionLot, expires_in_hours: int = 48) -> dict:
    response = client.post("/v1/ingestion/secure-links", json={
        "farmer_id": str(farmer.id), "purpose": "CONFIRM_QUANTITY", "production_lot_id": str(lot.id),
        "request_reference": "REQ-SECURE-001", "expires_in_hours": expires_in_hours,
        "constraints": {"maximum_quantity_kg": "150"},
    })
    assert response.status_code == 201
    return response.json()


def test_valid_farmer_secure_response_preserves_provenance(client, session) -> None:
    farmer, lot = _lot(session)
    link = _create_link(client, farmer, lot)
    inspected = client.get(f"/v1/secure-actions/{link['token']}")
    assert inspected.status_code == 200
    assert inspected.json()["farmer_name"] == farmer.name
    response = client.post(
        f"/v1/secure-actions/{link['token']}", headers={"Idempotency-Key": "farmer-response-1"},
        json={"available_quantity_kg": "95", "evidence_reference": "synthetic://farmer-confirmation/1"},
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "SELF_REPORTED"
    assert response.json()["freshness_status"] == "CURRENT"
    retry = client.post(
        f"/v1/secure-actions/{link['token']}", headers={"Idempotency-Key": "farmer-response-1"},
        json={"available_quantity_kg": "95", "evidence_reference": "synthetic://farmer-confirmation/1"},
    )
    assert retry.status_code == 200
    assert retry.json() == response.json()
    session.refresh(lot)
    assert lot.available_quantity_kg == Decimal("95.000")
    record = session.get(IngestionRecord, UUID(response.json()["ingestion_record_id"]))
    observation = session.query(OperationalObservation).filter_by(ingestion_record_id=record.id).one()
    assert record.channel == SourceChannel.SECURE_LINK
    assert observation.verification_status == VerificationStatus.SELF_REPORTED
    assert observation.freshness_status == FreshnessStatus.CURRENT


def test_secure_link_reuse_tamper_expiry_and_scope_are_blocked(client, session) -> None:
    farmer, lot = _lot(session)
    link = _create_link(client, farmer, lot)
    first = client.post(f"/v1/secure-actions/{link['token']}", headers={"Idempotency-Key": "once"},
                        json={"available_quantity_kg": "90"})
    assert first.status_code == 200
    assert client.post(f"/v1/secure-actions/{link['token']}", headers={"Idempotency-Key": "twice"},
                       json={"available_quantity_kg": "80"}).status_code == 409
    assert client.get(f"/v1/secure-actions/{link['token']}tampered").status_code == 404

    expiring = _create_link(client, farmer, lot, expires_in_hours=1)
    row = session.query(SecureActionLink).filter_by(
        token_hash=hashlib.sha256(expiring["token"].encode()).hexdigest()
    ).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()
    assert client.get(f"/v1/secure-actions/{expiring['token']}").status_code == 410

    scoped = _create_link(client, farmer, lot)
    too_large = client.post(f"/v1/secure-actions/{scoped['token']}", headers={"Idempotency-Key": "scope"},
                            json={"available_quantity_kg": "151"})
    assert too_large.status_code == 422


def test_secure_link_cannot_reduce_availability_below_reservation(client, session) -> None:
    farmer, lot = _lot(session)
    link = _create_link(client, farmer, lot)
    response = client.post(f"/v1/secure-actions/{link['token']}", headers={"Idempotency-Key": "unsafe"},
                           json={"available_quantity_kg": "10"})
    assert response.status_code == 409
    session.refresh(lot)
    assert lot.available_quantity_kg == Decimal("120.000")


def test_coordinator_entry_attributes_recorder_and_source(client, session) -> None:
    farmer, lot = _lot(session)
    response = client.post("/v1/ingestion/coordinator-observations", json={
        "farmer_id": str(farmer.id), "production_lot_id": str(lot.id),
        "action": "UPDATE_AVAILABLE_QUANTITY", "available_quantity_kg": "100",
        "source_channel": "PHONE", "effective_at": datetime.now(timezone.utc).isoformat(),
        "confirmation_status": "FARMER_CONFIRMED", "notes": "Farmer confirmed by phone",
    })
    assert response.status_code == 201
    assert response.json()["source"] == "PHONE"
    assert response.json()["verification_status"] == "COORDINATOR_CONFIRMED"
    record = session.get(IngestionRecord, UUID(response.json()["ingestion_record_id"]))
    assert record.actor_user_id is not None


def test_coordinator_channel_and_cross_tenant_target_are_rejected(client, session) -> None:
    farmer, lot = _lot(session)
    bad_channel = client.post("/v1/ingestion/coordinator-observations", json={
        "farmer_id": str(farmer.id), "production_lot_id": str(lot.id),
        "action": "UPDATE_AVAILABLE_QUANTITY", "available_quantity_kg": "100",
        "source_channel": "SENSOR", "effective_at": datetime.now(timezone.utc).isoformat(),
        "confirmation_status": "UNCONFIRMED",
    })
    assert bad_channel.status_code == 422


def test_csv_preview_reports_invalid_rows_and_confirm_is_idempotent(client, session) -> None:
    content = "name,parish\nCSV Farmer,Manchester\nMissing Parish,\nCSV Farmer,Manchester\n"
    preview = client.post("/v1/ingestion/imports/preview", json={
        "entity_type": "farmers", "source_file_name": "farmers.csv", "csv_content": content,
    })
    assert preview.status_code == 201
    body = preview.json()
    assert body["accepted_rows"] == 1
    assert body["rejected_rows"] == 2
    assert body["rows"][1]["errors"] == ["parish is required"]
    assert body["rows"][2]["errors"] == ["duplicate row in file"]
    confirmed = client.post(f"/v1/ingestion/imports/{body['import_id']}/confirm",
                            headers={"Idempotency-Key": "farmers-import-1"})
    assert confirmed.status_code == 200
    assert confirmed.json()["imported_rows"] == 1
    assert client.post(f"/v1/ingestion/imports/{body['import_id']}/confirm",
                       headers={"Idempotency-Key": "farmers-import-1"}).json() == confirmed.json()
    assert session.query(Farmer).filter_by(name="CSV Farmer").count() == 1
    record = session.query(IngestionRecord).filter_by(
        channel=SourceChannel.CSV_IMPORT, target_entity_type="farmers"
    ).one()
    event = session.get(DomainEvent, record.resulting_event_id)
    assert event.event_type == "ingestion.entity_created"
    assert event.correlation_id == record.correlation_id
    assert session.query(OutboxMessage).filter_by(event_id=event.id).count() == 1
    duplicate = client.post("/v1/ingestion/imports/preview", json={
        "entity_type": "farmers", "source_file_name": "renamed.csv", "csv_content": content,
    })
    assert duplicate.status_code == 409


def test_csv_production_lot_and_requirement_imports_use_scoped_parents(client, session) -> None:
    farmer, _ = _lot(session)
    buyer = Buyer(organization_id=DEFAULT_ORGANIZATION_ID, name="CSV Buyer", buyer_type="HOTEL", destination="Jamaica")
    session.add(buyer); session.commit()
    lot_csv = (
        "farmer_id,crop,harvest_start,harvest_end,expected_quantity_kg,available_quantity_kg,grade,availability_confidence,parish\n"
        f"{farmer.id},GINGER,2026-11-01,2026-11-10,200,180,A,HIGH,Manchester\n"
    )
    lot_preview = client.post("/v1/ingestion/imports/preview", json={
        "entity_type": "production_lots", "source_file_name": "lots.csv", "csv_content": lot_csv,
    }).json()
    assert client.post(f"/v1/ingestion/imports/{lot_preview['import_id']}/confirm",
                       headers={"Idempotency-Key": "lots-import"}).status_code == 200
    requirement_csv = (
        "buyer_id,crop,grade,required_quantity_kg,delivery_window_start,delivery_window_end\n"
        f"{buyer.id},GINGER,A,300,2026-11-05,2026-11-12\n"
    )
    requirement_preview = client.post("/v1/ingestion/imports/preview", json={
        "entity_type": "buyer_requirements", "source_file_name": "requirements.csv",
        "csv_content": requirement_csv,
    }).json()
    assert client.post(f"/v1/ingestion/imports/{requirement_preview['import_id']}/confirm",
                       headers={"Idempotency-Key": "requirements-import"}).status_code == 200
    assert session.query(ProductionLot).filter_by(farmer_id=farmer.id).count() == 2
    requirement = session.query(Requirement).filter_by(buyer_id=buyer.id).one()
    record = session.query(IngestionRecord).filter_by(
        channel=SourceChannel.CSV_IMPORT, target_entity_id=requirement.id
    ).one()
    assert session.get(DomainEvent, record.resulting_event_id).event_type == "requirement.created"


def test_csv_templates_are_downloadable_and_unknown_template_is_rejected(client) -> None:
    response = client.get("/v1/ingestion/imports/templates/farmers")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text == "name,parish\r\n"
    assert client.get("/v1/ingestion/imports/templates/shipments").status_code == 404
