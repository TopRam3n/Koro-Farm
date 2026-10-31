from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.exceptions import ExceptionActionError, acknowledge, resolve_manually
from src.backend.app.assurance.domain.exceptions import ExceptionKind, ExceptionStatus, SupplyException
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session

router = APIRouter(prefix="/exceptions", tags=["supply exceptions"])


class ExceptionRead(BaseModel):
    id: UUID
    requirement_id: UUID
    requirement_label: str | None = None
    kind: ExceptionKind
    status: ExceptionStatus
    shortfall_kg: Decimal
    summary: str
    details: dict
    opened_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolved_by: str | None
    resolution: str | None


class ResolveCommand(BaseModel):
    resolution: str = Field(min_length=3, max_length=500)


def _read(row: SupplyException, label: str | None = None) -> ExceptionRead:
    return ExceptionRead(id=row.id, requirement_id=row.requirement_id, requirement_label=label, kind=row.kind,
                         status=row.status, shortfall_kg=row.shortfall_kg, summary=row.summary, details=row.details,
                         opened_at=row.opened_at, updated_at=row.updated_at, acknowledged_at=row.acknowledged_at,
                         resolved_at=row.resolved_at, resolved_by=row.resolved_by, resolution=row.resolution)


@router.get("", response_model=list[ExceptionRead], dependencies=[Depends(require_permission(PermissionCode.RECOVERY_VIEW))])
def list_exceptions(status: ExceptionStatus | None = ExceptionStatus.OPEN, requirement_id: UUID | None = None,
                    session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> list[ExceptionRead]:
    statement = (select(SupplyException, Requirement, Buyer)
                 .join(Requirement, Requirement.id == SupplyException.requirement_id)
                 .join(Buyer, Buyer.id == Requirement.buyer_id)
                 .where(SupplyException.organization_id == context.organization_id))
    if status is not None:
        statement = statement.where(SupplyException.status == status)
    if requirement_id is not None:
        statement = statement.where(SupplyException.requirement_id == requirement_id)
    rows = session.execute(statement.order_by(SupplyException.opened_at.desc(), SupplyException.id).limit(200)).all()
    return [_read(row, f"{str(requirement.crop).replace('_', ' ')} for {buyer.name}") for row, requirement, buyer in rows]


@router.get("/{exception_id}", response_model=ExceptionRead, dependencies=[Depends(require_permission(PermissionCode.RECOVERY_VIEW))])
def get_exception(exception_id: UUID, session: Session = Depends(get_session)) -> ExceptionRead:
    return _read(session.get(SupplyException, exception_id))


@router.post("/{exception_id}/acknowledge", response_model=ExceptionRead,
             dependencies=[Depends(require_permission(PermissionCode.RECOVERY_VIEW))])
def post_acknowledge(exception_id: UUID, session: Session = Depends(get_session),
                     context: AuthorizationContext = Depends(get_authorization_context)) -> ExceptionRead:
    try:
        row = acknowledge(session, context, exception_id)
    except ExceptionActionError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _read(row)


@router.post("/{exception_id}/resolve", response_model=ExceptionRead,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def post_resolve(exception_id: UUID, payload: ResolveCommand, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> ExceptionRead:
    try:
        row = resolve_manually(session, context, exception_id, payload.resolution)
    except ExceptionActionError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return _read(row)
