from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus


def test_production_lot_rejects_reserved_above_available() -> None:
    lot = ProductionLot(
        farmer_id="123e4567-e89b-12d3-a456-426614174000", crop=Crop.GINGER,
        harvest_start=date(2026, 9, 1), harvest_end=date(2026, 9, 4),
        expected_quantity_kg=Decimal("50"), available_quantity_kg=Decimal("40"), reserved_quantity_kg=Decimal("41"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
        parish="Manchester", status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValueError, match="reserved quantity"):
        lot.validate()


def test_database_rejects_reserved_above_available(session) -> None:
    farmer = Farmer(name="Synthetic Farmer", parish="Manchester")
    session.add(farmer)
    session.flush()
    lot = ProductionLot(
        farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 9, 1), harvest_end=date(2026, 9, 4),
        expected_quantity_kg=Decimal("50"), available_quantity_kg=Decimal("40"), reserved_quantity_kg=Decimal("41"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
        parish="Manchester", status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc),
    )
    session.add(lot)
    with pytest.raises(IntegrityError):
        session.commit()


def test_requirement_lifecycle_enum_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        RequirementLifecycleStatus("FULFILLED")


def test_database_persists_requirement(session) -> None:
    buyer = Buyer(name="Hotel", buyer_type="HOTEL", destination="Montego Bay")
    session.add(buyer)
    session.flush()
    requirement = Requirement(
        buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A, required_quantity_kg=Decimal("500"),
        delivery_window_start=date(2026, 9, 1), delivery_window_end=date(2026, 9, 2),
    )
    requirement.validate()
    session.add(requirement)
    session.commit()
    assert session.get(Requirement, requirement.id).required_quantity_kg == Decimal("500.000")
