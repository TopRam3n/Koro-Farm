from datetime import date, datetime, timezone
from uuid import UUID
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.backend.app.assurance.application.recovery import _coverage
from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, Requirement, SupplyHealth
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.application.services import grade, receive
from src.backend.app.fulfilment.domain.models import FulfilmentNode, InspectionStatus, ReceivedSublot
from src.backend.app.supply.application.planner import PlannerConfig, finalize_plan
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation


def test_receive_grade_idempotency_and_traceable_physical_separation(session):
    buyer = Buyer(name="Hotel", buyer_type="HOTEL", destination="JA"); node = FulfilmentNode(name="Hub", node_type="HUB", parish="St James")
    session.add_all([buyer, node]); session.flush()
    req = create_requirement(session, Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A, required_quantity_kg=Decimal("100"), delivery_window_start=date(2026, 9, 1), delivery_window_end=date(2026, 9, 2)))
    farmer = Farmer(name="Farmer", parish="Manchester"); session.add(farmer); session.flush()
    lot = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=date(2026,9,1), harvest_end=date(2026,9,2), expected_quantity_kg=Decimal("100"), available_quantity_kg=Decimal("100"), reserved_quantity_kg=Decimal("0"), quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH, parish="Manchester", status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc)); session.add(lot); session.flush()
    session.add(LotCostInput(production_lot_id=lot.id, farmgate_price_per_kg_jmd=1, pickup_cost_jmd=0, handling_grading_cost_per_kg_jmd=0, packaging_cost_per_kg_jmd=0, transport_cost_jmd=0, expected_rejection_pct=0)); session.commit()
    plan = finalize_plan(session, req.id, PlannerConfig(standby_target_pct=Decimal("0")))
    allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.supply_plan_id == plan.plan_id))
    receipt = receive(session, allocation.id, node.id, Decimal("100"), datetime.now(timezone.utc), "receipt-1", "r1")
    assert receive(session, allocation.id, node.id, Decimal("100"), datetime.now(timezone.utc), "receipt-1", "r1") == receipt
    result = grade(session, receipt["received_sublot_id"], Decimal("93"), Decimal("7"), Grade.B, "GRADE_MISMATCH", "inspection-1", "g1")
    assert result["inspection_status"] == InspectionStatus.PARTIALLY_ACCEPTED
    sublot = session.get(ReceivedSublot, UUID(receipt["received_sublot_id"]))
    assert sublot.assigned_grade == Grade.B and lot.quality_grade_estimate == Grade.A
    assert _coverage(session, req.id) == Decimal("100.000") and sublot.accepted_quantity_kg == Decimal("93")
    with pytest.raises(ValueError): grade(session, sublot.id, Decimal("100"), Decimal("0"), Grade.A, None, None, "g2")
