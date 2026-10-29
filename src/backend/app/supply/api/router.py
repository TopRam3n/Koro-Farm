from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event, remember, replay_or_none
from src.backend.app.domain.common import AvailabilityConfidence, DateWindow, Grade
from src.backend.app.domain.common.fields import CropCodeField
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.application.tenancy import tenant_idempotency_key
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.application.crops import require_active_crop
from src.backend.app.supply.domain.models import CapacityVerification, Farmer, ProductionLot, ProductionLotStatus

router = APIRouter(prefix="/production-lots", tags=["production-lots"])


class ProductionLotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    farmer_id: UUID
    farmer_name: str | None = None
    crop: str
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
    capacity_verification: CapacityVerification = CapacityVerification.UNSPECIFIED
    provenance_source: str | None = None
    attestation_method: str | None = None
    evidence_reference: str | None = None
    declared_at: datetime | None = None
    farmgate_price_per_kg_jmd: Decimal | None = None
    version: int


class Provenance(BaseModel):
    """Who reported the figures and how. Required whenever a coordinator records supply for a farmer."""
    provenance_source: str = Field(min_length=3, max_length=200, description="e.g. 'phone call with farmer', 'field visit'")
    attestation_method: str = Field(min_length=3, max_length=100, description="e.g. 'verbal', 'signed form', 'photo of crop'")
    evidence_reference: str | None = Field(default=None, max_length=500)


class ProductionLotCreate(Provenance):
    farmer_id: UUID
    crop: CropCodeField
    harvest_start: date
    harvest_end: date
    expected_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    available_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    quality_grade_estimate: Grade
    parish: str | None = Field(default=None, min_length=2, max_length=100)
    farmgate_price_per_kg_jmd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @field_validator("harvest_end")
    @classmethod
    def valid_window(cls, end: date, info):
        if start := info.data.get("harvest_start"):
            DateWindow(start, end)
        return end

    @model_validator(mode="after")
    def available_within_expected(self):
        if self.available_quantity_kg > self.expected_quantity_kg:
            raise ValueError("available quantity cannot exceed the expected harvest")
        return self


class ProductionLotUpdate(Provenance):
    expected_version: int = Field(ge=1)
    harvest_start: date | None = None
    harvest_end: date | None = None
    expected_quantity_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    available_quantity_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    quality_grade_estimate: Grade | None = None
    farmgate_price_per_kg_jmd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


def _costs(session: Session, lot_id: UUID) -> LotCostInput | None:
    return session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == lot_id))


def _read(session: Session, lot: ProductionLot, farmer: Farmer | None = None) -> ProductionLotRead:
    data = ProductionLotRead.model_validate(lot)
    farmer = farmer or session.get(Farmer, lot.farmer_id)
    data.farmer_name = farmer.name if farmer else None
    costs = _costs(session, lot.id)
    data.farmgate_price_per_kg_jmd = costs.farmgate_price_per_kg_jmd if costs else None
    return data


def _set_price(session: Session, lot: ProductionLot, price: Decimal) -> None:
    costs = _costs(session, lot.id)
    if costs is None:
        session.add(LotCostInput(production_lot_id=lot.id, farmgate_price_per_kg_jmd=price, pickup_cost_jmd=0,
                                 handling_grading_cost_per_kg_jmd=0, packaging_cost_per_kg_jmd=0, transport_cost_jmd=0,
                                 expected_rejection_pct=0))
    else:
        costs.farmgate_price_per_kg_jmd = price


