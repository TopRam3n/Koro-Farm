"""Scoped marketplace receiving/inspection API.

Receipt/inspection events are tied directly to ACCEPTED FarmerOffer records.
Legacy SupplyAllocation receipts are intentionally not written or merged.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.domain.common import Grade
from app.fulfilment.domain.models import FulfilmentNode
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.main_dependencies import get_session
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.marketplace.fulfilment.models import MarketplaceInspectionStatus, MarketplaceReceipt
from app.supply.domain.models import Farmer, ProductionLot

router = APIRouter(prefix="/marketplace/fulfilment", tags=["marketplace fulfilment"])
_ZERO = Decimal("0")
_STAFF_VIEW = frozenset({
    RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN, RoleCode.PROCUREMENT_MANAGER,
    RoleCode.SUPPLY_COORDINATOR, RoleCode.WAREHOUSE_OPERATOR, RoleCode.AUDITOR,
})
_RECEIVE_ROLES = frozenset({RoleCode.PLATFORM_ADMIN, RoleCode.WAREHOUSE_OPERATOR})
_NODE_ROLES = frozenset({RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN})


class NodeCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    node_type: str = Field(min_length=2, max_length=80)
    parish: str = Field(min_length=2, max_length=100)


class ReceiptCreate(BaseModel):
    fulfilment_node_id: UUID
    received_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    receipt_evidence_reference: str = Field(min_length=3, max_length=500)


class InspectionCreate(BaseModel):
    accepted_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    rejected_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    assigned_grade: Grade | None = None
    rejection_reason: str | None = Field(default=None, max_length=200)
    inspection_evidence_reference: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def verify_inspection(self):
        if self.rejected_quantity_kg > 0 and not (self.rejection_reason or "").strip():
            raise ValueError("rejection reason required when rejecting produce")
        if self.accepted_quantity_kg > 0 and self.assigned_grade is None:
            raise ValueError("assigned grade required when accepting produce")
        if self.accepted_quantity_kg + self.rejected_quantity_kg <= 0:
            raise ValueError("inspection quantities cannot both be zero")
        return self


def _scope(ctx: AuthorizationContext, session: Session) -> tuple[str, UUID | None]:
    if ctx.role == RoleCode.BUYER:
        if ctx.buyer_id is None or session.scalar(select(Buyer.id).where(
            Buyer.id == ctx.buyer_id, Buyer.organization_id == ctx.organization_id,
        )) is None:
            raise HTTPException(403, "linked buyer account required")
        return "buyer", ctx.buyer_id
    if ctx.role == RoleCode.FARMER:
        if ctx.farmer_id is None or session.scalar(select(Farmer.id).where(
            Farmer.id == ctx.farmer_id, Farmer.organization_id == ctx.organization_id,
        )) is None:
            raise HTTPException(403, "linked farmer account required")
        return "farmer", ctx.farmer_id
    if ctx.role in _STAFF_VIEW:
        return "organization_staff", None
    raise HTTPException(403, "fulfilment workspace access denied")


def _require_receive(ctx: AuthorizationContext):
    if ctx.role not in _RECEIVE_ROLES:
        raise HTTPException(403, "warehouse operator permission required")


def _offer_statement(ctx: AuthorizationContext, session: Session):
    scope, linked_id = _scope(ctx, session)
    query = (select(FarmerOffer, Requirement, Buyer, ProductionLot, Farmer)
             .join(Requirement, Requirement.id == FarmerOffer.requirement_id)
             .join(Buyer, Buyer.id == Requirement.buyer_id)
             .join(ProductionLot, ProductionLot.id == FarmerOffer.production_lot_id)
             .join(Farmer, Farmer.id == FarmerOffer.farmer_id)
             .where(FarmerOffer.organization_id == ctx.organization_id,
                    Buyer.organization_id == ctx.organization_id,
                    Farmer.organization_id == ctx.organization_id,
                    ProductionLot.farmer_id == Farmer.id,
                    FarmerOffer.status == OfferStatus.ACCEPTED))
    if scope == "buyer":
        query = query.where(Requirement.buyer_id == linked_id)
    if scope == "farmer":
        query = query.where(FarmerOffer.farmer_id == linked_id)
    return scope, query


def _read_receipt(row: MarketplaceReceipt, node_name: str) -> dict:
    return {
        "id": str(row.id), "offer_id": str(row.offer_id),
        "fulfilment_node_id": str(row.fulfilment_node_id), "fulfilment_node_name": node_name,
        "received_quantity_kg": str(row.received_quantity_kg),
        "received_at": row.received_at.isoformat(),
        "receipt_evidence_reference": row.receipt_evidence_reference,
        "inspection_status": row.inspection_status.value,
        "accepted_quantity_kg": str(row.accepted_quantity_kg),
        "rejected_quantity_kg": str(row.rejected_quantity_kg),
        "assigned_grade": row.assigned_grade.value if row.assigned_grade else None,
        "rejection_reason": row.rejection_reason,
        "inspection_evidence_reference": row.inspection_evidence_reference,
        "inspected_at": row.inspected_at.isoformat() if row.inspected_at else None,
        "evidence_verified": False,  # references alone are NOT certified evidence
    }


@router.get("/nodes")
def list_nodes(session: Session = Depends(get_session),
               ctx: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    _scope(ctx, session)
    nodes = session.scalars(select(FulfilmentNode).where(
        FulfilmentNode.organization_id == ctx.organization_id, FulfilmentNode.active.is_(True),
    ).order_by(FulfilmentNode.name, FulfilmentNode.id)).all()
    return {"items": [{"id": str(n.id), "name": n.name, "node_type": n.node_type, "parish": n.parish} for n in nodes]}


@router.post("/nodes", status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, session: Session = Depends(get_session),
                ctx: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    if ctx.role not in _NODE_ROLES:
        raise HTTPException(403, "organization administrator permission required")
    node = FulfilmentNode(organization_id=ctx.organization_id, name=payload.name.strip(),
                          node_type=payload.node_type.strip(), parish=payload.parish.strip(), active=True)
    session.add(node)
    session.commit()
    session.refresh(node)
    return {"id": str(node.id), "name": node.name, "node_type": node.node_type, "parish": node.parish}


def _key(value: str | None) -> str:
    if value is None or not (4 <= len(value.strip()) <= 150):
        raise HTTPException(400, "Idempotency-Key header of 4–150 characters required")
    return value.strip()


@router.post("/offers/{offer_id}/receipts", status_code=status.HTTP_201_CREATED)
def receive_offer(offer_id: UUID, payload: ReceiptCreate,
                  idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                  session: Session = Depends(get_session),
                  ctx: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    _require_receive(ctx)
    key = _key(idempotency_key)
    # Fast idempotent lookup, followed by a second lookup while the offer is locked.
    existing = session.scalar(select(MarketplaceReceipt).where(
        MarketplaceReceipt.organization_id == ctx.organization_id, MarketplaceReceipt.receipt_key == key,
    ))
    if existing:
        if existing.offer_id != offer_id or existing.fulfilment_node_id != payload.fulfilment_node_id or existing.received_quantity_kg != payload.received_quantity_kg or existing.receipt_evidence_reference != payload.receipt_evidence_reference:
            raise HTTPException(409, "Idempotency-Key already used for another receipt command")
        return _read_receipt(existing, session.get(FulfilmentNode, existing.fulfilment_node_id).name)

    offer = session.scalar(select(FarmerOffer).where(
        FarmerOffer.id == offer_id, FarmerOffer.organization_id == ctx.organization_id,
    ).with_for_update())
    if offer is None or offer.status != OfferStatus.ACCEPTED:
        raise HTTPException(404, "accepted farmer offer not found")
    # Locking the offer serializes multiple receipts against the same commitment.
    again = session.scalar(select(MarketplaceReceipt).where(
        MarketplaceReceipt.organization_id == ctx.organization_id, MarketplaceReceipt.receipt_key == key,
    ))
    if again:
        if again.offer_id != offer_id or again.fulfilment_node_id != payload.fulfilment_node_id or again.received_quantity_kg != payload.received_quantity_kg or again.receipt_evidence_reference != payload.receipt_evidence_reference:
            raise HTTPException(409, "Idempotency-Key already used for another receipt command")
        return _read_receipt(again, session.get(FulfilmentNode, again.fulfilment_node_id).name)

    requirement = session.scalar(select(Requirement).join(Buyer, Buyer.id == Requirement.buyer_id).where(
        Requirement.id == offer.requirement_id, Buyer.organization_id == ctx.organization_id,
    ))
    farmer_ok = session.scalar(select(Farmer.id).where(
        Farmer.id == offer.farmer_id, Farmer.organization_id == ctx.organization_id,
    ))
    lot_ok = session.scalar(select(ProductionLot.id).where(
        ProductionLot.id == offer.production_lot_id, ProductionLot.farmer_id == offer.farmer_id,
    ))
    if requirement is None or farmer_ok is None or lot_ok is None:
        raise HTTPException(404, "accepted offer is outside organization scope")
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        raise HTTPException(409, "cancelled procurement request cannot receive produce")
    node = session.scalar(select(FulfilmentNode).where(
        FulfilmentNode.id == payload.fulfilment_node_id,
        FulfilmentNode.organization_id == ctx.organization_id, FulfilmentNode.active.is_(True),
    ))
    if node is None:
        raise HTTPException(404, "active receiving node not found")
    already_received = sum(session.scalars(select(MarketplaceReceipt.received_quantity_kg).where(
        MarketplaceReceipt.organization_id == ctx.organization_id, MarketplaceReceipt.offer_id == offer_id,
    )).all(), _ZERO)
    if already_received + payload.received_quantity_kg > offer.quantity_kg:
        raise HTTPException(409, "receipt would exceed accepted farmer offer quantity")
    row = MarketplaceReceipt(
        organization_id=ctx.organization_id, offer_id=offer_id,
        fulfilment_node_id=node.id, received_quantity_kg=payload.received_quantity_kg,
        received_at=datetime.now(timezone.utc),
        receipt_evidence_reference=payload.receipt_evidence_reference.strip(),
        receipt_key=key, received_by=ctx.user_id,
        inspection_status=MarketplaceInspectionStatus.PENDING_INSPECTION,
        accepted_quantity_kg=_ZERO, rejected_quantity_kg=_ZERO,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read_receipt(row, node.name)


@router.post("/receipts/{receipt_id}/inspect")
def inspect_receipt(receipt_id: UUID, payload: InspectionCreate,
                    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                    session: Session = Depends(get_session),
                    ctx: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    _require_receive(ctx)
    key = _key(idempotency_key)
    previous = session.scalar(select(MarketplaceReceipt).where(
        MarketplaceReceipt.organization_id == ctx.organization_id, MarketplaceReceipt.inspection_key == key,
    ))
    if previous:
        if previous.id != receipt_id or previous.accepted_quantity_kg != payload.accepted_quantity_kg or previous.rejected_quantity_kg != payload.rejected_quantity_kg or previous.assigned_grade != payload.assigned_grade or (previous.rejection_reason or None) != (payload.rejection_reason or None) or previous.inspection_evidence_reference != payload.inspection_evidence_reference:
            raise HTTPException(409, "Idempotency-Key already used for another inspection command")
        return _read_receipt(previous, session.get(FulfilmentNode, previous.fulfilment_node_id).name)

    receipt = session.scalar(select(MarketplaceReceipt).where(
        MarketplaceReceipt.id == receipt_id, MarketplaceReceipt.organization_id == ctx.organization_id,
    ).with_for_update())
    if receipt is None:
        raise HTTPException(404, "receipt not found")
    if receipt.inspection_status != MarketplaceInspectionStatus.PENDING_INSPECTION:
        raise HTTPException(409, "receipt has already been inspected")
    if payload.accepted_quantity_kg + payload.rejected_quantity_kg != receipt.received_quantity_kg:
        raise HTTPException(422, "inspection must account for the entire received quantity")
    if session.scalar(select(FulfilmentNode.id).where(
        FulfilmentNode.id == receipt.fulfilment_node_id, FulfilmentNode.organization_id == ctx.organization_id,
    )) is None:
        raise HTTPException(404, "receiving node not found")
    receipt.accepted_quantity_kg = payload.accepted_quantity_kg
    receipt.rejected_quantity_kg = payload.rejected_quantity_kg
    receipt.assigned_grade = payload.assigned_grade
    receipt.rejection_reason = payload.rejection_reason.strip() if payload.rejection_reason else None
    receipt.inspection_evidence_reference = payload.inspection_evidence_reference.strip()
    receipt.inspection_status = (
        MarketplaceInspectionStatus.ACCEPTED if payload.rejected_quantity_kg == _ZERO
        else MarketplaceInspectionStatus.REJECTED if payload.accepted_quantity_kg == _ZERO
        else MarketplaceInspectionStatus.PARTIALLY_ACCEPTED
    )
    receipt.inspected_at = datetime.now(timezone.utc)
    receipt.inspected_by = ctx.user_id
    receipt.inspection_key = key
    session.commit()
    session.refresh(receipt)
    return _read_receipt(receipt, session.get(FulfilmentNode, receipt.fulfilment_node_id).name)


@router.get("")
def get_marketplace_fulfilment(
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
    ctx: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    scope, statement = _offer_statement(ctx, session)
    offers = session.execute(statement.order_by(FarmerOffer.created_at.desc(), FarmerOffer.id.desc())).all()
    # Aggregate over the entire authorized set, then limit the rendered rows.
    ids = [offer.id for offer, _, _, _, _ in offers]
    receipts = session.execute(select(MarketplaceReceipt, FulfilmentNode)
        .join(FulfilmentNode, FulfilmentNode.id == MarketplaceReceipt.fulfilment_node_id)
        .where(MarketplaceReceipt.organization_id == ctx.organization_id,
               MarketplaceReceipt.offer_id.in_(ids))
        .order_by(MarketplaceReceipt.received_at.desc(), MarketplaceReceipt.id.desc())).all() if ids else []
    by_offer: dict[UUID, list[MarketplaceReceipt]] = defaultdict(list)
    for receipt, _ in receipts:
        by_offer[receipt.offer_id].append(receipt)
    items = []
    for offer, req, buyer, lot, farmer in offers:
        rows = by_offer[offer.id]
        received = sum((r.received_quantity_kg for r in rows), _ZERO)
        accepted = sum((r.accepted_quantity_kg for r in rows), _ZERO)
        rejected = sum((r.rejected_quantity_kg for r in rows), _ZERO)
        items.append({
            "id": str(offer.id), "offer_id": str(offer.id),
            "requirement_id": str(req.id), "production_lot_id": str(lot.id),
            "buyer_name": buyer.name, "farmer_name": farmer.name, "parish": lot.parish,
            "crop": req.crop.value, "grade": req.grade.value,
            "delivery_window_start": req.delivery_window_start.isoformat(),
            "delivery_window_end": req.delivery_window_end.isoformat(),
            "accepted_offer_kg": str(offer.quantity_kg),
            "received_kg": str(received), "awaiting_receipt_kg": str(max(_ZERO, offer.quantity_kg - received)),
            "inspected_accepted_kg": str(accepted), "inspected_rejected_kg": str(rejected),
            "pending_inspection_kg": str(max(_ZERO, received - accepted - rejected)),
        })
    totals = {
        "accepted_offer_kg": str(sum((Decimal(x["accepted_offer_kg"]) for x in items), _ZERO)),
        "received_kg": str(sum((Decimal(x["received_kg"]) for x in items), _ZERO)),
        "awaiting_receipt_kg": str(sum((Decimal(x["awaiting_receipt_kg"]) for x in items), _ZERO)),
        "inspected_accepted_kg": str(sum((Decimal(x["inspected_accepted_kg"]) for x in items), _ZERO)),
        "inspected_rejected_kg": str(sum((Decimal(x["inspected_rejected_kg"]) for x in items), _ZERO)),
        "pending_inspection_kg": str(sum((Decimal(x["pending_inspection_kg"]) for x in items), _ZERO)),
    }
    return {
        "scope": scope,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "offers_count": len(items),
        "items": items[:limit],
        "receipts_count": len(receipts),
        "receipts": [_read_receipt(r, n.name) for r, n in receipts[:limit]],
        "truncated": len(items) > limit or len(receipts) > limit,
        "note": "Accepted offers are reserved commitments, not deliveries. Receipts and inspections are recorded separately from legacy allocations. Evidence references are not independently verified; shipment/delivery/buyer confirmation are not inferred.",
    }
