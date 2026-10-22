from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.auth import get_current_user
from app.identity.application.authorization import get_authorization_context
from app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from app.identity.domain.permissions import RoleCode
from app.main import app
from app.demand.domain.models import Buyer
from app.domain.common import AvailabilityConfidence, Crop, Grade
from app.ingestion.domain.models import IngestionRecord, OperationalObservation
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus


ORG_ID = UUID("00000000-0000-0000-0000-000000001301")


def _identity(session, role: RoleCode, *, farmer_id=None, buyer_id=None):
    organization = session.get(Organization, ORG_ID)
    if organization is None:
        organization = Organization(id=ORG_ID, name="Marketplace Test", slug=f"marketplace-{uuid4().hex[:8]}")
        session.add(organization)
        session.flush()
    user = UserAccount(id=uuid4(), email=f"{uuid4().hex}@example.test", display_name="Test User")
    session.add(user)
    session.flush()
    membership = OrganizationMembership(
        user_id=user.id, organization_id=ORG_ID, role_code=role, status=MembershipStatus.ACTIVE,
        farmer_id=farmer_id, buyer_id=buyer_id,
    )
    session.add(membership)
    session.commit()
    return user


def _authenticate(user: UserAccount) -> dict[str, str]:
    app.dependency_overrides.pop(get_authorization_context, None)
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user.id), "email": user.email}
    return {"X-Organization-ID": str(ORG_ID)}


def _lot(session, farmer: Farmer, *, quantity: Decimal = Decimal("20")) -> ProductionLot:
    lot = ProductionLot(
        farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2027, 1, 1), harvest_end=date(2027, 1, 7),
        expected_quantity_kg=quantity, available_quantity_kg=quantity, reserved_quantity_kg=Decimal("0"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.MEDIUM,
        parish=farmer.parish, status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc),
    )
    session.add(lot)
    session.commit()
    return lot


def test_farmer_report_creates_only_linked_supply_and_provenance(client, session) -> None:
    own_farmer = Farmer(organization_id=ORG_ID, name="Own Farm", parish="Manchester")
    other_farmer = Farmer(organization_id=ORG_ID, name="Other Farm", parish="Clarendon")
    organization = Organization(id=ORG_ID, name="Marketplace Test", slug=f"marketplace-{uuid4().hex[:8]}")
    session.add_all([organization, own_farmer, other_farmer])
    session.flush()
    own_farmer.organization_id = organization.id
    other_farmer.organization_id = organization.id
    session.commit()
    user = _identity(session, RoleCode.FARMER, farmer_id=own_farmer.id)
    headers = _authenticate(user)

    response = client.post("/v1/ingestion/farmer-production-lots", headers=headers, json={
        "crop": "GINGER", "harvest_start": "2027-01-01", "harvest_end": "2027-01-07",
        "expected_quantity_kg": "35", "quality_grade_estimate": "B",
    })

    assert response.status_code == 201
    lot = session.get(ProductionLot, UUID(response.json()["production_lot_id"]))
    assert lot.farmer_id == own_farmer.id
    assert lot.expected_quantity_kg == Decimal("35")
    assert lot.available_quantity_kg == Decimal("0")
    assert lot.status == ProductionLotStatus.UNAVAILABLE
    assert lot.quality_grade_estimate == Grade.B
    assert lot.availability_confidence == AvailabilityConfidence.LOW
    record = session.get(IngestionRecord, UUID(response.json()["ingestion_record_id"]))
    assert record.actor_user_id == user.id
    assert record.farmer_id == own_farmer.id
    assert session.query(OperationalObservation).filter_by(target_entity_id=lot.id).count() == 6

    ready = client.post(f"/v1/ingestion/farmer-production-lots/{lot.id}/availability", headers=headers,
                        json={"available_quantity_kg": "20"})
    assert ready.status_code == 200
    session.refresh(lot)
    assert lot.available_quantity_kg == Decimal("20")
    assert lot.status == ProductionLotStatus.AVAILABLE
    assert other_farmer.id != lot.farmer_id

    too_much = client.post(f"/v1/ingestion/farmer-production-lots/{lot.id}/availability", headers=headers,
                           json={"available_quantity_kg": "36"})
    assert too_much.status_code == 422

    other_user = _identity(session, RoleCode.FARMER, farmer_id=other_farmer.id)
    assert client.post(f"/v1/ingestion/farmer-production-lots/{lot.id}/availability",
                       headers=_authenticate(other_user), json={"available_quantity_kg": "10"}).status_code == 404


