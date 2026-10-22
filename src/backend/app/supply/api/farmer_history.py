"""Authenticated, tenant-scoped read-only farmer profile/history endpoints."""
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from app.identity.domain.permissions import PermissionCode, RoleCode
from app.main_dependencies import get_session
from app.supply.domain.history_models import Farm, FarmerCrop, HistoricalProduction
from app.supply.domain.models import Farmer

router = APIRouter(prefix="/farmers", tags=["farmer history"], dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])


class FarmRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    parish: str
    active: bool


class FarmerCropRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    crop: str
    active: bool


class HistoricalProductionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    crop: str
    production_year: int
    production_quarter: int
    production_kg: Decimal
    data_source: str
    is_simulated: bool


class FarmerProfileRead(BaseModel):
    id: UUID
    name: str
    parish: str
    active: bool
    farms: list[FarmRead]
    crops: list[FarmerCropRead]


def _authorized_farmer(farmer_id: UUID, session: Session, ctx: AuthorizationContext) -> Farmer:
    statement = select(Farmer).where(Farmer.id == farmer_id, Farmer.organization_id == ctx.organization_id)
    if ctx.role == RoleCode.FARMER:
        statement = statement.where(Farmer.id == ctx.farmer_id)
    farmer = session.scalar(statement)
    if farmer is None:
        raise HTTPException(status_code=404, detail="farmer not found")
    return farmer


@router.get("/{farmer_id}/profile", response_model=FarmerProfileRead)
def get_farmer_profile(farmer_id: UUID, session: Session = Depends(get_session),
                       ctx: AuthorizationContext = Depends(get_authorization_context)) -> FarmerProfileRead:
    farmer = _authorized_farmer(farmer_id, session, ctx)
    farms = session.scalars(select(Farm).where(Farm.farmer_id == farmer_id).order_by(Farm.name)).all()
    crops = session.scalars(select(FarmerCrop).where(FarmerCrop.farmer_id == farmer_id).order_by(FarmerCrop.crop)).all()
    return FarmerProfileRead(id=farmer.id, name=farmer.name, parish=farmer.parish, active=farmer.active,
                             farms=[FarmRead.model_validate(f) for f in farms],
                             crops=[FarmerCropRead.model_validate(c) for c in crops])


@router.get("/{farmer_id}/production-history", response_model=list[HistoricalProductionRead])
def get_farmer_history(farmer_id: UUID, year: int | None = None, crop: str | None = None,
                       session: Session = Depends(get_session),
                       ctx: AuthorizationContext = Depends(get_authorization_context)) -> list[HistoricalProductionRead]:
    _authorized_farmer(farmer_id, session, ctx)
    statement = select(HistoricalProduction).where(HistoricalProduction.farmer_id == farmer_id)
    if year is not None:
        statement = statement.where(HistoricalProduction.production_year == year)
    if crop is not None:
        statement = statement.where(HistoricalProduction.crop == crop)
    statement = statement.order_by(HistoricalProduction.production_year, HistoricalProduction.production_quarter, HistoricalProduction.crop)
    return [HistoricalProductionRead.model_validate(row) for row in session.scalars(statement)]
