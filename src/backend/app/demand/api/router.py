from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event, remember, replay_or_none
from src.backend.app.assurance.domain.models import DomainEvent
from src.backend.app.demand.domain.models import Buyer, BuyerOrderChange, Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.domain.common import DateWindow, Grade, QuantityKg
from src.backend.app.domain.common.fields import CropCodeField
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.application.tenancy import tenant_idempotency_key
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.application.crops import require_active_crop
from src.backend.app.supply.domain.planning_models import AllocationStatus, SupplyAllocation
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor

router = APIRouter(prefix="/requirements", tags=["requirements"])

# R1 supports kilograms only; other units are rejected rather than silently converted.
SUPPORTED_UNITS = {"kg"}
# Allocation states that represent a supplier promise; an order holding any of these cannot simply be cancelled.
BINDING_ALLOCATION_STATES = {AllocationStatus.ACCEPTED, AllocationStatus.COMMITTED, AllocationStatus.STANDBY,
                             AllocationStatus.ACTIVATED}
EDITABLE_FIELDS = ("crop", "grade", "required_quantity_kg", "delivery_window_start", "delivery_window_end",
                   "product_form", "origin", "destination", "delivery_terms", "currency", "notes")


class OrderTerms(BaseModel):
    product_form: str | None = Field(default=None, max_length=80)
    quantity_unit: str = Field(default="kg", max_length=10)
    origin: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("quantity_unit")
    @classmethod
    def supported_unit(cls, unit: str) -> str:
        if unit not in SUPPORTED_UNITS:
            raise ValueError("only kg is supported in this release")
        return unit


class RequirementCreate(OrderTerms):
    buyer_id: UUID
    programme_id: UUID | None = None
    trade_corridor_id: UUID | None = None
    crop: CropCodeField
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


class RequirementUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    crop: CropCodeField | None = None
    grade: Grade | None = None
    required_quantity_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    delivery_window_start: date | None = None
    delivery_window_end: date | None = None
    product_form: str | None = Field(default=None, max_length=80)
    origin: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def has_change(self):
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("no changes supplied")
        return self


class CancelCommand(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    buyer_id: UUID
    buyer_name: str | None = None
    programme_id: UUID | None
    trade_corridor_id: UUID | None
    crop: str
    grade: Grade
    required_quantity_kg: Decimal
    quantity_unit: str = "kg"
    delivery_window_start: date
    delivery_window_end: date
    product_form: str | None = None
    origin: str | None = None
    destination: str | None = None
    delivery_terms: str | None = None
    currency: str | None = None
    notes: str | None = None
    lifecycle_status: RequirementLifecycleStatus
    supply_health: SupplyHealth
    plan_version: int
    version: int
    created_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BuyerChangeCommand(BaseModel):
    new_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


def _read(requirement: Requirement, buyer: Buyer | None) -> RequirementRead:
    data = RequirementRead.model_validate(requirement)
    data.buyer_name = buyer.name if buyer else None
    return data


def _scoped(session: Session, context: AuthorizationContext, requirement_id: UUID, *, lock: bool = False) -> tuple[Requirement, Buyer]:
    statement = select(Requirement, Buyer).join(Buyer, Buyer.id == Requirement.buyer_id).where(
        Requirement.id == requirement_id, Buyer.organization_id == context.organization_id)
    if lock:
        statement = statement.with_for_update(of=Requirement)
    row = session.execute(statement).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    return row[0], row[1]


def _jsonable(value):
    if isinstance(value, (Decimal, date, UUID)):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


@router.post("", response_model=RequirementRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_CREATE))])
def post_requirement(payload: RequirementCreate, session: Session = Depends(get_session),
                     context: AuthorizationContext = Depends(get_authorization_context),
                     idempotency_key: str | None = Depends(tenant_idempotency_key)) -> RequirementRead:
    if (replayed := replay_or_none(session, "requirement.create", idempotency_key)) is not None:
        return RequirementRead.model_validate(replayed)
    buyer = session.scalar(select(Buyer).where(Buyer.id == payload.buyer_id,
                                                Buyer.organization_id == context.organization_id))
    if buyer is None:
        raise HTTPException(status_code=404, detail="buyer not found")
    if not buyer.active:
        raise HTTPException(status_code=422, detail="buyer is inactive")
    payload.crop = require_active_crop(session, context.organization_id, payload.crop)
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
        requirement = Requirement(**payload.model_dump(), created_by_user_id=context.user_id)
        requirement.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.add(requirement)
    session.flush()
    record_event(session, context, "requirement.created", "requirement", requirement.id,
                 {"required_kg": str(requirement.required_quantity_kg), "crop": str(requirement.crop),
                  "grade": requirement.grade.value, "buyer_id": str(buyer.id)}, idempotency_key=idempotency_key)
    session.flush()
    session.refresh(requirement)
    result = _read(requirement, buyer)
    remember(session, "requirement.create", idempotency_key, result.model_dump(mode="json"))
    session.commit()
    return result


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
) -> list[RequirementRead]:
    if offset < 0 or limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="offset must be non-negative and limit must be between 1 and 200")
    statement = select(Requirement, Buyer).join(Buyer).where(Buyer.organization_id == context.organization_id)
    if supply_health is not None:
        statement = statement.where(Requirement.supply_health == supply_health)
    if lifecycle_status is not None:
        statement = statement.where(Requirement.lifecycle_status == lifecycle_status)
    if buyer_id is not None:
        statement = statement.where(Requirement.buyer_id == buyer_id)
    if programme_id is not None:
        statement = statement.where(Requirement.programme_id == programme_id)
    rows = session.execute(statement.order_by(Requirement.created_at.desc(), Requirement.id).offset(offset).limit(limit)).all()
    return [_read(requirement, buyer) for requirement, buyer in rows]


