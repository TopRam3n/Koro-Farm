"""Repeatable deterministic Supply Assurance recovery demonstration."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.assurance.application.recovery import dropout
from app.assurance.domain.models import DomainEvent
from app.risk.domain.models import RiskSnapshot
from app.demand.application.services import create_requirement
from app.demand.domain.models import Buyer, Requirement
from app.domain.common import Crop, Grade
from app.infrastructure.database.base import Base
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from app.economics.domain.models import LotCostInput
from app.domain.common import AvailabilityConfidence
from app.supply.application.planner import finalize_plan
from app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation


def main() -> None:
    db_path = Path(".demo-recovery.sqlite").resolve()
    db_path.unlink(missing_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        buyer = Buyer(name="Jamaican Hotel", buyer_type="HOTEL", destination="Montego Bay")
        session.add(buyer); session.flush()
        # Eight identical 80kg lots make the 80kg disruption and 100kg standby deterministic.
        for number in range(8):
            farmer = Farmer(name=f"Demo farmer {number + 1}", parish=("Clarendon" if number % 2 else "Manchester"))
            session.add(farmer); session.flush()
            lot = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date.today() + timedelta(days=4),
                harvest_end=date.today() + timedelta(days=11), expected_quantity_kg=Decimal("80"), available_quantity_kg=Decimal("80"),
                reserved_quantity_kg=Decimal("0"), quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
                parish=farmer.parish, status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
            session.add(lot); session.flush()
            session.add(LotCostInput(production_lot_id=lot.id, farmgate_price_per_kg_jmd=Decimal("300"), pickup_cost_jmd=Decimal("100"),
                handling_grading_cost_per_kg_jmd=Decimal("20"), packaging_cost_per_kg_jmd=Decimal("10"), transport_cost_jmd=Decimal("100"), expected_rejection_pct=Decimal("0.02")))
        session.commit()
        requirement = create_requirement(session, Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
            required_quantity_kg=Decimal("500"), delivery_window_start=date.today() + timedelta(days=5),
            delivery_window_end=date.today() + timedelta(days=10)))
        plan = finalize_plan(session, requirement.id)
        initial_risk = session.scalar(select(RiskSnapshot).where(RiskSnapshot.supply_plan_id == plan.plan_id))
        print("500KG GINGER REQUIREMENT\n========================\n\nINITIAL PLAN")
        print(f"Committed: {plan.committed_quantity_kg}kg | Standby: {plan.standby_quantity_kg}kg | Supply health: COVERED")
        print(f"Supply risk: {initial_risk.risk_label.value} | Largest farmer share: {initial_risk.largest_farmer_share_pct}% | Largest parish share: {initial_risk.largest_parish_share_pct}%")
        print(f"Standby coverage: {initial_risk.standby_coverage_pct}% | Replacement depth: {initial_risk.replacement_depth_kg}kg")
        print(f"Original landed cost: J${plan.total_landed_cost_jmd}")
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement.id,
            SupplyAllocation.role == AllocationRole.COMMITTED, SupplyAllocation.status == AllocationStatus.COMMITTED,
            SupplyAllocation.quantity_kg == Decimal("80")).order_by(SupplyAllocation.id))
        result = dropout(session, allocation.id, "crop_failure", f"demo-{uuid4()}")
        print(f"\nDISRUPTION\nFarmer allocation lost: {result['lost_kg']}kg | committed coverage: 500kg -> 420kg | health: COVERED -> AT_RISK")
        print(f"\nRECOVERY COMPLETE\nActivated standby: {result['standby_activated_kg']}kg | committed coverage: 420kg -> {result['committed_kg']}kg | health: AT_RISK -> {result['supply_health']}")
        from app.economics.domain.models import CostSnapshot
        snapshots = list(session.scalars(select(CostSnapshot).order_by(CostSnapshot.created_at)))
        premium = snapshots[-1].total_landed_cost_jmd - snapshots[0].total_landed_cost_jmd
        recovered_risk = session.scalar(select(RiskSnapshot).order_by(RiskSnapshot.plan_version.desc()))
        print(f"Supply risk: {initial_risk.risk_label.value} -> {recovered_risk.risk_label.value}; standby coverage: {initial_risk.standby_coverage_pct}% -> {recovered_risk.standby_coverage_pct}%")
        print(f"Recovered landed cost: J${snapshots[-1].total_landed_cost_jmd} | recovery cost delta: J${premium}")
        print("\nAudit events:")
        for event in session.scalars(select(DomainEvent).order_by(DomainEvent.occurred_at, DomainEvent.id)):
            print(f"  {event.event_type}: {event.payload}")
    finally:
        session.close(); engine.dispose(); db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
