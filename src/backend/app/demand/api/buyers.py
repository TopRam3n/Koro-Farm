from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event, remember, replay_or_none
from src.backend.app.demand.domain.models import Buyer
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.application.tenancy import tenant_idempotency_key
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session

router = APIRouter(prefix="/buyers", tags=["buyers"])


class BuyerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    buyer_type: str = Field(min_length=2, max_length=80)
    destination: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)


class BuyerUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    buyer_type: str | None = Field(default=None, min_length=2, max_length=80)
    destination: str | None = Field(default=None, min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    active: bool | None = None

    @model_validator(mode="after")
    def has_change(self):
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("no changes supplied")
        return self


class BuyerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    buyer_type: str
    destination: str
    notes: str | None
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


def _scoped(session: Session, context: AuthorizationContext, buyer_id: UUID) -> Buyer:
    buyer = session.scalar(select(Buyer).where(Buyer.id == buyer_id, Buyer.organization_id == context.organization_id))
    if buyer is None:
        raise HTTPException(404, "buyer not found")
    return buyer


@router.post("", response_model=BuyerRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_CREATE))])
def create_buyer(payload: BuyerCreate, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context),
                 idempotency_key: str | None = Depends(tenant_idempotency_key)) -> BuyerRead:
    if (replayed := replay_or_none(session, "buyer.create", idempotency_key)) is not None:
        return BuyerRead.model_validate(replayed)
    name = payload.name.strip()
    duplicate = session.scalar(select(Buyer.id).where(Buyer.organization_id == context.organization_id, Buyer.name == name))
    if duplicate is not None:
        raise HTTPException(409, f"a buyer named {name!r} already exists")
    buyer = Buyer(organization_id=context.organization_id, name=name, buyer_type=payload.buyer_type.strip(),
                  destination=payload.destination.strip(), notes=payload.notes, created_by_user_id=context.user_id)
    session.add(buyer)
    session.flush()
    record_event(session, context, "buyer.created", "buyer", buyer.id,
                 {"name": buyer.name, "buyer_type": buyer.buyer_type, "destination": buyer.destination},
                 idempotency_key=idempotency_key)
    session.flush()
    session.refresh(buyer)
    result = BuyerRead.model_validate(buyer)
    remember(session, "buyer.create", idempotency_key, result.model_dump(mode="json"))
    session.commit()
    return result


@router.get("", response_model=list[BuyerRead], dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def list_buyers(include_inactive: bool = False, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> list[Buyer]:
    statement = select(Buyer).where(Buyer.organization_id == context.organization_id)
    if not include_inactive:
        statement = statement.where(Buyer.active.is_(True))
    return list(session.scalars(statement.order_by(Buyer.name, Buyer.id)))


@router.get("/{buyer_id}", response_model=BuyerRead, dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def get_buyer(buyer_id: UUID, session: Session = Depends(get_session),
              context: AuthorizationContext = Depends(get_authorization_context)) -> Buyer:
    return _scoped(session, context, buyer_id)


@router.patch("/{buyer_id}", response_model=BuyerRead, dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_UPDATE))])
def update_buyer(buyer_id: UUID, payload: BuyerUpdate, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> Buyer:
    buyer = _scoped(session, context, buyer_id)
    if buyer.version != payload.expected_version:
        raise HTTPException(409, f"buyer was changed by someone else (now version {buyer.version}); reload and retry")
    diff = {}
    for name, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if value is None and name != "notes":
            raise HTTPException(422, f"{name} cannot be cleared")
        value = value.strip() if isinstance(value, str) else value
        if getattr(buyer, name) != value:
            diff[name] = [getattr(buyer, name), value]
            setattr(buyer, name, value)
    if not diff:
        raise HTTPException(422, "the supplied values match the current buyer")
    buyer.version += 1
    record_event(session, context, "buyer.updated", "buyer", buyer.id, {"changes": diff, "version": buyer.version})
    session.commit()
    session.refresh(buyer)
    return buyer