@router.get("/{requirement_id}", response_model=RequirementRead,
            dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def get_requirement(requirement_id: UUID, session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> RequirementRead:
    return _read(*_scoped(session, context, requirement_id))


@router.patch("/{requirement_id}", response_model=RequirementRead,
              dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_UPDATE))])
def update_requirement(requirement_id: UUID, payload: RequirementUpdate, session: Session = Depends(get_session),
                       context: AuthorizationContext = Depends(get_authorization_context)) -> RequirementRead:
    """Edit order terms. Allowed only before supply planning; afterwards use buyer-change or cancel."""
    requirement, buyer = _scoped(session, context, requirement_id, lock=True)
    if requirement.version != payload.expected_version:
        raise HTTPException(status_code=409, detail=f"order was changed by someone else (now version {requirement.version}); reload and retry")
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="a cancelled order cannot be edited")
    if requirement.plan_version > 0:
        raise HTTPException(status_code=409, detail="supply planning has started; change quantity through a buyer change instead")
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "crop" in changes and changes["crop"] is not None:
        changes["crop"] = require_active_crop(session, context.organization_id, changes["crop"])
    for name in ("crop", "grade", "required_quantity_kg", "delivery_window_start", "delivery_window_end"):
        if name in changes and changes[name] is None:
            raise HTTPException(status_code=422, detail=f"{name} cannot be cleared")
    diff = {}
    for name, value in changes.items():
        before = getattr(requirement, name)
        if before != value:
            diff[name] = [_jsonable(before), _jsonable(value)]
            setattr(requirement, name, value)
    if not diff:
        raise HTTPException(status_code=422, detail="the supplied values match the current order")
    try:
        requirement.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    requirement.version += 1
    record_event(session, context, "requirement.updated", "requirement", requirement.id,
                 {"changes": diff, "version": requirement.version})
    session.commit()
    session.refresh(requirement)
    return _read(requirement, buyer)


@router.post("/{requirement_id}/cancel", response_model=RequirementRead,
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_UPDATE))])
def cancel_requirement(requirement_id: UUID, payload: CancelCommand, session: Session = Depends(get_session),
                       context: AuthorizationContext = Depends(get_authorization_context)) -> RequirementRead:
    requirement, buyer = _scoped(session, context, requirement_id, lock=True)
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="order is already cancelled")
    binding = session.scalar(select(SupplyAllocation.id).where(
        SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.status.in_(BINDING_ALLOCATION_STATES)).limit(1))
    if binding is not None:
        raise HTTPException(status_code=409, detail="suppliers have accepted or reserved supply for this order; release them before cancelling")
    requirement.lifecycle_status = RequirementLifecycleStatus.CANCELLED
    requirement.cancelled_at = datetime.now(timezone.utc)
    requirement.cancellation_reason = payload.reason
    requirement.version += 1
    record_event(session, context, "requirement.cancelled", "requirement", requirement.id, {"reason": payload.reason})
    session.commit()
    session.refresh(requirement)
    return _read(requirement, buyer)


@router.get("/{requirement_id}/history",
            dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def requirement_history(requirement_id: UUID, session: Session = Depends(get_session),
                        context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    requirement, _ = _scoped(session, context, requirement_id)
    events = session.scalars(select(DomainEvent).where(
        DomainEvent.aggregate_id == requirement.id, DomainEvent.organization_id == context.organization_id,
    ).order_by(DomainEvent.occurred_at, DomainEvent.id)).all()
    changes = session.scalars(select(BuyerOrderChange).where(BuyerOrderChange.requirement_id == requirement.id)
                              .order_by(BuyerOrderChange.created_at)).all()
    return {
        "requirement_id": str(requirement.id),
        "events": [{"id": str(e.id), "event_type": e.event_type, "actor_type": e.actor_type, "actor_id": e.actor_id,
                    "payload": e.payload, "occurred_at": e.occurred_at} for e in events],
        "buyer_changes": [{"id": str(c.id), "previous_quantity_kg": str(c.previous_quantity_kg),
                           "new_quantity_kg": str(c.new_quantity_kg), "reason": c.reason, "created_at": c.created_at}
                          for c in changes],
    }


@router.post("/{requirement_id}/buyer-change",
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_UPDATE))])
def buyer_change(requirement_id: UUID, payload: BuyerChangeCommand, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    requirement, _ = _scoped(session, context, requirement_id, lock=True)
    previous = requirement.required_quantity_kg
    if payload.new_quantity_kg == previous:
        raise HTTPException(status_code=422, detail="buyer change must alter the quantity")
    change = BuyerOrderChange(requirement_id=requirement.id, previous_quantity_kg=previous, new_quantity_kg=payload.new_quantity_kg, reason=payload.reason)
    requirement.required_quantity_kg = payload.new_quantity_kg
    requirement.version += 1
    session.add(change)
    record_event(session, context, "requirement.buyer_changed", "requirement", requirement.id,
                 {"previous_quantity_kg": str(previous), "new_quantity_kg": str(payload.new_quantity_kg), "reason": payload.reason})
    session.commit()
    return {"requirement_id": str(requirement.id), "previous_quantity_kg": str(previous), "new_quantity_kg": str(payload.new_quantity_kg), "attribution": "BUYER_CHANGE", "farmer_reliability_impact": "NONE"}
