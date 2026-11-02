"""Shipments, deliveries, buyer confirmation, disputes, reconciliation and close-out (R1 WP4).

Every write checks its permission and delegates to reconciliation/application/services.py. Staff routes are
organization-scoped by enforce_path_scope; the buyer routes (`buyer_router`) are further limited to the buyer's own
orders. Physical records are never edited: corrections, later statements and new reconciliation versions are added.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.application.tenancy import tenant_idempotency_key
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.reconciliation.application import services as trade
from src.backend.app.reconciliation.domain.models import (
    BuyerConfirmation, Delivery, DeliveryAdjustment, Dispute, DisputeResolution, ReconciliationRecord,
    RequirementReconciliation, Shipment, ShipmentSublot,
)
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation

router = APIRouter(tags=["shipments", "reconciliation", "trade-evidence"])
buyer_router = APIRouter(prefix="/buyer", tags=["buyer deliveries"])


class ShipmentCreate(BaseModel):
    fulfilment_node_id: UUID
    reference: str = Field(min_length=3, max_length=80)


class AddSublot(BaseModel):
    received_sublot_id: UUID


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class DispatchCommand(BaseModel):
    evidence_reference: str | None = Field(default=None, max_length=500)


class DeliveryCommand(BaseModel):
    delivered_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    delivered_at: datetime
    delivery_evidence_reference: str | None = Field(default=None, max_length=500)
    # Removed in WP4: buyer confirmation is recorded separately, with a quantity and its channel.
    buyer_confirmed: bool | None = None
    buyer_confirmation_evidence: str | None = None


class DeliveryAdjustmentCommand(BaseModel):
    delta_kg: Decimal = Field(max_digits=12, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)
    evidence_reference: str | None = Field(default=None, max_length=500)


class ConfirmationCommand(BaseModel):
    confirmed_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    discrepancy: bool = False
    note: str | None = Field(default=None, max_length=1000)
    evidence_reference: str | None = Field(default=None, max_length=500)


class RelayedConfirmationCommand(ConfirmationCommand):
    buyer_representative: str = Field(min_length=2, max_length=200)
    communication_channel: str = Field(min_length=2, max_length=100, description="e.g. phone call, email, signed delivery note")
    attestation: str = Field(min_length=3, max_length=300)
    stated_at: datetime


class DisputeCommand(BaseModel):
    description: str = Field(min_length=3, max_length=1000)
    delivery_id: UUID | None = None
    quantity_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)


class ResolutionCommand(BaseModel):
    outcome: str = Field(pattern="^(RESOLVED|WITHDRAWN)$")
    resolution: str = Field(min_length=3, max_length=1000)


class ReconcileCommand(BaseModel):
    reason: str | None = Field(default=None, max_length=500, description="Required for a correction (version 2 onward)")
    verification_evidence_reference: str | None = Field(default=None, max_length=500)


class ReviewCommand(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=500)


class CloseCommand(BaseModel):
    accept_variance: bool = False
    reason: str | None = Field(default=None, max_length=500)


class AuditFlagCommand(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    note: str = Field(min_length=3, max_length=1000)
    requirement_id: UUID | None = None


def _run(session: Session, fn):
    try:
        result = fn()
    except trade.TradeForbidden as exc:
        session.rollback()
        raise HTTPException(403, str(exc)) from exc
    except trade.TradeError as exc:
        session.rollback()
        raise HTTPException(exc.status, str(exc)) from exc
    session.commit()
    return result


def _key(key: str | None) -> str:
    if not key:
        raise HTTPException(400, "Idempotency-Key header is required")
    return key


@router.post("/requirements/{requirement_id}/shipments")
def post_shipment(requirement_id: UUID, payload: ShipmentCreate, idempotency_key: str | None = Depends(tenant_idempotency_key),
                  session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _key(idempotency_key)
    return _run(session, lambda: trade.create_shipment(session, context, requirement_id, payload.fulfilment_node_id, payload.reference, key))


@router.post("/shipments/{shipment_id}/sublots")
def post_shipment_sublot(shipment_id: UUID, payload: AddSublot, idempotency_key: str | None = Depends(tenant_idempotency_key),
                         session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _key(idempotency_key)
    from src.backend.app.identity.application.tenancy import require_owned
    require_owned(session, context, "received_sublot", payload.received_sublot_id, "shipment or received sublot not found")
    return _run(session, lambda: trade.add_sublot(session, context, shipment_id, payload.received_sublot_id, key))


@router.post("/shipments/{shipment_id}/cancel")
def post_shipment_cancel(shipment_id: UUID, payload: Reason, session: Session = Depends(get_session),
                         context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _run(session, lambda: trade.cancel_shipment(session, context, shipment_id, payload.reason))


@router.post("/shipments/{shipment_id}/dispatch")
def post_dispatch(shipment_id: UUID, payload: DispatchCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                  session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _key(idempotency_key)
    return _run(session, lambda: trade.dispatch(session, context, shipment_id, payload.evidence_reference, key))


@router.post("/shipments/{shipment_id}/delivery")
def post_delivery(shipment_id: UUID, payload: DeliveryCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                  session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Record what physically arrived. The buyer's confirmation is a separate record (POST /deliveries/{id}/confirmations)."""
    key = _key(idempotency_key)
    if payload.buyer_confirmed or payload.buyer_confirmation_evidence:
        raise HTTPException(422, "buyer confirmation is recorded separately, with the confirmed quantity: "
                                 "the buyer confirms in their account, or staff record it at POST /deliveries/{delivery_id}/confirmations")
    return _run(session, lambda: trade.record_delivery(session, context, shipment_id, payload.delivered_quantity_kg,
                                                       payload.delivered_at, payload.delivery_evidence_reference, key))


