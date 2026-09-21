"""Synthetic Jamaican development seed data; never represents verified live farm data."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.assurance.application.recovery import dropout
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.application.services import grade, receive
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.infrastructure.database.session import create_session_factory
from src.backend.app.programmes.domain.models import Programme
from src.backend.app.identity.domain.models import DEFAULT_ORGANIZATION_ID, Organization
from src.backend.app.reconciliation.api.router import (
    AddSublot,
    DeliveryCommand,
    DispatchCommand,
    ReconcileCommand,
    ShipmentCreate,
    add_sublot,
    create_shipment,
    deliver,
    dispatch,
    reconcile,
)
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation
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
    if session.get(Organization, DEFAULT_ORGANIZATION_ID) is None:
        session.add(Organization(id=DEFAULT_ORGANIZATION_ID, name="KoroFarm Demo Organization", slug="korofarm-demo"))
        session.flush()
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
    """Create a deterministic, visibly synthetic demo-day operating state.

    The stable hero requirement remains the entry point, while the surrounding
    records exercise programme rollups, portfolio health, recovery, receiving,
    quality grading, economics, risk, and the operational registries.
    """
    if session.get(Requirement, DEMO_REQUIREMENT_ID) is not None:
        return DEMO_REQUIREMENT_ID
    if session.get(Organization, DEFAULT_ORGANIZATION_ID) is None:
        session.add(Organization(id=DEFAULT_ORGANIZATION_ID, name="KoroFarm Demo Organization", slug="korofarm-demo"))
        session.flush()
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

    buyers = [
        Buyer(id=UUID("00000000-0000-0000-0000-000000000011"), name="Kingston Fresh Markets (Synthetic)",
              buyer_type="RETAIL", destination="Kingston, Jamaica"),
        Buyer(id=UUID("00000000-0000-0000-0000-000000000012"), name="Caribbean Produce Export (Synthetic)",
              buyer_type="EXPORTER", destination="Bridgetown, Barbados"),
    ]
    session.add_all(buyers)
    session.flush()
    programmes = [
        Programme(id=UUID("00000000-0000-0000-0000-000000000101"), buyer_id=DEMO_BUYER_ID,
                  name="Resort ginger assurance (Synthetic)", commodity_scope="GINGER", start_date=date(2026, 9, 1),
                  end_date=date(2026, 12, 31)),
        Programme(id=UUID("00000000-0000-0000-0000-000000000102"), buyer_id=buyers[0].id,
                  name="Kingston retail continuity (Synthetic)", commodity_scope="GINGER", start_date=date(2026, 9, 1),
                  end_date=date(2027, 3, 31)),
        Programme(id=UUID("00000000-0000-0000-0000-000000000103"), buyer_id=buyers[1].id,
                  name="Regional export readiness (Synthetic)", commodity_scope="GINGER", start_date=date(2026, 9, 1),
                  end_date=date(2027, 6, 30)),
    ]
    session.add_all(programmes)
    hero = session.get(Requirement, DEMO_REQUIREMENT_ID)
    hero.programme_id = programmes[0].id

    # Eight additional farmers and sixteen lots bring the portfolio to
    # 16 farmers and 24 production lots without implying live verification.
    additional_parishes = ["Manchester", "St. Elizabeth", "Clarendon", "St. Ann"]
    for farmer_index in range(8, 16):
        farmer_id = UUID(f"00000000-0000-0000-0001-{farmer_index + 1:012d}")
        farmer = Farmer(id=farmer_id, name=f"Demo Farmer {farmer_index + 1}",
                        parish=additional_parishes[farmer_index % 4])
        session.add(farmer)
        session.flush()
        for lot_sequence in range(2):
            lot_number = 9 + (farmer_index - 8) * 2 + lot_sequence
            lot_id = UUID(f"00000000-0000-0000-0002-{lot_number:012d}")
            lot = ProductionLot(
                id=lot_id, farmer_id=farmer_id, crop=Crop.GINGER,
                harvest_start=date(2026, 9, 8) + timedelta(days=lot_sequence * 7),
                harvest_end=date(2026, 11, 30), expected_quantity_kg=Decimal("270"),
                available_quantity_kg=Decimal("250"), reserved_quantity_kg=Decimal("0"),
                quality_grade_estimate=Grade.A, availability_confidence=(
                    AvailabilityConfidence.HIGH if lot_number % 3 else AvailabilityConfidence.MEDIUM
                ), parish=farmer.parish, status=ProductionLotStatus.AVAILABLE,
                last_verified_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            )
            session.add(lot)
            session.flush()
            session.add(LotCostInput(
                production_lot_id=lot.id,
                farmgate_price_per_kg_jmd=Decimal(275 + (lot_number % 6) * 7),
                pickup_cost_jmd=Decimal(240 + (lot_number % 4) * 25),
                handling_grading_cost_per_kg_jmd=Decimal("22"),
                packaging_cost_per_kg_jmd=Decimal("12"),
                transport_cost_jmd=Decimal(325 + (lot_number % 3) * 40),
                expected_rejection_pct=Decimal("0.02") if lot_number % 4 else Decimal("0.04"),
            ))
    session.commit()

    requirement_specs = [
        (501, buyers[0].id, programmes[1].id, "400", date(2026, 9, 15), date(2026, 9, 22), True),
        (502, buyers[0].id, programmes[1].id, "400", date(2026, 9, 22), date(2026, 9, 30), True),
        (503, buyers[1].id, programmes[2].id, "400", date(2026, 10, 1), date(2026, 10, 10), True),
        (504, DEMO_BUYER_ID, programmes[0].id, "400", date(2026, 10, 10), date(2026, 10, 20), True),
        (505, buyers[1].id, programmes[2].id, "400", date(2026, 10, 20), date(2026, 10, 31), True),
        # Deliberately exceeds residual supply to exercise an honest AT_RISK state.
        (506, buyers[0].id, programmes[1].id, "2000", date(2026, 11, 1), date(2026, 11, 30), True),
        # Deliberately left unplanned for the planning queue.
        (507, buyers[1].id, programmes[2].id, "300", date(2026, 12, 1), date(2026, 12, 15), False),
    ]
    for suffix, buyer_id, programme_id, quantity, window_start, window_end, should_plan in requirement_specs:
        requirement = Requirement(
            id=UUID(f"00000000-0000-0000-0000-{suffix:012d}"), buyer_id=buyer_id,
            programme_id=programme_id, crop=Crop.GINGER, grade=Grade.A,
            required_quantity_kg=Decimal(quantity), delivery_window_start=window_start,
            delivery_window_end=window_end,
        )
        session.add(requirement)
        session.commit()
        if should_plan:
            finalize_plan(session, requirement.id)
            session.commit()

    # A completed recovery proves loss handling and cost/risk re-snapshotting.
    hero_allocation = session.scalar(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == DEMO_REQUIREMENT_ID,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
    ).order_by(SupplyAllocation.production_lot_id))
    dropout(session, hero_allocation.id, "synthetic weather disruption", "demo-hero-dropout")
    session.commit()

    # A completed institutional trade makes the shipment, delivery,
    # reconciliation, traceability, and trade-passport surfaces demonstrable.
    completed_requirement_id = UUID("00000000-0000-0000-0000-000000000503")
    accepted_sublot_ids: list[UUID] = []
    completed_allocations = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == completed_requirement_id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
    ).order_by(SupplyAllocation.production_lot_id)).all()
    for index, allocation in enumerate(completed_allocations, start=1):
        receipt = receive(
            session, allocation.id, DEMO_NODE_ID, allocation.quantity_kg,
            datetime(2026, 10, 5, 13, index, tzinfo=timezone.utc),
            f"synthetic://receipt/demo-completed-503-{index}", f"demo-completed-receipt-{index}",
        )
        graded = grade(
            session, UUID(receipt["received_sublot_id"]), allocation.quantity_kg, Decimal("0"), Grade.A,
            None, f"synthetic://inspection/demo-completed-503-{index}", f"demo-completed-grade-{index}",
        )
        accepted_sublot_ids.append(UUID(graded["received_sublot_id"]))
    session.commit()
    shipment_result = create_shipment(
        completed_requirement_id,
        ShipmentCreate(fulfilment_node_id=DEMO_NODE_ID, reference="SYN-DEMO-503"),
        idempotency_key="demo-completed-shipment",
        session=session,
    )
    shipment_id = UUID(shipment_result["shipment_id"])
    for index, sublot_id in enumerate(accepted_sublot_ids, start=1):
        add_sublot(
            shipment_id, AddSublot(received_sublot_id=sublot_id),
            idempotency_key=f"demo-completed-shipment-sublot-{index}", session=session,
        )
    dispatch(
        shipment_id, DispatchCommand(evidence_reference="synthetic://dispatch/demo-completed-503"),
        idempotency_key="demo-completed-dispatch", session=session,
    )
    deliver(
        shipment_id,
        DeliveryCommand(
            delivered_quantity_kg=Decimal("400"),
            delivered_at=datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc),
            delivery_evidence_reference="synthetic://delivery/demo-completed-503",
            buyer_confirmed=True,
            buyer_confirmation_evidence="synthetic://buyer-confirmation/demo-completed-503",
        ),
        idempotency_key="demo-completed-delivery",
        session=session,
    )
    reconcile(
        completed_requirement_id,
        ReconcileCommand(verification_evidence_reference="synthetic://verification/demo-completed-503"),
        idempotency_key="demo-completed-reconciliation",
        session=session,
    )

    # A partial rejection proves physical receiving, quality attribution, and
    # non-punitive recovery. Evidence references are explicitly synthetic.
    quality_requirement_id = UUID("00000000-0000-0000-0000-000000000502")
    quality_allocation = session.scalar(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == quality_requirement_id,
        SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED,
    ).order_by(SupplyAllocation.quantity_kg.desc(), SupplyAllocation.production_lot_id))
    receipt = receive(session, quality_allocation.id, DEMO_NODE_ID, Decimal("30"),
                      datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
                      "synthetic://receipt/demo-quality-502", "demo-quality-receipt")
    grade(session, UUID(receipt["received_sublot_id"]), Decimal("15"), Decimal("15"), Grade.A,
          "synthetic handling damage", "synthetic://inspection/demo-quality-502", "demo-quality-grade")
    session.commit()
    return DEMO_REQUIREMENT_ID


if __name__ == "__main__":
    session = create_session_factory()()
    try:
        seed(session)
    finally:
        session.close()
