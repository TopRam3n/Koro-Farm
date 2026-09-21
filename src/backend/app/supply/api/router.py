from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode

router = APIRouter(prefix="/production-lots", tags=["production-lots"])


class ProductionLotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    farmer_id: UUID
    crop: Crop
    harvest_start: date
    harvest_end: date
    expected_quantity_kg: Decimal
    available_quantity_kg: Decimal
    reserved_quantity_kg: Decimal
    quality_grade_estimate: Grade
    availability_confidence: AvailabilityConfidence
    parish: str
    status: ProductionLotStatus
    last_verified_at: datetime
    version: int


@router.get("", response_model=list[ProductionLotRead],
            dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def list_production_lots(session: Session = Depends(get_session),
                         context: AuthorizationContext = Depends(get_authorization_context)) -> list[ProductionLot]:
    statement = select(ProductionLot).join(Farmer).where(Farmer.organization_id == context.organization_id)
    if context.role == RoleCode.FARMER:
        if context.farmer_id is None:
            return []
        statement = statement.where(ProductionLot.farmer_id == context.farmer_id)
    return list(session.scalars(statement.order_by(ProductionLot.harvest_start, ProductionLot.id)))


@router.get("/{lot_id}", response_model=ProductionLotRead,
            dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def get_production_lot(lot_id: UUID, session: Session = Depends(get_session),
                       context: AuthorizationContext = Depends(get_authorization_context)) -> ProductionLot:
    statement = select(ProductionLot).join(Farmer).where(
        ProductionLot.id == lot_id, Farmer.organization_id == context.organization_id
    )
    if context.role == RoleCode.FARMER:
        statement = statement.where(ProductionLot.farmer_id == context.farmer_id)
    lot = session.scalar(statement)
    if lot is None:
        raise HTTPException(status_code=404, detail="production lot not found")
    return lot
