"""Repeatable physical-quality failure and supply-recovery demonstration."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.backend.app.assurance.application.recovery import _coverage
from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.application.services import grade, receive
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.supply.application.planner import PlannerConfig, finalize_plan
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation


def main() -> None:
    db_path = Path(".demo-quality-recovery.sqlite").resolve()
    db_path.unlink(missing_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        buyer = Buyer(name="Harbour View Hotel (Synthetic)", buyer_type="HOTEL", destination="Montego Bay")
        node = FulfilmentNode(name="Montego Bay Collection Hub (Synthetic)", node_type="COLLECTION_CENTRE", parish="St. James")
        session.add_all([buyer, node]); session.flush()
        today = date.today()
        # Five 100kg Grade-A commitments plus one 50kg pre-authorized reserve.
        for number, quantity in enumerate([100, 100, 100, 100, 100, 50]):
            farmer = Farmer(name=f"Demo farmer {number + 1}", parish=("Manchester" if number % 2 else "Clarendon"))
            session.add(farmer); session.flush()
            lot = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER,
                harvest_start=today + timedelta(days=3), harvest_end=today + timedelta(days=10),
                expected_quantity_kg=Decimal(quantity), available_quantity_kg=Decimal(quantity), reserved_quantity_kg=Decimal("0"),
                quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
                parish=farmer.parish, status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
            session.add(lot); session.flush()
            session.add(LotCostInput(production_lot_id=lot.id, farmgate_price_per_kg_jmd=Decimal("300"),
                pickup_cost_jmd=Decimal("100"), handling_grading_cost_per_kg_jmd=Decimal("20"),
                packaging_cost_per_kg_jmd=Decimal("10"), transport_cost_jmd=Decimal("100"), expected_rejection_pct=Decimal("0.02")))
        session.commit()
        requirement = create_requirement(session, Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
            required_quantity_kg=Decimal("500"), delivery_window_start=today + timedelta(days=4), delivery_window_end=today + timedelta(days=9)))
        plan = finalize_plan(session, requirement.id, PlannerConfig(standby_target_pct=Decimal("0.10")))
        allocation = session.scalar(select(SupplyAllocation).where(
            SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.COMMITTED,
            SupplyAllocation.status == AllocationStatus.COMMITTED, SupplyAllocation.quantity_kg == Decimal("100")))
        receipt = receive(session, allocation.id, node.id, Decimal("100"), datetime.now(timezone.utc), "demo-receipt-001", str(uuid4()))
        result = grade(session, receipt["received_sublot_id"], Decimal("70"), Decimal("30"), Grade.B,
            "GRADE_MISMATCH", "demo-inspection-001", str(uuid4()))
        print("QUALITY FAILURE RECOVERY DEMO\n=============================\n")
        print(f"Initial committed supply: {plan.committed_quantity_kg}kg; standby: {plan.standby_quantity_kg}kg")
        print("Received 100kg from one committed lot: 70kg accepted Grade A, 30kg rejected / Grade B")
        print(f"Effective Grade-A coverage after inspection: 470kg")
        print(f"Reserve activated: {result['recovery']['standby_activated_kg']}kg")
        print(f"Effective Grade-A committed coverage after recovery: {_coverage(session, requirement.id)}kg")
        print(f"Recovery status: {result['recovery']['status']}")
    finally:
        session.close(); engine.dispose(); db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
