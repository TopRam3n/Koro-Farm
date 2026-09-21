from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.demand.application.services import create_requirement
from src.backend.app.demand.domain.models import Buyer, BuyerOrderChange, Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.domain.common import Crop, DateWindow, Grade, QuantityKg
from src.backend.app.main_dependencies import get_session
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor

router = APIRouter(prefix="/requirements", tags=["requirements"])


class RequirementCreate(BaseModel):
    buyer_id: UUID
    programme_id: UUID | None = None
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
    programme_id: UUID | None
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


@router.post("", response_model=RequirementRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_CREATE))])
def post_requirement(payload: RequirementCreate, session: Session = Depends(get_session),
                     context: AuthorizationContext = Depends(get_authorization_context)) -> Requirement:
    buyer = session.scalar(select(Buyer).where(Buyer.id == payload.buyer_id,
                                                Buyer.organization_id == context.organization_id))
    if buyer is None:
        raise HTTPException(status_code=404, detail="buyer not found")
    if payload.programme_id:
        from src.backend.app.programmes.domain.models import Programme
        programme = session.get(Programme, payload.programme_id)
        if programme is None or programme.buyer_id != payload.buyer_id:
            raise HTTPException(status_code=422, detail="programme does not belong to buyer")
    if payload.trade_corridor_id:
        corridor = session.scalar(select(TradeCorridor).where(
            TradeCorridor.id == payload.trade_corridor_id,
            TradeCorridor.organization_id == context.organization_id,
        ))
        if corridor is None or not corridor.active:
            raise HTTPException(status_code=422, detail="trade corridor is not active")
    try:
        QuantityKg(payload.required_quantity_kg)
        requirement = Requirement(**payload.model_dump())
        return create_requirement(session, requirement)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[RequirementRead],
            dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def list_requirements(
    supply_health: SupplyHealth | None = None,
    lifecycle_status: RequirementLifecycleStatus | None = None,
    buyer_id: UUID | None = None,
    programme_id: UUID | None = None,
    offset: int = 0,
    limit: int = 50,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> list[Requirement]:
    if offset < 0 or limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="offset must be non-negative and limit must be between 1 and 200")
    statement = select(Requirement).join(Buyer).where(Buyer.organization_id == context.organization_id)
    if supply_health is not None:
        statement = statement.where(Requirement.supply_health == supply_health)
    if lifecycle_status is not None:
        statement = statement.where(Requirement.lifecycle_status == lifecycle_status)
    if buyer_id is not None:
        statement = statement.where(Requirement.buyer_id == buyer_id)
    if programme_id is not None:
        statement = statement.where(Requirement.programme_id == programme_id)
    return list(session.scalars(statement.order_by(Requirement.created_at.desc(), Requirement.id).offset(offset).limit(limit)))


@router.get("/{requirement_id}", response_model=RequirementRead,
            dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def get_requirement(requirement_id: UUID, session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> Requirement:
    requirement = session.scalar(select(Requirement).join(Buyer).where(
        Requirement.id == requirement_id, Buyer.organization_id == context.organization_id
    ))
    if requirement is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return requirement


@router.post("/{requirement_id}/buyer-change",
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_UPDATE))])
def buyer_change(requirement_id: UUID, payload: BuyerChangeCommand, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    requirement = session.scalar(select(Requirement).join(Buyer).where(
        Requirement.id == requirement_id, Buyer.organization_id == context.organization_id
    ))
    if requirement is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    previous = requirement.required_quantity_kg
    if payload.new_quantity_kg == previous:
        raise HTTPException(status_code=422, detail="buyer change must alter the quantity")
    change = BuyerOrderChange(requirement_id=requirement.id, previous_quantity_kg=previous, new_quantity_kg=payload.new_quantity_kg, reason=payload.reason)
    requirement.required_quantity_kg = payload.new_quantity_kg
    session.add(change); session.commit()
    return {"requirement_id": str(requirement.id), "previous_quantity_kg": str(previous), "new_quantity_kg": str(payload.new_quantity_kg), "attribution": "BUYER_CHANGE", "farmer_reliability_impact": "NONE"}
