from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus

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


@router.get("", response_model=list[ProductionLotRead])
def list_production_lots(session: Session = Depends(get_session)) -> list[ProductionLot]:
    return list(session.scalars(select(ProductionLot).order_by(ProductionLot.harvest_start, ProductionLot.id)))


@router.get("/{lot_id}", response_model=ProductionLotRead)
def get_production_lot(lot_id: UUID, session: Session = Depends(get_session)) -> ProductionLot:
    lot = session.get(ProductionLot, lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="production lot not found")
    return lot
