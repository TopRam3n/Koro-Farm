from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.recovery import accept, decline, dropout
from src.backend.app.main_dependencies import get_session

router = APIRouter(prefix="/allocations", tags=["allocations"])


class DropoutCommand(BaseModel):
    reason: str


@router.post("/{allocation_id}/dropout")
def post_dropout(allocation_id: UUID, payload: DropoutCommand,
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                 session: Session = Depends(get_session)) -> dict:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        return dropout(session, allocation_id, payload.reason, idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{allocation_id}/accept")
def post_accept(allocation_id: UUID,
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                session: Session = Depends(get_session)) -> dict:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        return accept(session, allocation_id, idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{allocation_id}/decline")
def post_decline(allocation_id: UUID,
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                 session: Session = Depends(get_session)) -> dict:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        return decline(session, allocation_id, idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
