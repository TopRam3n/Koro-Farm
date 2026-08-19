from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.domain.common import AvailabilityConfidence, Crop, Grade
from app.demand.domain.models import Buyer
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from app.infrastructure.database.seed import seed


def test_requirement_creation_endpoint(client, session) -> None:
    buyer = Buyer(name="Hotel", buyer_type="HOTEL", destination="Montego Bay")
    session.add(buyer)
    session.commit()
    response = client.post("/requirements", json={
        "buyer_id": str(buyer.id), "crop": "GINGER", "grade": "A", "required_quantity_kg": "500.000",
        "delivery_window_start": "2026-09-01", "delivery_window_end": "2026-09-02",
    })
    assert response.status_code == 201
    assert response.json()["supply_health"] == "UNPLANNED"
    assert client.get(f"/requirements/{response.json()['id']}").status_code == 200


def test_production_lot_serialization(client, session) -> None:
    farmer = Farmer(name="Farmer", parish="Clarendon")
    session.add(farmer)
    session.flush()
    lot = ProductionLot(
        farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 9, 1), harvest_end=date(2026, 9, 4),
        expected_quantity_kg=Decimal("70"), available_quantity_kg=Decimal("60"), reserved_quantity_kg=Decimal("0"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
        parish="Clarendon", status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc),
    )
    session.add(lot)
    session.commit()
    response = client.get(f"/production-lots/{lot.id}")
    assert response.status_code == 200
    assert response.json()["available_quantity_kg"] == "60.000"


def test_plan_and_assurance_endpoints(client, session) -> None:
    seed(session)
    buyer = session.query(Buyer).one()
    start = date.today() + timedelta(days=5)
    end = date.today() + timedelta(days=10)
    requirement = client.post("/requirements", json={
        "buyer_id": str(buyer.id), "crop": "GINGER", "grade": "A", "required_quantity_kg": "500",
        "delivery_window_start": str(start), "delivery_window_end": str(end),
    })
    assert requirement.status_code == 201
    plan = client.post(f"/requirements/{requirement.json()['id']}/plan")
    assert plan.status_code == 201
    assert plan.json()["committed_quantity_kg"] == "500.000"
    assurance = client.get(f"/requirements/{requirement.json()['id']}/assurance")
    assert assurance.status_code == 200
    assert assurance.json()["supply_health"] == "COVERED"
    assert assurance.json()["standby_quantity_kg"] == "100.000"
