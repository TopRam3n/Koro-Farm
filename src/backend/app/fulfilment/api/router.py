from datetime import datetime
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Requirement
from src.backend.app.domain.common import Grade
from src.backend.app.fulfilment.application.services import grade, receive
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation
from src.backend.app.supply.domain.models import Farmer, ProductionLot

router = APIRouter(tags=["fulfilment"])

class ReceiveCommand(BaseModel):
    allocation_id: UUID; fulfilment_node_id: UUID; received_quantity_kg: Decimal; received_at: datetime; receipt_evidence_reference: str | None = None
class GradeCommand(BaseModel):
    accepted_quantity_kg: Decimal; rejected_quantity_kg: Decimal; assigned_grade: Grade | None = None; rejection_reason: str | None = None; inspection_evidence_reference: str | None = None

@router.post("/sublots/receive")
def post_receive(payload: ReceiveCommand, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    try: return receive(session, payload.allocation_id, payload.fulfilment_node_id, payload.received_quantity_kg, payload.received_at, payload.receipt_evidence_reference, idempotency_key)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc

@router.post("/sublots/{sublot_id}/grade")
def post_grade(sublot_id: UUID, payload: GradeCommand, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    try: return grade(session, sublot_id, payload.accepted_quantity_kg, payload.rejected_quantity_kg, payload.assigned_grade, payload.rejection_reason, payload.inspection_evidence_reference, idempotency_key)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc

@router.get("/requirements/{requirement_id}/fulfilment")
def fulfilment_summary(requirement_id: UUID, session: Session = Depends(get_session)) -> dict:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None: raise HTTPException(404, "requirement not found")
    rows = session.execute(select(ReceivedSublot).join(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement_id)).scalars().all()
    committed = session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(SupplyAllocation.requirement_id == requirement_id, SupplyAllocation.role == AllocationRole.COMMITTED, SupplyAllocation.status == AllocationStatus.COMMITTED)) or Decimal("0")
    received = sum((x.received_quantity_kg for x in rows), Decimal("0")); accepted = sum((x.accepted_quantity_kg for x in rows), Decimal("0")); rejected = sum((x.rejected_quantity_kg for x in rows), Decimal("0"))
    return {"required_kg": str(requirement.required_quantity_kg), "committed_kg": str(committed), "received_kg": str(received), "accepted_kg": str(accepted), "rejected_kg": str(rejected), "accepted_shortfall_kg": str(max(requirement.required_quantity_kg - accepted, Decimal("0")))}

@router.get("/sublots/{sublot_id}/traceability")
def traceability(sublot_id: UUID, session: Session = Depends(get_session)) -> dict:
    row = session.execute(select(ReceivedSublot, SupplyAllocation, ProductionLot, Farmer).join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id).join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id).join(Farmer, Farmer.id == ProductionLot.farmer_id).where(ReceivedSublot.id == sublot_id)).one_or_none()
    if row is None: raise HTTPException(404, "received sublot not found")
    sublot, allocation, lot, farmer = row
    return {"received_sublot_id": str(sublot.id), "allocation_id": str(allocation.id), "production_lot_id": str(lot.id), "farmer_id": str(farmer.id), "farmer_name": farmer.name, "crop": lot.crop.value, "received_quantity_kg": str(sublot.received_quantity_kg), "accepted_quantity_kg": str(sublot.accepted_quantity_kg), "assigned_grade": sublot.assigned_grade.value if sublot.assigned_grade else None}
