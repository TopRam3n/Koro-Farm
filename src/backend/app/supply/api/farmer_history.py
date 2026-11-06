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

# PHASE5_FARMER_HISTORY_DIRECTORY: never exposes farmer directory to farmer or buyer accounts.
@router.get("/history-directory")
def farmer_history_directory(
    q: str = "",
    offset: int = 0,
    limit: int = 24,
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    from sqlalchemy import func, or_

    staff_roles = {
        RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN,
        RoleCode.PROCUREMENT_MANAGER, RoleCode.SUPPLY_COORDINATOR,
        RoleCode.WAREHOUSE_OPERATOR, RoleCode.AUDITOR,
    }
    if ctx.role not in staff_roles:
        raise HTTPException(status_code=403, detail="staff access required")
    if offset < 0 or not 1 <= limit <= 100 or len(q.strip()) > 100:
        raise HTTPException(status_code=422, detail="invalid directory pagination or search")

    search = q.strip()
    conditions = [Farmer.organization_id == ctx.organization_id]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        conditions.append(or_(Farmer.name.ilike(pattern, escape="\\"), Farmer.parish.ilike(pattern, escape="\\")))

    aggregate = (
        select(
            HistoricalProduction.farmer_id.label("farmer_id"),
            func.count(HistoricalProduction.id).label("record_count"),
            func.min(HistoricalProduction.production_year).label("first_year"),
            func.max(HistoricalProduction.production_year).label("last_year"),
        )
        .group_by(HistoricalProduction.farmer_id)
        .subquery()
    )
    total = session.scalar(select(func.count(Farmer.id)).where(*conditions)) or 0
    statement = (
        select(Farmer, func.coalesce(aggregate.c.record_count, 0),
               aggregate.c.first_year, aggregate.c.last_year)
        .outerjoin(aggregate, aggregate.c.farmer_id == Farmer.id)
        .where(*conditions)
        .order_by(Farmer.name, Farmer.id)
        .offset(offset)
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return {
        "items": [{
            "id": str(farmer.id), "name": farmer.name,
            "parish": farmer.parish, "active": farmer.active,
            "history_record_count": int(record_count),
            "first_year": first_year, "last_year": last_year,
        } for farmer, record_count, first_year, last_year in rows],
        "total": int(total), "offset": offset, "limit": limit,
    }
