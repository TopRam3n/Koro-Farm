"""KOROFARM_MARKETPLACE_REQUESTS_PHASE1: Buyer requests and farmer visibility.

Farmer offers/commitments are deliberately deferred to phase 2; no quantities
are committed or reserved by these endpoints.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.domain.common import Crop, Grade
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.main_dependencies import get_session

router = APIRouter(prefix="/marketplace/requests", tags=["buyer farmer requests"])


class CreateBuyerRequest(BaseModel):
    crop: Crop
    grade: Grade
    required_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    delivery_window_start: date
    delivery_window_end: date

    @model_validator(mode="after")
    def check_dates(self):
        if self.delivery_window_end < self.delivery_window_start:
            raise ValueError("delivery end cannot precede start")
        if self.delivery_window_start < date.today():
            raise ValueError("delivery start cannot be in the past")
        return self


def request_row(requirement: Requirement, buyer: Buyer) -> dict:
    return {
        "id": str(requirement.id),
        "buyer_name": buyer.name,
        "buyer_id": str(buyer.id),
        "crop": requirement.crop.value,
        "grade": requirement.grade.value,
        "required_quantity_kg": str(requirement.required_quantity_kg),
        "delivery_window_start": requirement.delivery_window_start,
        "delivery_window_end": requirement.delivery_window_end,
        "lifecycle_status": requirement.lifecycle_status.value,
        "supply_health": requirement.supply_health.value,
    }


@router.get("")
def list_buyer_farmer_requests(
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    if context.role not in {RoleCode.BUYER, RoleCode.FARMER, RoleCode.PLATFORM_ADMIN}:
        raise HTTPException(403, "buyer or farmer membership required")
    statement = select(Requirement, Buyer).join(Buyer, Buyer.id == Requirement.buyer_id).where(
        Buyer.organization_id == context.organization_id
    )
    if context.role == RoleCode.BUYER:
        if context.buyer_id is None:
            raise HTTPException(403, "buyer account not linked")
        statement = statement.where(Requirement.buyer_id == context.buyer_id)
    elif context.role == RoleCode.FARMER:
        if context.farmer_id is None:
            raise HTTPException(403, "farmer account not linked")
        statement = statement.where(Requirement.lifecycle_status == RequirementLifecycleStatus.ACTIVE)
    rows = session.execute(statement.order_by(Requirement.created_at.desc(), Requirement.id).limit(100)).all()
    return {"items": [request_row(requirement, buyer) for requirement, buyer in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_buyer_request(
    payload: CreateBuyerRequest,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    if context.role != RoleCode.BUYER or context.buyer_id is None:
        raise HTTPException(403, "linked buyer account required")
    buyer = session.scalar(select(Buyer).where(
        Buyer.id == context.buyer_id, Buyer.organization_id == context.organization_id
    ))
    if buyer is None:
        raise HTTPException(404, "buyer not found")
    requirement = Requirement(
        buyer_id=buyer.id, crop=payload.crop, grade=payload.grade,
        required_quantity_kg=payload.required_quantity_kg,
        delivery_window_start=payload.delivery_window_start,
        delivery_window_end=payload.delivery_window_end,
        lifecycle_status=RequirementLifecycleStatus.DRAFT,
    )
    session.add(requirement)
    session.commit()
    session.refresh(requirement)
    return request_row(requirement, buyer)


@router.post("/{request_id}/publish")
def publish_buyer_request(
    request_id: UUID,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    if context.role != RoleCode.BUYER or context.buyer_id is None:
        raise HTTPException(403, "linked buyer account required")
    row = session.execute(select(Requirement, Buyer).join(Buyer).where(
        Requirement.id == request_id,
        Requirement.buyer_id == context.buyer_id,
        Buyer.organization_id == context.organization_id,
    ).with_for_update()).one_or_none()
    if row is None:
        raise HTTPException(404, "request not found")
    requirement, buyer = row
    if requirement.lifecycle_status != RequirementLifecycleStatus.DRAFT:
        raise HTTPException(409, "only draft requests can be published")
    if requirement.delivery_window_start < date.today():
        raise HTTPException(422, "delivery window has already started")
    requirement.lifecycle_status = RequirementLifecycleStatus.ACTIVE
    requirement.version += 1
    session.commit()
    session.refresh(requirement)
    return request_row(requirement, buyer)