def test_buyer_can_watch_availability_and_order_without_overselling(client, session) -> None:
    organization = Organization(id=ORG_ID, name="Marketplace Test", slug=f"marketplace-{uuid4().hex[:8]}")
    buyer = Buyer(organization_id=ORG_ID, name="Hotel Buyer", buyer_type="HOTEL", destination="Kingston")
    farmer = Farmer(organization_id=ORG_ID, name="Sample Farm", parish="St. Mary")
    session.add_all([organization, buyer, farmer])
    session.flush()
    lot = _lot(session, farmer)
    buyer_user = _identity(session, RoleCode.BUYER, buyer_id=buyer.id)
    headers = _authenticate(buyer_user)

    availability = client.get("/marketplace/availability", headers=headers)
    assert availability.status_code == 200
    assert availability.json()["items"][0]["farmer_name"] == farmer.name

    watch = client.post("/marketplace/watches", headers=headers, json={
        "crop": "GINGER", "minimum_quantity_kg": "10",
    })
    assert watch.status_code == 201
    alerts = client.get("/marketplace/alerts", headers=headers)
    assert alerts.status_code == 200
    assert len(alerts.json()["items"]) == 1
    assert alerts.json()["items"][0]["production_lot_id"] == str(lot.id)

    order = client.post("/marketplace/orders", headers=headers, json={
        "production_lot_id": str(lot.id), "quantity_kg": "15",
    })
    assert order.status_code == 201
    assert order.json()["status"] == "PLACED"
    session.refresh(lot)
    assert lot.reserved_quantity_kg == Decimal("15")

    oversell = client.post("/marketplace/orders", headers=headers, json={
        "production_lot_id": str(lot.id), "quantity_kg": "6",
    })
    assert oversell.status_code == 409

    remaining = client.get("/marketplace/availability", headers=headers)
    assert remaining.json()["items"][0]["available_quantity_kg"] == "5.000"


def test_farmer_cannot_place_orders_or_read_another_buyers_orders(client, session) -> None:
    organization = Organization(id=ORG_ID, name="Marketplace Test", slug=f"marketplace-{uuid4().hex[:8]}")
    farmer = Farmer(organization_id=ORG_ID, name="Sample Farm", parish="St. Mary")
    buyer = Buyer(organization_id=ORG_ID, name="Hotel Buyer", buyer_type="HOTEL", destination="Kingston")
    session.add_all([organization, farmer, buyer])
    session.flush()
    _lot(session, farmer)
    farmer_user = _identity(session, RoleCode.FARMER, farmer_id=farmer.id)
    headers = _authenticate(farmer_user)

    response = client.post("/marketplace/orders", headers=headers, json={
        "production_lot_id": str(uuid4()), "quantity_kg": "1",
    })
    assert response.status_code == 403
    assert client.get("/farmers", headers=headers).status_code == 403
    assert client.get("/requirements", headers=headers).status_code == 403


def test_buyer_cannot_access_staff_registries(client, session) -> None:
    organization = Organization(id=ORG_ID, name="Marketplace Test", slug=f"marketplace-{uuid4().hex[:8]}")
    buyer = Buyer(organization_id=ORG_ID, name="Hotel Buyer", buyer_type="HOTEL", destination="Kingston")
    session.add_all([organization, buyer])
    session.commit()
    buyer_user = _identity(session, RoleCode.BUYER, buyer_id=buyer.id)
    headers = _authenticate(buyer_user)

    assert client.get("/farmers", headers=headers).status_code == 403
    assert client.get("/requirements", headers=headers).status_code == 403


def test_platform_admin_can_review_marketplace_without_impersonating_a_buyer(client, session) -> None:
    organization = Organization(id=ORG_ID, name="Marketplace Test", slug=f"marketplace-{uuid4().hex[:8]}")
    buyer = Buyer(organization_id=ORG_ID, name="Hotel Buyer", buyer_type="HOTEL", destination="Kingston")
    farmer = Farmer(organization_id=ORG_ID, name="Sample Farm", parish="St. Mary")
    session.add_all([organization, buyer, farmer])
    session.flush()
    lot = _lot(session, farmer)
    buyer_user = _identity(session, RoleCode.BUYER, buyer_id=buyer.id)
    buyer_headers = _authenticate(buyer_user)
    order = client.post("/marketplace/orders", headers=buyer_headers, json={
        "production_lot_id": str(lot.id), "quantity_kg": "5",
    })
    assert order.status_code == 201

    admin = _identity(session, RoleCode.PLATFORM_ADMIN)
    admin_headers = _authenticate(admin)
    assert client.get("/marketplace/orders", headers=admin_headers).json()["items"][0]["id"] == order.json()["id"]
    assert client.get("/marketplace/alerts", headers=admin_headers).status_code == 200
    unattributed_order = client.post("/marketplace/orders", headers=admin_headers, json={
        "production_lot_id": str(lot.id), "quantity_kg": "1",
    })
    assert unattributed_order.status_code == 422
