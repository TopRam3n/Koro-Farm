from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.domain.common.fields import CropCodeField
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.application.crops import visible_crops
from src.backend.app.supply.domain.crops import CropRecord

router = APIRouter(prefix="/crops", tags=["crops"])


class CropCreate(BaseModel):
    code: CropCodeField
    name: str = Field(min_length=2, max_length=120)


class CropRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    active: bool
    shared: bool
    created_at: datetime


def _read(row: CropRecord) -> CropRead:
    return CropRead(id=row.id, code=row.code, name=row.name, active=row.active,
                    shared=row.organization_id is None, created_at=row.created_at)


@router.get("", response_model=list[CropRead])
def list_crops(session: Session = Depends(get_session),
               context: AuthorizationContext = Depends(get_authorization_context)) -> list[CropRead]:
    rows = session.scalars(visible_crops(context.organization_id).order_by(CropRecord.name, CropRecord.id))
    return [_read(row) for row in rows]


@router.post("", response_model=CropRead, status_code=status.HTTP_201_CREATED)
def create_crop(payload: CropCreate, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> CropRead:
    if not ({PermissionCode.SUPPLY_MANAGE, PermissionCode.REQUIREMENT_CREATE} & context.permissions):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission denied")
    if session.scalar(visible_crops(context.organization_id).where(CropRecord.code == payload.code)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"crop {payload.code!r} already exists")
    row = CropRecord(organization_id=context.organization_id, code=payload.code, name=payload.name.strip(),
                     created_by_user_id=context.user_id)
    session.add(row)
    session.flush()
    event = DomainEvent(event_type="crop.created", aggregate_type="crop", aggregate_id=row.id, correlation_id=uuid4(),
                        actor_type="user", actor_id=str(context.user_id), organization_id=context.organization_id,
                        payload={"code": row.code, "name": row.name})
    session.add(event)
    session.flush()
    session.add(OutboxMessage(event_id=event.id, topic=event.event_type, payload=event.payload))
    session.commit()
    session.refresh(row)
    return _read(row)
