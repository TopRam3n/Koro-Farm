"""Read-only, tenant-scoped demand ledger for BUYER and operations staff.

Marketplace acceptance and finalized supply-plan allocation are two different
commitment systems. Never sum them; this response reports each separately.
"""
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.domain.common import Crop
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.main_dependencies import get_session
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation

router = APIRouter(prefix="/marketplace/demand", tags=["marketplace demand"])

_STAFF = frozenset({
    RoleCode.PLATFORM_ADMIN,
    RoleCode.ORGANIZATION_ADMIN,
    RoleCode.PROCUREMENT_MANAGER,
    RoleCode.SUPPLY_COORDINATOR,
    RoleCode.WAREHOUSE_OPERATOR,
    RoleCode.AUDITOR,
})
_ZERO = Decimal("0")


def _coverage_status(status: RequirementLifecycleStatus, remaining: Decimal, accepted: Decimal) -> str:
    if status == RequirementLifecycleStatus.DRAFT:
        return "DRAFT"
    if status == RequirementLifecycleStatus.CANCELLED:
        return "CANCELLED"
    if status == RequirementLifecycleStatus.CLOSED:
        return "CLOSED"
    if remaining == 0:
        return "COVERED"
    if accepted > 0:
        return "PARTIALLY_COVERED"
    return "UNFILLED"


@router.get("")
def list_demand(
    crop: Crop | None = None,
    lifecycle_status: RequirementLifecycleStatus | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    """List accessible requirements, with accepted-offer coverage and plan totals separate.

    BUYER: only their linked buyer ID, inside active organization membership.
    Staff: only buyers within the active organization. FARMER: forbidden.
    Summary counts and quantities refer to the returned *page*, not the whole DB.
    """
    if context.role != RoleCode.BUYER and context.role not in _STAFF:
        raise HTTPException(status_code=403, detail="buyer or authorized operations role required")

    restrictions = [Buyer.organization_id == context.organization_id]
    if context.role == RoleCode.BUYER:
        if context.buyer_id is None:
            raise HTTPException(status_code=403, detail="linked buyer account required")
        restrictions.append(Requirement.buyer_id == context.buyer_id)
        # A stale membership must not imply permission to read orphaned buyer records.
        if session.scalar(select(Buyer.id).where(
            Buyer.id == context.buyer_id,
            Buyer.organization_id == context.organization_id,
        )) is None:
            raise HTTPException(status_code=403, detail="linked buyer account required")
    if crop is not None:
        restrictions.append(Requirement.crop == crop)
    if lifecycle_status is not None:
        restrictions.append(Requirement.lifecycle_status == lifecycle_status)

    total = session.scalar(
        select(func.count(Requirement.id)).join(Buyer, Buyer.id == Requirement.buyer_id).where(*restrictions)
    ) or 0
    rows = session.execute(
        select(Requirement, Buyer)
        .join(Buyer, Buyer.id == Requirement.buyer_id)
        .where(*restrictions)
        .order_by(Requirement.created_at.desc(), Requirement.id.desc())
        .offset(offset).limit(limit)
    ).all()
    ids: list[UUID] = [req.id for req, _ in rows]

    offered: dict[UUID, dict[OfferStatus, Decimal]] = defaultdict(dict)
    planned: dict[UUID, Decimal] = {}
    if ids:
        # All calculations are server-side and always limited to visible IDs.
        for req_id, state, quantity in session.execute(
            select(FarmerOffer.requirement_id, FarmerOffer.status, func.sum(FarmerOffer.quantity_kg))
            .where(FarmerOffer.organization_id == context.organization_id,
                   FarmerOffer.requirement_id.in_(ids),
                   FarmerOffer.status.in_([OfferStatus.ACCEPTED, OfferStatus.PENDING]))
            .group_by(FarmerOffer.requirement_id, FarmerOffer.status)
        ).all():
            offered[req_id][state] = Decimal(quantity)

        # Legacy finalized operations plans are NOT marketplace accepted offers.
        for req_id, quantity in session.execute(
            select(SupplyAllocation.requirement_id, func.sum(SupplyAllocation.quantity_kg))
            .join(Requirement, Requirement.id == SupplyAllocation.requirement_id)
            .join(Buyer, Buyer.id == Requirement.buyer_id)
            .where(Buyer.organization_id == context.organization_id,
                   SupplyAllocation.requirement_id.in_(ids),
                   SupplyAllocation.role == AllocationRole.COMMITTED,
                   SupplyAllocation.status.in_([AllocationStatus.COMMITTED, AllocationStatus.ACTIVATED]))
            .group_by(SupplyAllocation.requirement_id)
        ).all():
            planned[req_id] = Decimal(quantity)

    items = []
    for req, buyer in rows:
        accepted = offered[req.id].get(OfferStatus.ACCEPTED, _ZERO)
        pending = offered[req.id].get(OfferStatus.PENDING, _ZERO)
        required = req.required_quantity_kg
        remaining = max(_ZERO, required - accepted)
        percent = min(Decimal("100"), accepted / required * 100) if required else _ZERO
        items.append({
            "id": str(req.id),
            "buyer_id": str(buyer.id),
            "buyer_name": buyer.name,
            "programme_id": str(req.programme_id) if req.programme_id else None,
            "crop": req.crop.value,
            "grade": req.grade.value,
            "lifecycle_status": req.lifecycle_status.value,
            "planning_supply_health": req.supply_health.value,
            "delivery_window_start": req.delivery_window_start.isoformat(),
            "delivery_window_end": req.delivery_window_end.isoformat(),
            "required_quantity_kg": str(required),
            "accepted_offer_quantity_kg": str(accepted),
            "pending_offer_quantity_kg": str(pending),
            "remaining_offer_quantity_kg": str(remaining),
            "offer_coverage_pct": float(percent),
            "coverage_status": _coverage_status(req.lifecycle_status, remaining, accepted),
            "planned_committed_quantity_kg": str(planned.get(req.id, _ZERO)),
            "created_at": req.created_at.isoformat() if req.created_at else None,
        })

    # Page-scoped metrics. Exclude cancelled/drafts from active demand totals;
    # do not claim that an accepted offer is received or delivered produce.
    active = [r for r in items if r["lifecycle_status"] not in {"DRAFT", "CANCELLED", "CLOSED"}]
    return {
        "items": items,
        "scope": "buyer" if context.role == RoleCode.BUYER else "organization_staff",
        "pagination": {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(items) < total},
        "summary": {
            "page_requests": len(items),
            "page_active_requests": len(active),
            "page_requested_kg": str(sum((Decimal(r["required_quantity_kg"]) for r in active), _ZERO)),
            "page_accepted_offer_kg": str(sum((Decimal(r["accepted_offer_quantity_kg"]) for r in active), _ZERO)),
            "page_remaining_offer_kg": str(sum((Decimal(r["remaining_offer_quantity_kg"]) for r in active), _ZERO)),
        },
        "coverage_basis": "Accepted marketplace offers only; pending offers and finalized supply-plan allocations are not added to marketplace coverage. No delivery is inferred.",
    }
