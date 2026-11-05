"""The fulfilment overview across an organization's open orders (R1 WP5, M1).

Read-only. Every figure comes from the same records and helpers as the per-order fulfilment record
(reconciliation/application/services.py); nothing is estimated. Each queue names the permission needed to act on it,
so the workspace shows a queue as actionable only to people the server would let act. The server still enforces
every action on its own route.
"""
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.reconciliation.application import services as trade
from src.backend.app.reconciliation.domain.models import Delivery, ReconciliationRecord, Shipment, ShipmentStatus
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import SupplyAllocation

# Jamaica keeps UTC-5 all year (no daylight saving), so "today" needs no time-zone database.
JAMAICA = timezone(timedelta(hours=-5), "America/Jamaica")
ENDED = {RequirementLifecycleStatus.COMPLETED, RequirementLifecycleStatus.CLOSED_WITH_VARIANCE,
         RequirementLifecycleStatus.CLOSED, RequirementLifecycleStatus.CANCELLED}
QUEUE_PERMISSIONS = {
    "receipts_today": PermissionCode.RECEIVING_VIEW,
    "ungraded_receipts": PermissionCode.GRADING_RECORD,
    "open_shipments": PermissionCode.SHIPMENT_DISPATCH,
    "in_transit": PermissionCode.DELIVERY_CONFIRM,
    "awaiting_buyer_confirmation": PermissionCode.BUYER_CONFIRMATION_RELAY,
    "sequence_flags": PermissionCode.TRADE_RECONCILE,
    "open_disputes": PermissionCode.TRADE_RECONCILE,
    "reconciliations_pending_review": PermissionCode.TRADE_RECONCILE,
    "ready_to_close": PermissionCode.TRADE_RECONCILE,
}


def _label(requirement: Requirement, buyer: Buyer) -> str:
    return f"{str(requirement.crop.value if hasattr(requirement.crop, 'value') else requirement.crop).replace('_', ' ').title()} for {buyer.name}"


def fulfilment_overview(session: Session, organization_id: UUID, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day_start = datetime.combine(now.astimezone(JAMAICA).date(), time.min, tzinfo=JAMAICA)
    orders = session.execute(select(Requirement, Buyer).join(Buyer, Buyer.id == Requirement.buyer_id)
                             .where(Buyer.organization_id == organization_id,
                                    Requirement.lifecycle_status.in_([RequirementLifecycleStatus.ACTIVE,
                                                                      RequirementLifecycleStatus.IN_FULFILMENT,
                                                                      RequirementLifecycleStatus.RECONCILED]))
                             .order_by(Requirement.delivery_window_start, Requirement.id)).all()
    labels = {requirement.id: _label(requirement, buyer) for requirement, buyer in orders}
    ids = list(labels)
    queues: dict[str, list[dict]] = {name: [] for name in QUEUE_PERMISSIONS}
    if ids:
        receipts = session.execute(
            select(ReceivedSublot, SupplyAllocation.requirement_id, Farmer.name)
            .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
            .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
            .join(Farmer, Farmer.id == ProductionLot.farmer_id)
            .where(SupplyAllocation.requirement_id.in_(ids), ReceivedSublot.entry_type == "RECEIPT")
            .order_by(ReceivedSublot.received_at)).all()
        for receipt, requirement_id, farmer in receipts:
            received, accepted, rejected = trade.effective_receipt(session, receipt)
            item = {"requirement_id": str(requirement_id), "order": labels[requirement_id], "receipt_id": str(receipt.id),
                    "supplier": farmer, "received_kg": format(received.normalize(), "f"), "received_at": receipt.received_at}
            received_at = receipt.received_at if receipt.received_at.tzinfo else receipt.received_at.replace(tzinfo=timezone.utc)
            if received_at >= day_start:
                queues["receipts_today"].append(item)
            if receipt.graded_at is None:
                queues["ungraded_receipts"].append(item)
        shipments = session.scalars(select(Shipment).where(Shipment.requirement_id.in_(ids))
                                    .order_by(Shipment.created_at)).all()
        deliveries = {d.shipment_id: d for d in session.scalars(
            select(Delivery).where(Delivery.shipment_id.in_([s.id for s in shipments])))} if shipments else {}
        for shipment in shipments:
            base = {"requirement_id": str(shipment.requirement_id), "order": labels[shipment.requirement_id],
                    "shipment_id": str(shipment.id), "reference": shipment.reference}
            if shipment.status == ShipmentStatus.OPEN:
                queues["open_shipments"].append(base)
            elif shipment.status == ShipmentStatus.DISPATCHED:
                queues["in_transit"].append({**base, "dispatched_at": shipment.dispatched_at})
            delivery = deliveries.get(shipment.id)
            if delivery is not None and trade.current_confirmation(session, delivery.id) is None:
                queues["awaiting_buyer_confirmation"].append({
                    **base, "delivery_id": str(delivery.id), "delivered_at": delivery.delivered_at,
                    "delivered_kg": format(trade.delivered_kg(session, delivery).normalize(), "f")})
        for requirement, _ in orders:
            for finding in trade.sequence_findings(session, requirement.id):
                if not finding["reviewed"]:
                    queues["sequence_flags"].append({"requirement_id": str(requirement.id), "order": labels[requirement.id],
                                                     "message": finding["message"], "key": finding["key"]})
            for dispute in trade.open_disputes(session, requirement.id):
                queues["open_disputes"].append({
                    "requirement_id": str(requirement.id), "order": labels[requirement.id], "dispute_id": str(dispute.id),
                    "party": dispute.raised_by_party, "description": dispute.description, "created_at": dispute.created_at,
                    "quantity_kg": format(dispute.quantity_kg.normalize(), "f") if dispute.quantity_kg is not None else None})
            if requirement.lifecycle_status == RequirementLifecycleStatus.RECONCILED:
                completion = trade.completion_check(session, requirement)
                queues["ready_to_close"].append({"requirement_id": str(requirement.id), "order": labels[requirement.id],
                                                 "can_complete": completion["can_complete"],
                                                 "blockers": completion["blockers"]})
        for record in session.scalars(select(ReconciliationRecord).where(
                ReconciliationRecord.requirement_id.in_(ids), ReconciliationRecord.status == "PENDING_REVIEW")
                .order_by(ReconciliationRecord.created_at)):
            queues["reconciliations_pending_review"].append({
                "requirement_id": str(record.requirement_id), "order": labels[record.requirement_id],
                "reconciliation_id": str(record.id), "version": record.version, "reason": record.reason,
                "created_by_user_id": str(record.created_by_user_id) if record.created_by_user_id else None})
    return {
        "generated_at": now, "day_start": day_start, "open_orders": len(ids),
        "queues": {name: {"items": items, "count": len(items), "action_permission": QUEUE_PERMISSIONS[name].value}
                   for name, items in queues.items()},
    }
