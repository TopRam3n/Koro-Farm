from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event, remember, replay_or_none
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.application.tenancy import tenant_idempotency_key
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.models import Farmer

# The list endpoint (GET /farmers) lives in registry/api/router.py and is organization-scoped there.
router = APIRouter(prefix="/farmers", tags=["farmers"])


class FarmerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    parish: str = Field(min_length=2, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class FarmerUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    parish: str | None = Field(default=None, min_length=2, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)
    active: bool | None = None

    @model_validator(mode="after")
    def has_change(self):
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("no changes supplied")
        return self


class FarmerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    parish: str
    contact_phone: str | None
    notes: str | None
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


def _scoped(session: Session, context: AuthorizationContext, farmer_id: UUID) -> Farmer:
    farmer = session.scalar(select(Farmer).where(Farmer.id == farmer_id, Farmer.organization_id == context.organization_id))
    if farmer is None:
        raise HTTPException(404, "farmer not found")
    return farmer


@router.post("", response_model=FarmerRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def create_farmer(payload: FarmerCreate, session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context),
                  idempotency_key: str | None = Depends(tenant_idempotency_key)) -> FarmerRead:
    if (replayed := replay_or_none(session, "farmer.create", idempotency_key)) is not None:
        return FarmerRead.model_validate(replayed)
    farmer = Farmer(organization_id=context.organization_id, name=payload.name.strip(), parish=payload.parish.strip(),
                    contact_phone=payload.contact_phone, notes=payload.notes, created_by_user_id=context.user_id)
    session.add(farmer)
    session.flush()
    record_event(session, context, "farmer.created", "farmer", farmer.id,
                 {"name": farmer.name, "parish": farmer.parish}, idempotency_key=idempotency_key)
    session.flush()
    session.refresh(farmer)
    result = FarmerRead.model_validate(farmer)
    remember(session, "farmer.create", idempotency_key, result.model_dump(mode="json"))
    session.commit()
    return result


@router.get("/{farmer_id}", response_model=FarmerRead, dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def get_farmer(farmer_id: UUID, session: Session = Depends(get_session),
               context: AuthorizationContext = Depends(get_authorization_context)) -> Farmer:
    return _scoped(session, context, farmer_id)


@router.patch("/{farmer_id}", response_model=FarmerRead, dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def update_farmer(farmer_id: UUID, payload: FarmerUpdate, session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context)) -> Farmer:
    farmer = _scoped(session, context, farmer_id)
    if farmer.version != payload.expected_version:
        raise HTTPException(409, f"farmer was changed by someone else (now version {farmer.version}); reload and retry")
    diff = {}
    for name, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if value is None and name not in {"notes", "contact_phone"}:
            raise HTTPException(422, f"{name} cannot be cleared")
        value = value.strip() if isinstance(value, str) else value
        if getattr(farmer, name) != value:
            diff[name] = [getattr(farmer, name), value]
            setattr(farmer, name, value)
    if not diff:
        raise HTTPException(422, "the supplied values match the current farmer")
    farmer.version += 1
    record_event(session, context, "farmer.updated", "farmer", farmer.id, {"changes": diff, "version": farmer.version})
    session.commit()
    session.refresh(farmer)
    return farmer