@router.post("/deliveries/{delivery_id}/adjustments")
def post_delivery_adjustment(delivery_id: UUID, payload: DeliveryAdjustmentCommand, session: Session = Depends(get_session),
                             context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _run(session, lambda: trade.adjust_delivery(session, context, delivery_id, payload.delta_kg, payload.reason,
                                                       payload.evidence_reference))


@router.post("/deliveries/{delivery_id}/confirmations")
def post_relayed_confirmation(delivery_id: UUID, payload: RelayedConfirmationCommand,
                              idempotency_key: str | None = Depends(tenant_idempotency_key), session: Session = Depends(get_session),
                              context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Staff record a confirmation the buyer gave through another channel. Shown as relayed, never as the buyer's own."""
    return _run(session, lambda: trade.confirm_delivery(
        session, context, delivery_id, payload.confirmed_quantity_kg, discrepancy=payload.discrepancy, note=payload.note,
        evidence_reference=payload.evidence_reference, buyer_representative=payload.buyer_representative,
        communication_channel=payload.communication_channel, attestation=payload.attestation, stated_at=payload.stated_at,
        key=idempotency_key))


@router.post("/requirements/{requirement_id}/disputes")
def post_dispute(requirement_id: UUID, payload: DisputeCommand, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _run(session, lambda: trade.raise_dispute(session, context, requirement_id, payload.description, payload.delivery_id,
                                                     payload.quantity_kg))


@router.post("/disputes/{dispute_id}/resolution")
def post_resolution(dispute_id: UUID, payload: ResolutionCommand, session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _run(session, lambda: trade.resolve_dispute(session, context, dispute_id, payload.outcome, payload.resolution))


@router.post("/requirements/{requirement_id}/reconcile")
def post_reconcile(requirement_id: UUID, payload: ReconcileCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                   session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _key(idempotency_key)
    return _run(session, lambda: trade.reconcile(session, context, requirement_id, payload.reason,
                                                 payload.verification_evidence_reference, key))


@router.post("/reconciliations/{reconciliation_id}/review")
def post_review(reconciliation_id: UUID, payload: ReviewCommand, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _run(session, lambda: trade.review_reconciliation(session, context, reconciliation_id, payload.approve, payload.note))


@router.post("/requirements/{requirement_id}/close")
def post_close(requirement_id: UUID, payload: CloseCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
               session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    key = _key(idempotency_key)
    return _run(session, lambda: trade.close_order(session, context, requirement_id, accept_variance=payload.accept_variance,
                                                   reason=payload.reason, key=key))


@router.post("/audit-flags", status_code=201)
def post_audit_flag(payload: AuditFlagCommand, session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    if payload.requirement_id is not None:
        from src.backend.app.identity.application.tenancy import require_owned
        require_owned(session, context, "requirement", payload.requirement_id)
    return _run(session, lambda: trade.flag_for_audit(session, context, payload.subject, payload.note, payload.requirement_id))


@router.get("/stock-ledger", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def get_stock_ledger(session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Run the stock ledger check for this organization now. Mismatches are recorded, never repaired."""
    from src.backend.app.supply.application.ledger import check_ledger
    found = check_ledger(session, context.organization_id)
    session.commit()
    return {"balanced": not found, "mismatches": found}


def _delivery_view(session: Session, delivery: Delivery) -> dict:
    statements = session.scalars(select(BuyerConfirmation).where(BuyerConfirmation.delivery_id == delivery.id)
                                 .order_by(BuyerConfirmation.created_at)).all()
    adjustments = session.scalars(select(DeliveryAdjustment).where(DeliveryAdjustment.delivery_id == delivery.id)
                                  .order_by(DeliveryAdjustment.created_at)).all()
    current = statements[-1] if statements else None
    return {"id": str(delivery.id), "shipment_id": str(delivery.shipment_id), "recorded_quantity_kg": str(delivery.delivered_quantity_kg),
            "delivered_quantity_kg": str(trade.delivered_kg(session, delivery)), "delivered_at": delivery.delivered_at,
            "evidence_reference": delivery.delivery_evidence_reference,
            "adjustments": [{"delta_kg": str(a.delta_kg), "reason": a.reason, "created_at": a.created_at} for a in adjustments],
            "confirmation": None if current is None else {
                "id": str(current.id), "confirmed_quantity_kg": str(current.confirmed_quantity_kg), "outcome": current.outcome.value,
                "channel": current.channel.value, "buyer_representative": current.buyer_representative,
                "communication_channel": current.communication_channel, "attestation": current.attestation,
                "stated_at": current.stated_at, "note": current.note, "created_at": current.created_at},
            "confirmation_history": len(statements)}


@router.get("/requirements/{requirement_id}/fulfilment-record", dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def get_fulfilment_record(requirement_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Everything physical and commercial about an order's fulfilment, with deterministic figures."""
    requirement = session.get(Requirement, requirement_id)
    figures, variances, basis = trade.order_figures(session, requirement)
    allocations = session.execute(select(SupplyAllocation, ProductionLot, Farmer)
                                  .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
                                  .join(Farmer, Farmer.id == ProductionLot.farmer_id)
                                  .where(SupplyAllocation.requirement_id == requirement_id, SupplyAllocation.role == AllocationRole.COMMITTED)).all()
    names = {a.id: (farmer.name, lot.parish) for a, lot, farmer in allocations}
    receipts = session.scalars(select(ReceivedSublot).where(ReceivedSublot.allocation_id.in_(list(names)), ReceivedSublot.entry_type == "RECEIPT")
                               .order_by(ReceivedSublot.received_at)).all() if names else []
    shipped = {link.received_sublot_id: link.shipment_id for link in session.scalars(select(ShipmentSublot))
               if link.received_sublot_id in {r.id for r in receipts}}
    shipments = session.scalars(select(Shipment).where(Shipment.requirement_id == requirement_id).order_by(Shipment.created_at)).all()
    deliveries = {d.shipment_id: d for d in session.scalars(select(Delivery).where(Delivery.shipment_id.in_([s.id for s in shipments])))} if shipments else {}
    disputes = session.scalars(select(Dispute).where(Dispute.requirement_id == requirement_id).order_by(Dispute.created_at)).all()
    resolutions = {r.dispute_id: r for r in session.scalars(select(DisputeResolution).where(DisputeResolution.dispute_id.in_([d.id for d in disputes])))} if disputes else {}
    records = session.scalars(select(ReconciliationRecord).where(ReconciliationRecord.requirement_id == requirement_id)
                              .order_by(ReconciliationRecord.version)).all()
    effective = trade.effective_reconciliation(session, requirement_id)
    return {
        "requirement_id": str(requirement_id), "lifecycle_status": requirement.lifecycle_status.value,
        "figures": figures, "variances": variances, "completion": trade.completion_check(session, requirement, figures),
        "receivable_allocations": [{"allocation_id": str(a.id), "farmer_name": farmer.name, "parish": lot.parish,
                                    "obligation_kg": str(a.obligation_kg)} for a, lot, farmer in allocations if a.status == AllocationStatus.COMMITTED],
        "receipts": [{"id": str(r.id), "allocation_id": str(r.allocation_id), "farmer_name": names[r.allocation_id][0],
                      "fulfilment_node_id": str(r.fulfilment_node_id),
                      **dict(zip(("received_kg", "accepted_kg", "rejected_kg"), (str(v) for v in trade.effective_receipt(session, r)))),
                      "graded": r.graded_at is not None, "assigned_grade": r.assigned_grade.value if r.assigned_grade else None,
                      "rejection_reason": r.rejection_reason, "received_at": r.received_at,
                      "corrections": len(session.scalars(select(ReceivedSublot.id).where(ReceivedSublot.adjusts_sublot_id == r.id)).all()),
                      "shipment_id": str(shipped[r.id]) if r.id in shipped else None} for r in receipts],
        "shipments": [{"id": str(s.id), "reference": s.reference, "status": s.status.value, "dispatched_at": s.dispatched_at,
                       "cancellation_reason": s.cancellation_reason,
                       "delivery": _delivery_view(session, deliveries[s.id]) if s.id in deliveries else None} for s in shipments],
        "disputes": [{"id": str(d.id), "delivery_id": str(d.delivery_id) if d.delivery_id else None, "party": d.raised_by_party,
                      "quantity_kg": str(d.quantity_kg) if d.quantity_kg is not None else None, "description": d.description,
                      "created_at": d.created_at, "status": resolutions[d.id].outcome if d.id in resolutions else "OPEN",
                      "resolution": resolutions[d.id].resolution if d.id in resolutions else None} for d in disputes],
        "reconciliations": [{"id": str(r.id), "version": r.version, "status": r.status, "figures": r.figures, "variances": r.variances,
                             "reason": r.reason, "material_change": r.material_change, "legacy": r.legacy,
                             "created_by_user_id": str(r.created_by_user_id) if r.created_by_user_id else None,
                             "reviewed_by_user_id": str(r.reviewed_by_user_id) if r.reviewed_by_user_id else None,
                             "created_at": r.created_at} for r in records],
        "effective_reconciliation_version": effective.version if effective else None,
        "unconfirmed_deliveries": basis["unconfirmed_deliveries"],
    }


@router.get("/farmers/{farmer_id}/trade-performance-passport")
def passport(farmer_id: UUID, session: Session = Depends(get_session)) -> dict:
    """Only measures computable from records. Quality acceptance is accepted / received over reconciled, buyer-confirmed
    trades. Quantity fulfilment and any reliability index are not assessed until they are defined (WP4, M10)."""
    if session.get(Farmer, farmer_id) is None:
        raise HTTPException(404, "farmer not found")
    effective = select(ReconciliationRecord.requirement_id).where(ReconciliationRecord.status == "EFFECTIVE")
    legacy = select(RequirementReconciliation.requirement_id).where(
        RequirementReconciliation.buyer_confirmed.is_(True), RequirementReconciliation.verification_evidence_reference.is_not(None),
        or_(RequirementReconciliation.dispute_status.is_(None), RequirementReconciliation.dispute_status == "RESOLVED"))
    rows = session.execute(select(ReceivedSublot, SupplyAllocation).join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
                           .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
                           .where(ProductionLot.farmer_id == farmer_id,
                                  or_(SupplyAllocation.requirement_id.in_(effective), SupplyAllocation.requirement_id.in_(legacy)))).all()
    received = sum((s.received_quantity_kg for s, _ in rows), Decimal("0"))
    accepted = sum((s.accepted_quantity_kg for s, _ in rows), Decimal("0"))
    trades = len({a.requirement_id for _, a in rows})
    quality_rate = (accepted * Decimal("100") / received) if received else None
    return {"farmer_id": str(farmer_id), "completed_institutional_trades": trades,
            "quality_acceptance_rate_pct": str(quality_rate) if quality_rate is not None else None,
            "quantity_fulfilment_rate_pct": None, "on_time_delivery_rate_pct": None, "fulfilment_reliability_index": None,
            "not_assessed": ["quantity_fulfilment_rate_pct", "on_time_delivery_rate_pct", "fulfilment_reliability_index"],
            "history_maturity": "BUILDING_HISTORY" if trades < 3 else "ESTABLISHED_HISTORY", "financing_eligibility": "NOT_ASSESSED"}


@router.get("/shipments/{shipment_id}/traceability")
def shipment_traceability(shipment_id: UUID, session: Session = Depends(get_session)) -> dict:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(404, "shipment not found")
    rows = session.execute(select(ShipmentSublot, ReceivedSublot, SupplyAllocation, ProductionLot, Farmer)
                           .join(ReceivedSublot, ReceivedSublot.id == ShipmentSublot.received_sublot_id)
                           .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
                           .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
                           .join(Farmer, Farmer.id == ProductionLot.farmer_id)
                           .where(ShipmentSublot.shipment_id == shipment_id)).all()
    return {"shipment_id": str(shipment_id), "status": shipment.status.value, "sources": [{
        "shipment_sublot_id": str(link.id), "received_sublot_id": str(sublot.id), "allocation_id": str(allocation.id),
        "production_lot_id": str(lot.id), "farmer_id": str(farmer.id), "farmer_name": farmer.name,
        "accepted_quantity_kg": str(link.accepted_quantity_kg)} for link, sublot, allocation, lot, farmer in rows]}


@router.get("/production-lots/{lot_id}/shipments")
def lot_shipments(lot_id: UUID, session: Session = Depends(get_session)) -> dict:
    if session.get(ProductionLot, lot_id) is None:
        raise HTTPException(404, "production lot not found")
    rows = session.execute(select(Shipment, ShipmentSublot, ReceivedSublot)
                           .join(ShipmentSublot, ShipmentSublot.shipment_id == Shipment.id)
                           .join(ReceivedSublot, ReceivedSublot.id == ShipmentSublot.received_sublot_id)
                           .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
                           .where(SupplyAllocation.production_lot_id == lot_id)).all()
    return {"production_lot_id": str(lot_id), "shipments": [{
        "shipment_id": str(shipment.id), "reference": shipment.reference, "status": shipment.status.value,
        "received_sublot_id": str(sublot.id), "accepted_quantity_kg": str(link.accepted_quantity_kg)} for shipment, link, sublot in rows]}


# --- Buyers: their own deliveries only ------------------------------------------------------------------------------

@buyer_router.get("/deliveries", dependencies=[Depends(require_permission(PermissionCode.DELIVERY_CONFIRM_OWN))])
def buyer_deliveries(session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> list[dict]:
    if context.buyer_id is None:
        return []
    rows = session.execute(select(Delivery, Shipment, Requirement).join(Shipment, Shipment.id == Delivery.shipment_id)
                           .join(Requirement, Requirement.id == Shipment.requirement_id).join(Buyer, Buyer.id == Requirement.buyer_id)
                           .where(Requirement.buyer_id == context.buyer_id, Buyer.organization_id == context.organization_id)
                           .order_by(Delivery.delivered_at.desc())).all()
    return [{**_delivery_view(session, delivery), "order": f"{str(requirement.crop).replace('_', ' ')}, {requirement.required_quantity_kg} kg",
             "requirement_id": str(requirement.id), "shipment_reference": shipment.reference} for delivery, shipment, requirement in rows]


@buyer_router.post("/deliveries/{delivery_id}/confirmation")
def buyer_confirm(delivery_id: UUID, payload: ConfirmationCommand, idempotency_key: str | None = Depends(tenant_idempotency_key),
                  session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """The authenticated buyer confirms the quantity they received, or reports a discrepancy."""
    return _run(session, lambda: trade.confirm_delivery(session, context, delivery_id, payload.confirmed_quantity_kg,
                                                        discrepancy=payload.discrepancy, note=payload.note,
                                                        evidence_reference=payload.evidence_reference, key=idempotency_key))


@buyer_router.post("/deliveries/{delivery_id}/disputes")
def buyer_dispute(delivery_id: UUID, payload: DisputeCommand, session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    delivery = session.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(404, "delivery not found")
    shipment = session.get(Shipment, delivery.shipment_id)
    return _run(session, lambda: trade.raise_dispute(session, context, shipment.requirement_id, payload.description, delivery_id,
                                                     payload.quantity_kg))