@router.get("", response_model=list[ProductionLotRead],
            dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def list_production_lots(farmer_id: UUID | None = None, session: Session = Depends(get_session),
                         context: AuthorizationContext = Depends(get_authorization_context)) -> list[ProductionLotRead]:
    statement = select(ProductionLot, Farmer).join(Farmer).where(Farmer.organization_id == context.organization_id)
    if context.role == RoleCode.FARMER:
        if context.farmer_id is None:
            return []
        statement = statement.where(ProductionLot.farmer_id == context.farmer_id)
    if farmer_id is not None:
        statement = statement.where(ProductionLot.farmer_id == farmer_id)
    rows = session.execute(statement.order_by(ProductionLot.harvest_start, ProductionLot.id)).all()
    return [_read(session, lot, farmer) for lot, farmer in rows]


@router.get("/{lot_id}", response_model=ProductionLotRead,
            dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def get_production_lot(lot_id: UUID, session: Session = Depends(get_session),
                       context: AuthorizationContext = Depends(get_authorization_context)) -> ProductionLotRead:
    statement = select(ProductionLot).join(Farmer).where(
        ProductionLot.id == lot_id, Farmer.organization_id == context.organization_id
    )
    if context.role == RoleCode.FARMER:
        statement = statement.where(ProductionLot.farmer_id == context.farmer_id)
    lot = session.scalar(statement)
    if lot is None:
        raise HTTPException(status_code=404, detail="production lot not found")
    return _read(session, lot)


@router.post("", response_model=ProductionLotRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def create_production_lot(payload: ProductionLotCreate, session: Session = Depends(get_session),
                          context: AuthorizationContext = Depends(get_authorization_context),
                          idempotency_key: str | None = Depends(tenant_idempotency_key)) -> ProductionLotRead:
    """A coordinator records a farmer's lot on their behalf.

    The figures are the farmer's declaration as relayed to the coordinator: the lot is DECLARED, not
    VERIFIED, with LOW availability confidence, and it does not count as independent farmer confirmation.
    """
    if (replayed := replay_or_none(session, "production_lot.create", idempotency_key)) is not None:
        return ProductionLotRead.model_validate(replayed)
    farmer = session.scalar(select(Farmer).where(Farmer.id == payload.farmer_id, Farmer.organization_id == context.organization_id))
    if farmer is None:
        raise HTTPException(404, "farmer not found")
    if not farmer.active:
        raise HTTPException(422, "farmer is inactive")
    crop = require_active_crop(session, context.organization_id, payload.crop)
    now = datetime.now(timezone.utc)
    lot = ProductionLot(
        farmer_id=farmer.id, crop=crop, harvest_start=payload.harvest_start, harvest_end=payload.harvest_end,
        expected_quantity_kg=payload.expected_quantity_kg, available_quantity_kg=payload.available_quantity_kg,
        reserved_quantity_kg=Decimal("0"), quality_grade_estimate=payload.quality_grade_estimate,
        availability_confidence=AvailabilityConfidence.LOW, parish=(payload.parish or farmer.parish).strip(),
        status=ProductionLotStatus.AVAILABLE if payload.available_quantity_kg > 0 else ProductionLotStatus.UNAVAILABLE,
        last_verified_at=now, capacity_verification=CapacityVerification.DECLARED,
        provenance_source=payload.provenance_source.strip(), attestation_method=payload.attestation_method.strip(),
        evidence_reference=payload.evidence_reference, recorded_by_user_id=context.user_id, declared_at=now,
    )
    try:
        lot.validate()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.add(lot)
    session.flush()
    if payload.farmgate_price_per_kg_jmd is not None:
        _set_price(session, lot, payload.farmgate_price_per_kg_jmd)
    record_event(session, context, "production_lot.declared", "production_lot", lot.id, {
        "farmer_id": str(farmer.id), "crop": str(crop), "expected_quantity_kg": str(lot.expected_quantity_kg),
        "available_quantity_kg": str(lot.available_quantity_kg), "capacity_verification": "DECLARED",
        "provenance_source": lot.provenance_source, "attestation_method": lot.attestation_method,
        "evidence_reference": lot.evidence_reference, "recorded_on_behalf_of_farmer": True,
    }, idempotency_key=idempotency_key)
    session.flush()
    session.refresh(lot)
    result = _read(session, lot, farmer)
    remember(session, "production_lot.create", idempotency_key, result.model_dump(mode="json"))
    session.commit()
    return result


@router.patch("/{lot_id}", response_model=ProductionLotRead,
              dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def update_production_lot(lot_id: UUID, payload: ProductionLotUpdate, session: Session = Depends(get_session),
                          context: AuthorizationContext = Depends(get_authorization_context)) -> ProductionLotRead:
    """Record a changed declaration for a lot. Every change carries its own provenance.

    Reductions below already-reserved stock go through the supplier capacity report
    (POST /production-lots/{lot_id}/capacity-reports), which preserves commitments and opens an exception.
    """
    lot = session.scalar(select(ProductionLot).join(Farmer).where(
        ProductionLot.id == lot_id, Farmer.organization_id == context.organization_id).with_for_update(of=ProductionLot))
    if lot is None:
        raise HTTPException(404, "production lot not found")
    if lot.version != payload.expected_version:
        raise HTTPException(409, f"lot was changed by someone else (now version {lot.version}); reload and retry")
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version", "provenance_source", "attestation_method", "evidence_reference"})
    diff = {}
    price = changes.pop("farmgate_price_per_kg_jmd", None)
    for name, value in changes.items():
        if value is None:
            raise HTTPException(422, f"{name} cannot be cleared")
        if getattr(lot, name) != value:
            diff[name] = [str(getattr(lot, name)), str(value)]
            setattr(lot, name, value)
    if price is not None:
        costs = _costs(session, lot.id)
        if costs is None or costs.farmgate_price_per_kg_jmd != price:
            diff["farmgate_price_per_kg_jmd"] = [str(costs.farmgate_price_per_kg_jmd) if costs else None, str(price)]
            _set_price(session, lot, price)
    if not diff:
        raise HTTPException(422, "the supplied values match the current lot")
    if lot.available_quantity_kg > lot.expected_quantity_kg:
        raise HTTPException(422, "available quantity cannot exceed the expected harvest")
    if lot.available_quantity_kg < lot.reserved_quantity_kg:
        raise HTTPException(409, "this would fall below supply already reserved for orders; submit a capacity report instead")
    try:
        lot.validate()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    now = datetime.now(timezone.utc)
    lot.status = ProductionLotStatus.AVAILABLE if lot.available_quantity_kg > lot.reserved_quantity_kg else ProductionLotStatus.UNAVAILABLE
    lot.capacity_verification = CapacityVerification.DECLARED
    lot.provenance_source, lot.attestation_method = payload.provenance_source.strip(), payload.attestation_method.strip()
    lot.evidence_reference, lot.recorded_by_user_id, lot.declared_at, lot.last_verified_at = payload.evidence_reference, context.user_id, now, now
    lot.version += 1
    record_event(session, context, "production_lot.updated", "production_lot", lot.id, {
        "changes": diff, "version": lot.version, "provenance_source": lot.provenance_source,
        "attestation_method": lot.attestation_method, "evidence_reference": lot.evidence_reference,
    })
    session.commit()
    session.refresh(lot)
    return _read(session, lot)
