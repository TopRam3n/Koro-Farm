from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, BuyerOrderChange, Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.domain.common import Crop, DateWindow, Grade, QuantityKg
from src.backend.app.main_dependencies import get_session
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor

router = APIRouter(prefix="/requirements", tags=["requirements"])


class RequirementCreate(BaseModel):
    buyer_id: UUID
    trade_corridor_id: UUID | None = None
    crop: Crop
    grade: Grade
    required_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    delivery_window_start: date
    delivery_window_end: date

    @field_validator("delivery_window_end")
    @classmethod
    def valid_window(cls, end: date, info):
        start = info.data.get("delivery_window_start")
        if start:
            DateWindow(start, end)
        return end


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    buyer_id: UUID
    trade_corridor_id: UUID | None
    crop: Crop
    grade: Grade
    required_quantity_kg: Decimal
    delivery_window_start: date
    delivery_window_end: date
    lifecycle_status: RequirementLifecycleStatus
    supply_health: SupplyHealth
    plan_version: int
    version: int


class BuyerChangeCommand(BaseModel):
    new_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


@router.post("", response_model=RequirementRead, status_code=status.HTTP_201_CREATED)
def post_requirement(payload: RequirementCreate, session: Session = Depends(get_session)) -> Requirement:
    if session.get(Buyer, payload.buyer_id) is None:
        raise HTTPException(status_code=404, detail="buyer not found")
    if payload.trade_corridor_id:
        corridor = session.get(TradeCorridor, payload.trade_corridor_id)
        if corridor is None or not corridor.active:
            raise HTTPException(status_code=422, detail="trade corridor is not active")
    try:
        QuantityKg(payload.required_quantity_kg)
        requirement = Requirement(**payload.model_dump())
        return create_requirement(session, requirement)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{requirement_id}", response_model=RequirementRead)
def get_requirement(requirement_id: UUID, session: Session = Depends(get_session)) -> Requirement:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return requirement


@router.post("/{requirement_id}/buyer-change")
def buyer_change(requirement_id: UUID, payload: BuyerChangeCommand, session: Session = Depends(get_session)) -> dict:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    previous = requirement.required_quantity_kg
    if payload.new_quantity_kg == previous:
        raise HTTPException(status_code=422, detail="buyer change must alter the quantity")
    change = BuyerOrderChange(requirement_id=requirement.id, previous_quantity_kg=previous, new_quantity_kg=payload.new_quantity_kg, reason=payload.reason)
    requirement.required_quantity_kg = payload.new_quantity_kg
    session.add(change); session.commit()
    return {"requirement_id": str(requirement.id), "previous_quantity_kg": str(previous), "new_quantity_kg": str(payload.new_quantity_kg), "attribution": "BUYER_CHANGE", "farmer_reliability_impact": "NONE"}
