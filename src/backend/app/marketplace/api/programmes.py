"""Organization-scoped marketplace programme portfolio and request association.

Coverage is ACCEPTED FarmerOffer quantities only. Legacy allocation commitments,
physical receipts, and delivered supply are separate and never inferred here.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.main_dependencies import get_session
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.programmes.domain.models import Programme, ProgrammeStatus

router = APIRouter(prefix="/marketplace/programmes", tags=["marketplace programmes"])

_STAFF = frozenset({
    RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN,
    RoleCode.PROCUREMENT_MANAGER, RoleCode.SUPPLY_COORDINATOR,
    RoleCode.WAREHOUSE_OPERATOR, RoleCode.AUDITOR,
})
_WRITERS = frozenset({
    RoleCode.BUYER, RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN,
    RoleCode.PROCUREMENT_MANAGER,
})
_ACTIVE_REQUESTS = frozenset({
    RequirementLifecycleStatus.PLANNING,
    RequirementLifecycleStatus.ACTIVE,
    RequirementLifecycleStatus.IN_FULFILMENT,
})
_ZERO = Decimal("0")


class ProgrammeCreate(BaseModel):
    buyer_id: UUID | None = None
    name: str = Field(min_length=3, max_length=200)
    commodity_scope: str | None = Field(default=None, max_length=100)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_window(self):
        if self.end_date < self.start_date:
            raise ValueError("programme end date must not precede start date")
        return self


class ProgrammeStatusUpdate(BaseModel):
    status: ProgrammeStatus


def _access(ctx: AuthorizationContext, session: Session) -> UUID | None:
    """Return buyer scope or None for authorized organization-wide staff."""
    if ctx.role == RoleCode.BUYER:
        if ctx.buyer_id is None or session.scalar(select(Buyer.id).where(
            Buyer.id == ctx.buyer_id,
            Buyer.organization_id == ctx.organization_id,
        )) is None:
            raise HTTPException(403, "linked buyer account required")
        return ctx.buyer_id
    if ctx.role in _STAFF:
        return None
    raise HTTPException(403, "buyer or authorized staff membership required")


def _write_permission(ctx: AuthorizationContext) -> None:
    if ctx.role not in _WRITERS:
        raise HTTPException(403, "programme modification permission required")


def _owned_buyer(session: Session, ctx: AuthorizationContext, buyer_id: UUID) -> Buyer:
    buyer = session.scalar(select(Buyer).where(
        Buyer.id == buyer_id, Buyer.organization_id == ctx.organization_id,
    ))
    if buyer is None:
        raise HTTPException(404, "buyer not found in active organization")
    return buyer


def _programme(session: Session, ctx: AuthorizationContext, buyer_scope: UUID | None, programme_id: UUID):
    statement = select(Programme, Buyer).join(Buyer, Buyer.id == Programme.buyer_id).where(
        Programme.id == programme_id,
        Buyer.organization_id == ctx.organization_id,
    )
    if buyer_scope is not None:
        statement = statement.where(Programme.buyer_id == buyer_scope)
    result = session.execute(statement).one_or_none()
    if result is None:
        raise HTTPException(404, "programme not found")
    return result


def _summaries(session: Session, ctx: AuthorizationContext, programme_buyers: list[tuple[Programme, Buyer]]) -> list[dict]:
    if not programme_buyers:
        return []
    programme_ids = [programme.id for programme, _ in programme_buyers]
    # All requirements for these programmes, and only in the active organization.
    req_rows = session.scalars(
        select(Requirement)
        .join(Buyer, Buyer.id == Requirement.buyer_id)
        .where(Requirement.programme_id.in_(programme_ids), Buyer.organization_id == ctx.organization_id)
        .order_by(Requirement.created_at.desc(), Requirement.id.desc())
    ).all()
    req_ids = [r.id for r in req_rows]
    offer_qty: dict[UUID, dict[OfferStatus, Decimal]] = defaultdict(dict)
    if req_ids:
        for req_id, offer_status, qty in session.execute(
            select(FarmerOffer.requirement_id, FarmerOffer.status, func.sum(FarmerOffer.quantity_kg))
            .where(
                FarmerOffer.requirement_id.in_(req_ids),
                FarmerOffer.organization_id == ctx.organization_id,
                FarmerOffer.status.in_([OfferStatus.ACCEPTED, OfferStatus.PENDING]),
            )
            .group_by(FarmerOffer.requirement_id, FarmerOffer.status)
        ).all():
            offer_qty[req_id][offer_status] = Decimal(qty)
    req_by_programme: dict[UUID, list[Requirement]] = defaultdict(list)
    for req in req_rows:
        req_by_programme[req.programme_id].append(req)

    items = []
    for programme, buyer in programme_buyers:
        linked = req_by_programme[programme.id]
        active = [r for r in linked if r.lifecycle_status in _ACTIVE_REQUESTS]
        required = sum((r.required_quantity_kg for r in active), _ZERO)
        accepted = sum((offer_qty[r.id].get(OfferStatus.ACCEPTED, _ZERO) for r in active), _ZERO)
        pending = sum((offer_qty[r.id].get(OfferStatus.PENDING, _ZERO) for r in active), _ZERO)
        remaining = sum((max(_ZERO, r.required_quantity_kg - offer_qty[r.id].get(OfferStatus.ACCEPTED, _ZERO)) for r in active), _ZERO)
        items.append({
            "id": str(programme.id), "buyer_id": str(programme.buyer_id),
            "buyer_name": buyer.name, "name": programme.name,
            "commodity_scope": programme.commodity_scope,
            "start_date": programme.start_date.isoformat(), "end_date": programme.end_date.isoformat(),
            "status": programme.status.value,
            "created_at": programme.created_at.isoformat() if programme.created_at else None,
            "requirement_count": len(linked),
            "active_requirement_count": len(active),
            "draft_requirement_count": sum(r.lifecycle_status == RequirementLifecycleStatus.DRAFT for r in linked),
            "active_required_kg": str(required),
            "active_accepted_offer_kg": str(accepted),
            "active_pending_offer_kg": str(pending),
            "active_remaining_offer_kg": str(remaining),
            "active_offer_coverage_pct": float(min(Decimal("100"), accepted * 100 / required)) if required else 0.0,
            "recent_requirements": [{
                "id": str(r.id), "crop": r.crop.value, "grade": r.grade.value,
                "lifecycle_status": r.lifecycle_status.value,
                "required_quantity_kg": str(r.required_quantity_kg),
                "accepted_offer_quantity_kg": str(offer_qty[r.id].get(OfferStatus.ACCEPTED, _ZERO)),
                "delivery_window_start": r.delivery_window_start.isoformat(),
                "delivery_window_end": r.delivery_window_end.isoformat(),
            } for r in linked[:5]],
        })
    return items


@router.get("")
def list_programmes(
    status_filter: ProgrammeStatus | None = None,
    buyer_id: UUID | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    if buyer_scope is not None and buyer_id is not None and buyer_id != buyer_scope:
        raise HTTPException(403, "cannot view another buyer's programmes")
    statement = select(Programme, Buyer).join(Buyer, Buyer.id == Programme.buyer_id).where(
        Buyer.organization_id == ctx.organization_id,
    )
    if buyer_scope is not None:
        statement = statement.where(Programme.buyer_id == buyer_scope)
    elif buyer_id is not None:
        statement = statement.where(Programme.buyer_id == buyer_id)
    if status_filter is not None:
        statement = statement.where(Programme.status == status_filter)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.execute(statement.order_by(Programme.created_at.desc(), Programme.id.desc()).offset(offset).limit(limit)).all()
    return {
        "items": _summaries(session, ctx, rows),
        "scope": "buyer" if buyer_scope is not None else "organization_staff",
        "pagination": {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(rows) < total},
        "coverage_basis": "ACCEPTED marketplace offers on active linked requirements only; not received or delivered quantities. Legacy supply-plan allocations are excluded.",
    }


@router.get("/buyers")
def programme_buyers(
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    statement = select(Buyer).where(Buyer.organization_id == ctx.organization_id)
    if buyer_scope is not None:
        statement = statement.where(Buyer.id == buyer_scope)
    rows = session.scalars(statement.order_by(Buyer.name, Buyer.id).limit(200)).all()
    return {"items": [{"id": str(row.id), "name": row.name} for row in rows]}


@router.get("/available-requirements")
def unassigned_requirements(
    buyer_id: UUID | None = None,
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    if buyer_scope is not None:
        if buyer_id is not None and buyer_id != buyer_scope:
            raise HTTPException(403, "cannot access another buyer's requirements")
        buyer_id = buyer_scope
    elif buyer_id is None:
        raise HTTPException(422, "buyer_id is required for staff users")
    _owned_buyer(session, ctx, buyer_id)
    rows = session.scalars(select(Requirement).where(
        Requirement.buyer_id == buyer_id,
        Requirement.programme_id.is_(None),
        Requirement.lifecycle_status.not_in([RequirementLifecycleStatus.CANCELLED, RequirementLifecycleStatus.CLOSED]),
    ).order_by(Requirement.created_at.desc(), Requirement.id.desc()).limit(200)).all()
    return {"items": [{
        "id": str(r.id), "crop": r.crop.value, "grade": r.grade.value,
        "lifecycle_status": r.lifecycle_status.value,
        "required_quantity_kg": str(r.required_quantity_kg),
        "delivery_window_start": r.delivery_window_start.isoformat(),
        "delivery_window_end": r.delivery_window_end.isoformat(),
    } for r in rows]}


@router.get("/{programme_id}")
def get_programme(
    programme_id: UUID,
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    row = _programme(session, ctx, buyer_scope, programme_id)
    return _summaries(session, ctx, [row])[0]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_programme(
    payload: ProgrammeCreate,
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    _write_permission(ctx)
    if buyer_scope is not None:
        if payload.buyer_id is not None and payload.buyer_id != buyer_scope:
            raise HTTPException(403, "cannot create a programme for another buyer")
        buyer_id = buyer_scope
    else:
        if payload.buyer_id is None:
            raise HTTPException(422, "buyer_id is required for staff users")
        buyer_id = payload.buyer_id
    buyer = _owned_buyer(session, ctx, buyer_id)
    programme = Programme(
        buyer_id=buyer.id,
        name=payload.name,
        commodity_scope=payload.commodity_scope,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=ProgrammeStatus.ACTIVE,
    )
    session.add(programme)
    session.commit()
    session.refresh(programme)
    return _summaries(session, ctx, [(programme, buyer)])[0]


@router.patch("/{programme_id}")
def update_programme_status(
    programme_id: UUID,
    payload: ProgrammeStatusUpdate,
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    _write_permission(ctx)
    programme, buyer = _programme(session, ctx, buyer_scope, programme_id)
    programme.status = payload.status
    session.commit()
    session.refresh(programme)
    return _summaries(session, ctx, [(programme, buyer)])[0]


@router.post("/{programme_id}/requirements/{requirement_id}")
def link_requirement(
    programme_id: UUID,
    requirement_id: UUID,
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer_scope = _access(ctx, session)
    _write_permission(ctx)
    programme, buyer = _programme(session, ctx, buyer_scope, programme_id)
    if programme.status != ProgrammeStatus.ACTIVE:
        raise HTTPException(409, "programme must be active to link requirements")
    req = session.scalar(select(Requirement).join(Buyer, Buyer.id == Requirement.buyer_id).where(
        Requirement.id == requirement_id,
        Requirement.buyer_id == programme.buyer_id,
        Buyer.organization_id == ctx.organization_id,
    ).with_for_update(of=Requirement))
    if req is None:
        raise HTTPException(404, "requirement not found for this programme's buyer")
    if req.programme_id is not None and req.programme_id != programme.id:
        raise HTTPException(409, "requirement is already linked to another programme")
    if req.lifecycle_status in {RequirementLifecycleStatus.CANCELLED, RequirementLifecycleStatus.CLOSED}:
        raise HTTPException(409, "closed or cancelled requirements cannot be newly linked")
    if req.programme_id == programme.id:
        return {"programme_id": str(programme.id), "requirement_id": str(req.id), "associated": True, "already_linked": True}
    req.programme_id = programme.id
    req.version += 1
    session.commit()
    return {"programme_id": str(programme.id), "requirement_id": str(req.id), "associated": True, "already_linked": False}
