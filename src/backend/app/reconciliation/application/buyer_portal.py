"""What a buyer sees of their own orders (R1 WP5, M2). Read-only.

Scope: only orders whose buyer record is the one linked to the buyer's active membership, in that membership's
organization (`buyer_order`). Anything else is "not found", whatever the id, so another buyer's order cannot even be
confirmed to exist.

Quantities are never merged:
* delivered: proof-of-delivery quantity, with corrections;
* confirmed by the buyer: the buyer's own current statements in their account;
* relayed by staff: current statements staff recorded from another channel (P5). Shown apart and labelled, never as
  the buyer's own;
* disputed: open disputes' stated quantities;
* awaiting the buyer: delivered quantity with no current statement;
* still to deliver: required minus delivered, never below zero.
Supplier identities, receipts, grading and internal reconciliation versions are staff records and are not exposed.

Disputes shown: those the buyer raised, and staff disputes about one of the buyer's deliveries, each with its outcome.
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.reconciliation.application import services as trade
from src.backend.app.reconciliation.domain.models import (
    BuyerConfirmation, ConfirmationChannel, Delivery, DeliveryAdjustment, Dispute,
    DisputeResolution, Shipment,
)

ZERO = Decimal("0")
SOURCE_LABELS = {
    ConfirmationChannel.BUYER_ACCOUNT: "Confirmed by the buyer in their account",
    ConfirmationChannel.STAFF_RELAYED: "Relayed by staff from another channel",
    ConfirmationChannel.LEGACY_UNQUANTIFIED: "Legacy yes/no flag; not a confirmed quantity",
}
BUYER_STATUS = {
    "DRAFT": "Being prepared", "PLANNING": "Arranging supply", "ACTIVE": "Supply arranged", "IN_FULFILMENT": "Being fulfilled",
    "RECONCILED": "Delivered; being finalised", "COMPLETED": "Completed", "CLOSED_WITH_VARIANCE": "Closed with an agreed difference",
    "CLOSED": "Closed", "CANCELLED": "Cancelled",
}


class NotYours(LookupError):
    """The order is not one of this buyer's orders (reported as 404)."""


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _orders_query(context: AuthorizationContext):
    return (select(Requirement).join(Buyer, Buyer.id == Requirement.buyer_id)
            .where(Requirement.buyer_id == context.buyer_id, Buyer.organization_id == context.organization_id))


def buyer_order(session: Session, context: AuthorizationContext, requirement_id: UUID) -> Requirement:
    if context.buyer_id is None:
        raise NotYours(requirement_id)
    requirement = session.scalar(_orders_query(context).where(Requirement.id == requirement_id))
    if requirement is None:
        raise NotYours(requirement_id)
    return requirement


def _deliveries(session: Session, requirement_id: UUID) -> list[tuple[Delivery, Shipment]]:
    return list(session.execute(select(Delivery, Shipment).join(Shipment, Shipment.id == Delivery.shipment_id)
                                .where(Shipment.requirement_id == requirement_id)
                                .order_by(Delivery.delivered_at, Shipment.reference, Delivery.id)).all())


def _statements(session: Session, delivery_id: UUID) -> list[BuyerConfirmation]:
    """Oldest first, following the supersedes chain (timestamps can tie); unlinked legacy rows by time."""
    rows = list(session.scalars(select(BuyerConfirmation).where(BuyerConfirmation.delivery_id == delivery_id)
                                .order_by(BuyerConfirmation.created_at, BuyerConfirmation.id)))
    successor = {row.supersedes_id: row for row in rows if row.supersedes_id is not None}
    ordered = [row for row in rows if row.supersedes_id is None or row.supersedes_id not in {r.id for r in rows}]
    chain = []
    for root in ordered:
        node = root
        while node is not None and node not in chain:
            chain.append(node)
            node = successor.get(node.id)
    return chain + [row for row in rows if row not in chain]


def _statement_view(statement: BuyerConfirmation) -> dict:
    view = {"id": str(statement.id), "confirmed_quantity_kg": _text(statement.confirmed_quantity_kg),
            "outcome": statement.outcome.value, "source": statement.channel.value,
            "source_label": SOURCE_LABELS[statement.channel], "note": statement.note, "created_at": statement.created_at}
    if statement.channel == ConfirmationChannel.STAFF_RELAYED:
        view.update({"buyer_representative": statement.buyer_representative,
                     "communication_channel": statement.communication_channel, "stated_at": statement.stated_at})
    return view


def _disputes(session: Session, requirement_id: UUID, delivery_ids: set[UUID]) -> list[dict]:
    disputes = session.scalars(select(Dispute).where(Dispute.requirement_id == requirement_id).order_by(Dispute.created_at)).all()
    visible = [d for d in disputes if d.raised_by_party == "BUYER" or (d.delivery_id is not None and d.delivery_id in delivery_ids)]
    resolutions = {r.dispute_id: r for r in session.scalars(
        select(DisputeResolution).where(DisputeResolution.dispute_id.in_([d.id for d in visible])))} if visible else {}
    return [{"id": str(d.id), "delivery_id": str(d.delivery_id) if d.delivery_id else None,
             "raised_by": "you" if d.raised_by_party == "BUYER" else "your supplier coordinator",
             "quantity_kg": _text(d.quantity_kg) if d.quantity_kg is not None else None, "description": d.description,
             "created_at": d.created_at, "status": resolutions[d.id].outcome if d.id in resolutions else "OPEN",
             "resolution": resolutions[d.id].resolution if d.id in resolutions else None,
             "resolved_at": resolutions[d.id].created_at if d.id in resolutions else None} for d in visible]


