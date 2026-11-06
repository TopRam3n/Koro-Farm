"""Marketplace Command Center portfolio read model.

IMPORTANT: The source of procurement coverage is ACCEPTED FarmerOffer records.
The older SupplyAllocation / SupplyPlan path is a separate workflow, not an
additional pool of procurement commitments. Receipts/deliveries are not inferred.
"""
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.main_dependencies import get_session
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.supply.domain.models import Farmer

router = APIRouter(prefix="/marketplace/command-center", tags=["marketplace command center"])

_STAFF = frozenset({
    RoleCode.PLATFORM_ADMIN,
    RoleCode.ORGANIZATION_ADMIN,
    RoleCode.PROCUREMENT_MANAGER,
    RoleCode.SUPPLY_COORDINATOR,
    RoleCode.WAREHOUSE_OPERATOR,
    RoleCode.AUDITOR,
})
_ACTIVE = frozenset({
    RequirementLifecycleStatus.PLANNING,
    RequirementLifecycleStatus.ACTIVE,
    RequirementLifecycleStatus.IN_FULFILMENT,
})
_ZERO = Decimal("0")


def _access(ctx: AuthorizationContext, session: Session) -> tuple[str, UUID | None]:
    if ctx.role == RoleCode.BUYER:
        if ctx.buyer_id is None or session.scalar(select(Buyer.id).where(
            Buyer.id == ctx.buyer_id, Buyer.organization_id == ctx.organization_id,
        )) is None:
            raise HTTPException(403, "linked buyer account required")
        return "buyer", ctx.buyer_id
    if ctx.role in _STAFF:
        return "organization_staff", None
    raise HTTPException(403, "buyer or authorized operations role required")


def _coverage_label(accepted: Decimal, required: Decimal) -> str:
    if accepted >= required:
        return "COVERED"
    return "PARTIALLY_COVERED" if accepted > _ZERO else "UNFILLED"


def _request_record(req: Requirement, buyer: Buyer, accepted: Decimal, pending: Decimal) -> dict:
    required = req.required_quantity_kg
    remaining = max(_ZERO, required - accepted)
    return {
        "id": str(req.id),
        "buyer_name": buyer.name,
        "crop": req.crop.value,
        "grade": req.grade.value,
        "lifecycle_status": req.lifecycle_status.value,
        "delivery_window_start": req.delivery_window_start.isoformat(),
        "delivery_window_end": req.delivery_window_end.isoformat(),
        "required_kg": str(required),
        "accepted_offer_kg": str(accepted),
        "pending_offer_kg": str(pending),
        "remaining_offer_kg": str(remaining),
        "coverage_pct": float(min(Decimal("100"), (accepted / required * 100))) if required else 0.0,
        "coverage_status": _coverage_label(accepted, required),
    }


