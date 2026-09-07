"""Synthetic Jamaican development seed data; never represents verified live farm data."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.infrastructure.database.session import create_session_factory
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.application.planner import finalize_plan

DEMO_REQUIREMENT_ID = UUID("00000000-0000-0000-0000-000000000500")
DEMO_BUYER_ID = UUID("00000000-0000-0000-0000-000000000001")
DEMO_NODE_ID = UUID("00000000-0000-0000-0000-000000000002")

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


def seed_competition_demo(session: Session) -> UUID:
    """Create the exact synthetic 500 kg competition state with stable identifiers."""
    if session.get(Requirement, DEMO_REQUIREMENT_ID) is not None:
        return DEMO_REQUIREMENT_ID
    buyer = Buyer(id=DEMO_BUYER_ID, name="Harbour View Hotel (Synthetic)", buyer_type="HOTEL",
                  destination="Montego Bay, Jamaica")
    node = FulfilmentNode(id=DEMO_NODE_ID, name="Montego Bay Collection Hub (Synthetic)",
                          node_type="COLLECTION_CENTRE", parish="St. James")
    session.add_all([buyer, node])
    session.flush()
    start = date(2026, 9, 8)
    end = date(2026, 9, 15)
    parishes = ["Manchester", "St. Elizabeth", "Clarendon", "St. Ann"]
    for index in range(8):
        farmer_id = UUID(f"00000000-0000-0000-0001-{index + 1:012d}")
        lot_id = UUID(f"00000000-0000-0000-0002-{index + 1:012d}")
        farmer = Farmer(id=farmer_id, name=f"Demo Farmer {index + 1}", parish=parishes[index % 4])
        lot = ProductionLot(
            id=lot_id, farmer_id=farmer_id, crop=Crop.GINGER, harvest_start=start,
            harvest_end=end, expected_quantity_kg=Decimal("80"), available_quantity_kg=Decimal("80"),
            reserved_quantity_kg=Decimal("0"), quality_grade_estimate=Grade.A,
            availability_confidence=AvailabilityConfidence.HIGH, parish=farmer.parish,
            status=ProductionLotStatus.AVAILABLE,
            last_verified_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
        session.add_all([farmer, lot])
        session.flush()
        session.add(LotCostInput(
            production_lot_id=lot_id, farmgate_price_per_kg_jmd=Decimal(280 + index * 5),
            pickup_cost_jmd=Decimal("250"), handling_grading_cost_per_kg_jmd=Decimal("22"),
            packaging_cost_per_kg_jmd=Decimal("12"), transport_cost_jmd=Decimal("350"),
            expected_rejection_pct=Decimal("0.02"),
        ))
    requirement = Requirement(
        id=DEMO_REQUIREMENT_ID, buyer_id=DEMO_BUYER_ID, crop=Crop.GINGER, grade=Grade.A,
        required_quantity_kg=Decimal("500"), delivery_window_start=start, delivery_window_end=end,
    )
    session.add(requirement)
    session.commit()
    finalize_plan(session, DEMO_REQUIREMENT_ID)
    session.commit()
    return DEMO_REQUIREMENT_ID


if __name__ == "__main__":
    session = create_session_factory()()
    try:
        seed(session)
    finally:
        session.close()
