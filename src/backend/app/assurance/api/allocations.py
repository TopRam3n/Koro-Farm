from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.recovery import dropout
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.application.tenancy import tenant_idempotency_key
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.application.commitments import (
    CommitmentError,
    CommitmentForbidden,
    SupplierResponse,
    respond,
    set_response_deadline,
    solicit,
    withdraw,
)
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import AllocationStatus, ConsentDecision, SupplierConsent, SupplyAllocation

router = APIRouter(prefix="/allocations", tags=["allocations"])
# Supplier responses: staff recording on a farmer's behalf, or the farmer themselves (own lots only).
response_router = APIRouter(prefix="/allocations", tags=["supplier responses"])


class DropoutCommand(BaseModel):
    reason: str
    defer_recovery: bool = True


class SolicitCommand(BaseModel):
    message: str | None = Field(default=None, max_length=1000)
    respond_within_hours: int | None = Field(default=None, ge=1, le=336,
                                             description="Default: 24 hours, or 4 hours when delivery starts within 48 hours")


class DeadlineCommand(BaseModel):
    respond_by: datetime
    reason: str = Field(min_length=3, max_length=500)


class WithdrawCommand(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ResponseCommand(BaseModel):
    decision: ConsentDecision
    attestation_method: str = Field(min_length=3, max_length=100,
                                    description="How the decision was given, e.g. 'phone call', 'signed form', 'farmer portal'")
    evidence_reference: str | None = Field(default=None, max_length=500)
    accepted_quantity_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    activation_conditions: str | None = Field(default=None, max_length=1000,
                                              description="Required for standby: when the supplier agrees it may be called on")
    valid_until: date | None = None
    note: str | None = Field(default=None, max_length=1000)


def _require_key(key: str | None) -> str:
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return key


def _run(fn):
    try:
        return fn()
    except CommitmentForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CommitmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{allocation_id}/dropout")
def post_dropout(allocation_id: UUID, payload: DropoutCommand,
                 idempotency_key: str | None = Depends(tenant_idempotency_key),
                 session: Session = Depends(get_session)) -> dict:
    key = _require_key(idempotency_key)
    try:
        result = dropout(session, allocation_id, payload.reason, key, auto_recover=not payload.defer_recovery)
        session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{allocation_id}/solicit", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def post_solicit(allocation_id: UUID, payload: SolicitCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                 session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _require_key(idempotency_key)
    result = _run(lambda: solicit(session, context, allocation_id, payload.message, key, payload.respond_within_hours))
    session.commit()
    return result


@router.patch("/{allocation_id}/deadline", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def patch_deadline(allocation_id: UUID, payload: DeadlineCommand, session: Session = Depends(get_session),
                   context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    result = _run(lambda: set_response_deadline(session, context, allocation_id, payload.respond_by, payload.reason))
    session.commit()
    return result


@router.post("/{allocation_id}/withdraw", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def post_withdraw(allocation_id: UUID, payload: WithdrawCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                  session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _require_key(idempotency_key)
    result = _run(lambda: withdraw(session, context, allocation_id, payload.reason, key))
    session.commit()
    return result


def _respond(allocation_id: UUID, payload: ResponseCommand, key: str | None, session: Session,
             context: AuthorizationContext) -> dict:
    key = _require_key(key)
    response = SupplierResponse(**payload.model_dump())
    result = _run(lambda: respond(session, context, allocation_id, response, key))
    session.commit()
    return result


@response_router.post("/{allocation_id}/responses")
def post_response(allocation_id: UUID, payload: ResponseCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                  session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _respond(allocation_id, payload, idempotency_key, session, context)


class LegacyDecision(BaseModel):
    attestation_method: str = Field(min_length=3, max_length=100)
    evidence_reference: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


@response_router.post("/{allocation_id}/accept")
def post_accept(allocation_id: UUID, payload: LegacyDecision, idempotency_key: str | None = Depends(tenant_idempotency_key),
                session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Shorthand for a full acceptance response. An attestation is still required."""
    return _respond(allocation_id, ResponseCommand(decision=ConsentDecision.ACCEPTED, **payload.model_dump()),
                    idempotency_key, session, context)


@response_router.post("/{allocation_id}/decline")
def post_decline(allocation_id: UUID, payload: LegacyDecision, idempotency_key: str | None = Depends(tenant_idempotency_key),
                 session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _respond(allocation_id, ResponseCommand(decision=ConsentDecision.DECLINED, **payload.model_dump()),
                    idempotency_key, session, context)


@response_router.get("/{allocation_id}/consents")
def list_consents(allocation_id: UUID, session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context)) -> list[dict]:
    allocation = session.get(SupplyAllocation, allocation_id)
    lot = session.get(ProductionLot, allocation.production_lot_id)
    if context.role == RoleCode.FARMER and context.farmer_id != lot.farmer_id:
        raise HTTPException(status_code=404, detail="allocation not found")
    rows = session.scalars(select(SupplierConsent).where(SupplierConsent.allocation_id == allocation_id)
                           .order_by(SupplierConsent.recorded_at)).all()
    return [{"id": str(c.id), "consent_type": c.consent_type.value, "decision": c.decision.value, "channel": c.channel.value,
             "quantity_kg": str(c.quantity_kg), "attestation_method": c.attestation_method,
             "evidence_reference": c.evidence_reference, "activation_conditions": c.activation_conditions,
             "valid_until": c.valid_until, "note": c.note, "recorded_by_user_id": str(c.recorded_by_user_id) if c.recorded_by_user_id else None,
             "recorded_at": c.recorded_at} for c in rows]


@response_router.get("/solicitations/mine", dependencies=[Depends(require_permission(PermissionCode.FARMER_SUPPLY_REPORT))])
def my_solicitations(session: Session = Depends(get_session),
                     context: AuthorizationContext = Depends(get_authorization_context)) -> list[dict]:
    """Requests awaiting this farmer's answer."""
    if context.farmer_id is None:
        return []
    rows = session.execute(
        select(SupplyAllocation, ProductionLot, Requirement, Buyer)
        .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .join(Requirement, Requirement.id == SupplyAllocation.requirement_id)
        .join(Buyer, Buyer.id == Requirement.buyer_id)
        .where(ProductionLot.farmer_id == context.farmer_id, Farmer.organization_id == context.organization_id,
               SupplyAllocation.status == AllocationStatus.SOLICITED)
        .order_by(SupplyAllocation.solicited_at)).all()
    return [{"allocation_id": str(a.id), "role": a.role.value, "quantity_kg": str(a.quantity_kg), "crop": str(r.crop),
             "grade": r.grade.value, "delivery_window_start": r.delivery_window_start, "delivery_window_end": r.delivery_window_end,
             "buyer_name": b.name, "production_lot_id": str(lot.id), "solicited_at": a.solicited_at,
             "response_due_at": a.response_due_at, "reminder_sent_at": a.reminder_sent_at} for a, lot, r, b in rows]