@router.get("/summary")
def marketplace_command_center_summary(
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    """Full permitted portfolio, not just the first page of /marketplace/demand.

    All quantities are current database-derived procurement figures. No inferred
    received/shipped/delivered state, automatic risk scores or merged plan totals.
    """
    scope, buyer_id = _access(context, session)

    requirement_scope = [Buyer.organization_id == context.organization_id]
    if buyer_id is not None:
        requirement_scope.append(Requirement.buyer_id == buyer_id)

    requirements = session.execute(
        select(Requirement, Buyer)
        .join(Buyer, Buyer.id == Requirement.buyer_id)
        .where(*requirement_scope)
        .order_by(Requirement.created_at.desc(), Requirement.id.desc())
    ).all()

    offer_scope = [
        FarmerOffer.organization_id == context.organization_id,
        Buyer.organization_id == context.organization_id,
    ]
    if buyer_id is not None:
        offer_scope.append(Requirement.buyer_id == buyer_id)

    quantities: dict[UUID, dict[OfferStatus, Decimal]] = defaultdict(dict)
    for req_id, status, quantity in session.execute(
        select(FarmerOffer.requirement_id, FarmerOffer.status, func.sum(FarmerOffer.quantity_kg))
        .join(Requirement, Requirement.id == FarmerOffer.requirement_id)
        .join(Buyer, Buyer.id == Requirement.buyer_id)
        .where(*offer_scope, FarmerOffer.status.in_([OfferStatus.ACCEPTED, OfferStatus.PENDING]))
        .group_by(FarmerOffer.requirement_id, FarmerOffer.status)
    ).all():
        quantities[req_id][status] = Decimal(quantity)

    active = []
    drafts = 0
    for req, buyer in requirements:
        if req.lifecycle_status == RequirementLifecycleStatus.DRAFT:
            drafts += 1
        if req.lifecycle_status not in _ACTIVE:
            continue
        values = quantities[req.id]
        active.append(_request_record(
            req, buyer,
            values.get(OfferStatus.ACCEPTED, _ZERO),
            values.get(OfferStatus.PENDING, _ZERO),
        ))

    requested = sum((Decimal(r["required_kg"]) for r in active), _ZERO)
    accepted = sum((Decimal(r["accepted_offer_kg"]) for r in active), _ZERO)
    pending = sum((Decimal(r["pending_offer_kg"]) for r in active), _ZERO)
    remaining = sum((Decimal(r["remaining_offer_kg"]) for r in active), _ZERO)
    uncovered = [r for r in active if Decimal(r["remaining_offer_kg"]) > _ZERO]
    uncovered.sort(key=lambda r: (r["delivery_window_start"], -Decimal(r["remaining_offer_kg"]), r["id"]))
    covered = sum(1 for r in active if r["coverage_status"] == "COVERED")
    partially_covered = sum(1 for r in active if r["coverage_status"] == "PARTIALLY_COVERED")

    by_crop: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"requests": 0, "required_kg": _ZERO, "accepted_offer_kg": _ZERO}
    )
    for row in active:
        item = by_crop[row["crop"]]
        item["requests"] += 1
        item["required_kg"] += Decimal(row["required_kg"])
        item["accepted_offer_kg"] += Decimal(row["accepted_offer_kg"])

    # This is a state-change *feed*, not a domain-event audit ledger.
    # Only offer status and creation timestamp are available from this model.
    offer_rows = session.execute(
        select(FarmerOffer, Requirement, Farmer, Buyer)
        .join(Requirement, Requirement.id == FarmerOffer.requirement_id)
        .join(Buyer, Buyer.id == Requirement.buyer_id)
        .join(Farmer, Farmer.id == FarmerOffer.farmer_id)
        .where(*offer_scope, Farmer.organization_id == context.organization_id)
        .order_by(FarmerOffer.created_at.desc(), FarmerOffer.id.desc())
        .limit(8)
    ).all()
    recent_offers = [{
        "id": str(offer.id), "requirement_id": str(req.id),
        "buyer_name": buyer.name, "farmer_name": farmer.name,
        "crop": req.crop.value, "quantity_kg": str(offer.quantity_kg),
        "status": offer.status.value,
        "created_at": offer.created_at.isoformat() if offer.created_at else None,
    } for offer, req, farmer, buyer in offer_rows]

    return {
        "scope": scope,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "coverage_basis": "accepted marketplace farmer offers; not received or delivered supply",
        "totals": {
            "all_requests": len(requirements),
            "active_requests": len(active),
            "draft_requests": drafts,
            "covered_active_requests": covered,
            "partially_covered_active_requests": partially_covered,
            "unfilled_active_requests": len(active) - covered - partially_covered,
            "requests_needing_supply": len(uncovered),
            "requested_kg": str(requested),
            "accepted_offer_kg": str(accepted),
            "pending_offer_kg": str(pending),
            "remaining_offer_kg": str(remaining),
            "coverage_pct": float(min(Decimal("100"), accepted / requested * 100)) if requested else None,
        },
        "attention": uncovered[:10],
        "recent_requests": active[:8],
        "recent_offers": recent_offers,
        "by_crop": [
            {"crop": crop, "requests": values["requests"],
             "required_kg": str(values["required_kg"]),
             "accepted_offer_kg": str(values["accepted_offer_kg"])}
            for crop, values in sorted(by_crop.items())
        ],
        "limits": {
            "attention": 10, "recent_requests": 8, "recent_offers": 8,
            "no_physical_fulfilment_inference": True,
            "no_legacy_allocation_merging": True,
        },
    }