def order_summary(session: Session, requirement: Requirement) -> dict:
    delivered = confirmed_own = relayed = awaiting = ZERO
    for delivery, _ in _deliveries(session, requirement.id):
        amount = trade.delivered_kg(session, delivery)
        delivered += amount
        current = trade.current_confirmation(session, delivery.id)
        if current is None or current.channel == ConfirmationChannel.LEGACY_UNQUANTIFIED:
            awaiting += amount
        elif current.channel == ConfirmationChannel.BUYER_ACCOUNT:
            confirmed_own += current.confirmed_quantity_kg
        else:
            relayed += current.confirmed_quantity_kg
    disputed = sum((d.quantity_kg or ZERO for d in trade.open_disputes(session, requirement.id)), ZERO)
    status = requirement.lifecycle_status.value
    return {
        "requirement_id": str(requirement.id), "crop": str(requirement.crop.value if hasattr(requirement.crop, "value") else requirement.crop),
        "grade": str(requirement.grade.value if hasattr(requirement.grade, "value") else requirement.grade),
        "delivery_window_start": requirement.delivery_window_start, "delivery_window_end": requirement.delivery_window_end,
        "destination": requirement.destination, "status": status, "status_label": BUYER_STATUS.get(status, status.title()),
        "quantities": {
            "required_kg": _text(requirement.required_quantity_kg), "delivered_kg": _text(delivered),
            "confirmed_by_you_kg": _text(confirmed_own), "relayed_by_staff_kg": _text(relayed), "disputed_kg": _text(disputed),
            "awaiting_your_confirmation_kg": _text(awaiting),
            "still_to_deliver_kg": _text(max(requirement.required_quantity_kg - delivered, ZERO)),
        },
    }


def list_orders(session: Session, context: AuthorizationContext) -> list[dict]:
    if context.buyer_id is None:
        return []
    requirements = session.scalars(_orders_query(context).order_by(Requirement.delivery_window_start.desc(), Requirement.id)).all()
    return [order_summary(session, requirement) for requirement in requirements]


def order_detail(session: Session, context: AuthorizationContext, requirement_id: UUID) -> dict:
    requirement = buyer_order(session, context, requirement_id)
    deliveries = _deliveries(session, requirement.id)
    rows = []
    for delivery, shipment in deliveries:
        statements = _statements(session, delivery.id)
        corrections = session.scalars(select(DeliveryAdjustment).where(DeliveryAdjustment.delivery_id == delivery.id)
                                      .order_by(DeliveryAdjustment.created_at)).all()
        rows.append({"id": str(delivery.id), "shipment_reference": shipment.reference, "delivered_at": delivery.delivered_at,
                     "delivered_quantity_kg": _text(trade.delivered_kg(session, delivery)),
                     "recorded_quantity_kg": _text(delivery.delivered_quantity_kg),
                     "corrections": [{"delta_kg": _text(c.delta_kg), "reason": c.reason, "created_at": c.created_at} for c in corrections],
                     "current_statement": _statement_view(statements[-1]) if statements else None,
                     "statement_history": [_statement_view(s) for s in statements]})
    return {**order_summary(session, requirement), "deliveries": rows,
            "disputes": _disputes(session, requirement.id, {d.id for d, _ in deliveries})}


CSV_COLUMNS = ["order_id", "crop", "grade", "shipment_reference", "delivery_id", "delivered_at", "delivered_kg",
               "recorded_kg", "corrections", "statement_number", "statement_recorded_at", "outcome", "confirmed_kg",
               "source", "buyer_representative", "communication_channel", "stated_at", "note", "current_statement"]


def _safe_cell(value) -> str:
    """Spreadsheet-safe text: a leading = + - @ (or tab/CR) would be run as a formula by spreadsheet software."""
    text = "" if value is None else (value.isoformat() if isinstance(value, datetime) else str(value))
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def delivery_record(session: Session, context: AuthorizationContext, requirement_id: UUID) -> dict:
    """Every delivery and every statement about it, in order, with its source. One row per statement (a delivery with
    no statement gets one row with outcome NOT_CONFIRMED)."""
    detail = order_detail(session, context, requirement_id)
    rows = []
    for delivery in detail["deliveries"]:
        base = {"order_id": detail["requirement_id"], "crop": detail["crop"], "grade": detail["grade"],
                "shipment_reference": delivery["shipment_reference"], "delivery_id": delivery["id"],
                "delivered_at": delivery["delivered_at"], "delivered_kg": delivery["delivered_quantity_kg"],
                "recorded_kg": delivery["recorded_quantity_kg"], "corrections": len(delivery["corrections"])}
        history = delivery["statement_history"]
        if not history:
            rows.append({**base, "statement_number": 0, "outcome": "NOT_CONFIRMED", "current_statement": "yes"})
        for number, statement in enumerate(history, 1):
            rows.append({**base, "statement_number": number, "statement_recorded_at": statement["created_at"],
                         "outcome": statement["outcome"], "confirmed_kg": statement["confirmed_quantity_kg"],
                         "source": statement["source_label"], "buyer_representative": statement.get("buyer_representative"),
                         "communication_channel": statement.get("communication_channel"),
                         "stated_at": statement.get("stated_at"), "note": statement["note"],
                         "current_statement": "yes" if number == len(history) else "no (superseded)"})
    return {"generated_at": datetime.now(timezone.utc), "order": {k: v for k, v in detail.items() if k not in ("deliveries", "disputes")},
            "rows": rows, "disputes": detail["disputes"]}


def delivery_record_csv(record: dict) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in record["rows"]:
        writer.writerow({column: _safe_cell(row.get(column)) for column in CSV_COLUMNS})
    return buffer.getvalue()


__all__ = ["NotYours", "buyer_order", "delivery_record", "delivery_record_csv", "list_orders", "order_detail"]
