"""Synthetic Jamaican development seed data; never represents verified live farm data."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.common import AvailabilityConfidence, Crop, Grade
from app.demand.domain.models import Buyer
from app.economics.domain.models import LotCostInput
from app.fulfilment.domain.models import FulfilmentNode
from app.infrastructure.database.session import create_session_factory
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus

FARMERS = [
    ("Alicia Brown", "Manchester"), ("Dwayne Clarke", "Manchester"), ("Marcia Ellis", "St. Elizabeth"),
    ("Rohan Grant", "St. Elizabeth"), ("Keisha Henry", "Clarendon"), ("Omar James", "Clarendon"),
    ("Patricia King", "St. Ann"), ("Leroy Lewis", "St. Ann"), ("Nadine Morgan", "Manchester"),
    ("Peter Nelson", "St. Elizabeth"), ("Renee Palmer", "Clarendon"), ("Sean Reid", "St. Ann"),
]
LOT_QUANTITIES = [65, 50, 80, 45, 70, 55, 60, 40, 75, 50, 65, 45, 55, 60, 50, 70, 45, 55]


def seed(session: Session) -> None:
    if session.scalar(select(Buyer.id).limit(1)) is not None:
        return
    buyer = Buyer(name="Harbour View Hotel (Synthetic)", buyer_type="HOTEL", destination="Montego Bay, Jamaica")
    node = FulfilmentNode(name="Montego Bay Collection Hub (Synthetic)", node_type="COLLECTION_CENTRE", parish="St. James")
    farmers = [Farmer(name=name, parish=parish) for name, parish in FARMERS]
    session.add_all([buyer, node, *farmers])
    session.flush()
    today = date.today()
    now = datetime.now(timezone.utc)
    lots: list[ProductionLot] = []
    for index, quantity in enumerate(LOT_QUANTITIES):
        farmer = farmers[index % len(farmers)]
        lots.append(ProductionLot(
            farmer_id=farmer.id, crop=Crop.GINGER,
            harvest_start=today + timedelta(days=3 + index % 5), harvest_end=today + timedelta(days=10 + index % 5),
            expected_quantity_kg=Decimal(quantity + 10), available_quantity_kg=Decimal(quantity), reserved_quantity_kg=Decimal("0"),
            quality_grade_estimate=Grade.A if index != 7 else Grade.B,
            availability_confidence=(AvailabilityConfidence.HIGH if index % 3 == 0 else AvailabilityConfidence.MEDIUM),
            parish=farmer.parish, status=ProductionLotStatus.AVAILABLE, last_verified_at=now,
        ))
    session.add_all(lots)
    session.flush()
    session.add_all([
        LotCostInput(
            production_lot_id=lot.id,
            farmgate_price_per_kg_jmd=Decimal(285 + (index % 5) * 8),
            pickup_cost_jmd=Decimal(250 + (index % 4) * 20),
            handling_grading_cost_per_kg_jmd=Decimal("22.00"),
            packaging_cost_per_kg_jmd=Decimal("12.00"),
            transport_cost_jmd=Decimal(350 + (index % 3) * 30),
            expected_rejection_pct=Decimal("0.03") if index % 3 else Decimal("0.02"),
        )
        for index, lot in enumerate(lots)
    ])
    session.commit()


if __name__ == "__main__":
    session = create_session_factory()()
    try:
        seed(session)
    finally:
        session.close()
