"""Physical fulfilment after receipt, buyer confirmation, reconciliation and close-out (R1 WP4: M3, M4, M5; P2, P5, P6, P11).

Quantities are kept distinct and never inferred from one another:
  required -> committed -> received -> quality-accepted / rejected -> dispatched -> delivered -> buyer-confirmed,
plus released (reservations given back) and disputed.

* Physical records are never edited. A delivery correction is a DeliveryAdjustment; a buyer's later statement
  supersedes an earlier one; a reconciliation correction is a new version.
* Buyer confirmation is a quantity no greater than what was delivered, with its channel: the authenticated buyer
  (BUYER_ACCOUNT) or attested staff relay (STAFF_RELAYED, naming the buyer's representative, channel, time and
  attestation). Relayed confirmation is never presented as the buyer's own.
* Reconciled is not completed. Completion requires confirmed delivery of the required quantity, every delivery
  confirmed, and no open dispute; otherwise an order ends only through an authorized variance acceptance.
* Close-out releases only undelivered reservations, unused standby and open requests (supply/application/release.py).

Every function works inside the caller's transaction; callers commit. Arithmetic here is deterministic.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event
from src.backend.app.assurance.domain.models import CommandDeduplication
from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from src.backend.app.fulfilment.domain.models import FulfilmentNode, ReceivedSublot
from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode
from src.backend.app.reconciliation.domain.models import (
    AuditFlag, BuyerConfirmation, ConfirmationChannel, ConfirmationOutcome, Delivery, DeliveryAdjustment, Dispute,
    DisputeResolution, ReconciliationRecord, Shipment, ShipmentStatus, ShipmentSublot,
)
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, ConsentStatus, SupplyAllocation

ZERO = Decimal("0")
FRESH = {"populate_existing": True}
ENDED = (RequirementLifecycleStatus.CANCELLED, RequirementLifecycleStatus.COMPLETED,
         RequirementLifecycleStatus.CLOSED_WITH_VARIANCE, RequirementLifecycleStatus.CLOSED)
MATERIAL_FIGURES = ("received_kg", "accepted_kg", "rejected_kg", "delivered_kg", "buyer_confirmed_kg", "committed_kg")


class TradeError(ValueError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class TradeForbidden(PermissionError):
    pass


def _require(actor: AuthorizationContext, permission: PermissionCode, what: str) -> None:
    if permission not in actor.permissions:
        raise TradeForbidden(f"{what} requires the {permission.value} permission")


def _replay(session: Session, command: str, key: str | None) -> dict | None:
    if not key:
        return None
    row = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == command,
                                                            CommandDeduplication.idempotency_key == key))
    return row.result if row else None


def _remember(session: Session, command: str, key: str | None, result: dict) -> dict:
    if key:
        session.add(CommandDeduplication(command_type=command, idempotency_key=key, result=result))
    return result


def _lock_requirement(session: Session, requirement_id: UUID) -> Requirement:
    requirement = session.scalar(select(Requirement).where(Requirement.id == requirement_id).with_for_update().execution_options(**FRESH))
    if requirement is None:
        raise TradeError("order not found", 404)
    return requirement


def _organization(session: Session, requirement: Requirement) -> UUID:
    return session.scalar(select(Buyer.organization_id).where(Buyer.id == requirement.buyer_id))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --- Figures --------------------------------------------------------------------------------------------------------

def delivered_kg(session: Session, delivery: Delivery) -> Decimal:
    adjustments = session.scalar(select(func.coalesce(func.sum(DeliveryAdjustment.delta_kg), 0))
                                 .where(DeliveryAdjustment.delivery_id == delivery.id)) or ZERO
    return delivery.delivered_quantity_kg + Decimal(adjustments)


def current_confirmation(session: Session, delivery_id: UUID) -> BuyerConfirmation | None:
    """The buyer's latest statement about a delivery (a later one supersedes earlier ones)."""
    return session.scalar(select(BuyerConfirmation).where(BuyerConfirmation.delivery_id == delivery_id)
                          .order_by(BuyerConfirmation.created_at.desc(), BuyerConfirmation.id.desc()).limit(1))


def open_disputes(session: Session, requirement_id: UUID) -> list[Dispute]:
    resolved = select(DisputeResolution.dispute_id)
    return session.scalars(select(Dispute).where(Dispute.requirement_id == requirement_id, Dispute.id.not_in(resolved))
                           .order_by(Dispute.created_at)).all()


def order_figures(session: Session, requirement: Requirement) -> tuple[dict, dict, dict]:
    """(figures, variances, basis) for an order, computed from records only."""
    allocations = session.scalars(select(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement.id,
                                                                 SupplyAllocation.role == AllocationRole.COMMITTED)).all()
    ids = [a.id for a in allocations]
    sums = session.execute(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0),
                                  func.coalesce(func.sum(ReceivedSublot.accepted_quantity_kg), 0),
                                  func.coalesce(func.sum(ReceivedSublot.rejected_quantity_kg), 0))
                           .where(ReceivedSublot.allocation_id.in_(ids))).one() if ids else (0, 0, 0)
    received, accepted, rejected = (Decimal(v or 0) for v in sums)
    receipts = session.scalars(select(ReceivedSublot).where(ReceivedSublot.allocation_id.in_(ids),
                                                            ReceivedSublot.entry_type == "RECEIPT")).all() if ids else []
    ungraded = [r for r in receipts if r.graded_at is None]
    committed = ZERO
    for allocation in allocations:
        if allocation.consent_status != ConsentStatus.RECORDED:
            continue
        if allocation.status == AllocationStatus.COMMITTED:
            committed += allocation.quantity_kg
        elif allocation.status == AllocationStatus.LOST:
            committed += sum((r.received_quantity_kg for r in receipts if r.allocation_id == allocation.id), ZERO)
    shipments = session.scalars(select(Shipment).where(Shipment.requirement_id == requirement.id)).all()
    shipped = {s.id: session.scalar(select(func.coalesce(func.sum(ShipmentSublot.accepted_quantity_kg), 0))
                                    .where(ShipmentSublot.shipment_id == s.id)) or ZERO for s in shipments}
    dispatched = sum((Decimal(shipped[s.id]) for s in shipments if s.status in (ShipmentStatus.DISPATCHED, ShipmentStatus.DELIVERED)), ZERO)
    deliveries = session.scalars(select(Delivery).join(Shipment, Shipment.id == Delivery.shipment_id)
                                 .where(Shipment.requirement_id == requirement.id)).all()
    delivered, confirmed, legacy, unconfirmed, discrepancies, confirmation_ids = ZERO, ZERO, ZERO, [], [], []
    for delivery in deliveries:
        amount = delivered_kg(session, delivery)
        delivered += amount
        statement = current_confirmation(session, delivery.id)
        if statement is None:
            unconfirmed.append(str(delivery.id))
            continue
        confirmation_ids.append(str(statement.id))
        if statement.channel == ConfirmationChannel.LEGACY_UNQUANTIFIED:
            legacy += amount
            unconfirmed.append(str(delivery.id))
            continue
        confirmed += statement.confirmed_quantity_kg
        if statement.outcome == ConfirmationOutcome.DISCREPANCY:
            discrepancies.append(str(delivery.id))
    disputes = open_disputes(session, requirement.id)
    released = sum(((a.released_quantity_kg or ZERO) for a in allocations), ZERO)
    figures = {
        "required_kg": requirement.required_quantity_kg, "committed_kg": committed, "received_kg": received,
        "accepted_kg": accepted, "rejected_kg": rejected, "ungraded_receipts": len(ungraded), "dispatched_kg": dispatched,
        "delivered_kg": delivered, "buyer_confirmed_kg": confirmed, "legacy_unquantified_confirmation_kg": legacy,
        "unconfirmed_deliveries": len(unconfirmed), "deliveries_with_discrepancy": len(discrepancies),
        "open_disputes": len(disputes), "disputed_kg": sum((d.quantity_kg or ZERO for d in disputes), ZERO),
        "released_kg": released,
    }
    variances = {
        "required_minus_committed_kg": requirement.required_quantity_kg - committed,
        "required_minus_received_kg": requirement.required_quantity_kg - received,
        "required_minus_accepted_kg": requirement.required_quantity_kg - accepted,
        "accepted_not_dispatched_kg": accepted - dispatched,
        "dispatched_minus_delivered_kg": dispatched - delivered,
        "delivered_minus_confirmed_kg": delivered - confirmed,
        "required_minus_confirmed_kg": requirement.required_quantity_kg - confirmed,
    }
    basis = {"receipts": sorted(str(r.id) for r in receipts), "shipments": sorted(str(s.id) for s in shipments),
             "deliveries": sorted(str(d.id) for d in deliveries), "confirmations": sorted(confirmation_ids),
             "unconfirmed_deliveries": sorted(unconfirmed), "open_disputes": sorted(str(d.id) for d in disputes)}

    def text(values):
        return {k: (format(v.normalize(), "f") if isinstance(v, Decimal) else v) for k, v in values.items()}
    return text(figures), text(variances), basis


# --- Shipments and deliveries ---------------------------------------------------------------------------------------

def create_shipment(session: Session, actor: AuthorizationContext, requirement_id: UUID, fulfilment_node_id: UUID,
                    reference: str, key: str | None) -> dict:
    _require(actor, PermissionCode.SHIPMENT_CREATE, "creating a shipment")
    if (done := _replay(session, "shipment.create", key)) is not None:
        return done
    requirement = _lock_requirement(session, requirement_id)
    if requirement.lifecycle_status in ENDED:
        raise TradeError("this order has ended; no new shipments")
    node = session.get(FulfilmentNode, fulfilment_node_id)
    if node is None or node.organization_id != actor.organization_id:
        raise TradeError("fulfilment site not found", 404)
    if not node.active:
        raise TradeError("this fulfilment site is deactivated")
    shipment = Shipment(requirement_id=requirement_id, fulfilment_node_id=fulfilment_node_id, reference=reference.strip())
    try:
        with session.begin_nested():
            session.add(shipment)
            session.flush()
    except IntegrityError as exc:
        raise TradeError("this site already has a shipment with that reference") from exc
    result = {"shipment_id": str(shipment.id), "status": shipment.status.value, "reference": shipment.reference}
    record_event(session, actor, "shipment.created", "requirement", requirement_id, result, idempotency_key=key)
    return _remember(session, "shipment.create", key, result)


def effective_receipt(session: Session, sublot: ReceivedSublot) -> tuple[Decimal, Decimal, Decimal]:
    """(received, accepted, rejected) for a receipt including its corrections."""
    rows = session.execute(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0),
                                  func.coalesce(func.sum(ReceivedSublot.accepted_quantity_kg), 0),
                                  func.coalesce(func.sum(ReceivedSublot.rejected_quantity_kg), 0))
                           .where((ReceivedSublot.id == sublot.id) | (ReceivedSublot.adjusts_sublot_id == sublot.id))).one()
    return tuple(Decimal(v or 0) for v in rows)


def add_sublot(session: Session, actor: AuthorizationContext, shipment_id: UUID, received_sublot_id: UUID, key: str | None) -> dict:
    _require(actor, PermissionCode.SHIPMENT_CREATE, "adding produce to a shipment")
    if (done := _replay(session, "shipment.add_sublot", key)) is not None:
        return done
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    sublot = session.scalar(select(ReceivedSublot).where(ReceivedSublot.id == received_sublot_id).with_for_update())
    if shipment is None or sublot is None:
        raise TradeError("shipment or received sublot not found", 404)
    allocation = session.get(SupplyAllocation, sublot.allocation_id)
    if sublot.entry_type != "RECEIPT":
        raise TradeError("a correction record cannot be shipped; ship the receipt it corrects")
    if shipment.status != ShipmentStatus.OPEN or allocation.requirement_id != shipment.requirement_id:
        raise TradeError("sublot cannot be added to this shipment")
    _, accepted, _ = effective_receipt(session, sublot)
    if sublot.graded_at is None or accepted <= 0:
        raise TradeError("only graded, accepted quantity may be shipped")
    if session.scalar(select(ShipmentSublot.id).where(ShipmentSublot.received_sublot_id == sublot.id)):
        raise TradeError("sublot is already assigned to a shipment")
    session.add(ShipmentSublot(shipment_id=shipment.id, received_sublot_id=sublot.id, accepted_quantity_kg=accepted))
    result = {"shipment_id": str(shipment.id), "accepted_quantity_kg": str(accepted)}
    record_event(session, actor, "shipment.sublot_added", "requirement", shipment.requirement_id,
                 {**result, "received_sublot_id": str(sublot.id)}, idempotency_key=key)
    return _remember(session, "shipment.add_sublot", key, result)


def cancel_shipment(session: Session, actor: AuthorizationContext, shipment_id: UUID, reason: str) -> dict:
    """Abandon an open shipment before dispatch. Its produce returns to the received, unshipped pool."""
    _require(actor, PermissionCode.SHIPMENT_CREATE, "cancelling a shipment")
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    if shipment is None:
        raise TradeError("shipment not found", 404)
    if shipment.status != ShipmentStatus.OPEN:
        raise TradeError("only an open shipment can be cancelled; dispatched produce is reconciled, not cancelled")
    links = session.scalars(select(ShipmentSublot).where(ShipmentSublot.shipment_id == shipment.id)).all()
    removed = [str(link.received_sublot_id) for link in links]
    for link in links:
        session.delete(link)  # composition of a never-dispatched shipment; the event below keeps the record
    shipment.status, shipment.cancelled_at, shipment.cancellation_reason = ShipmentStatus.CANCELLED, datetime.now(timezone.utc), reason
    record_event(session, actor, "shipment.cancelled", "requirement", shipment.requirement_id,
                 {"shipment_id": str(shipment.id), "reason": reason, "removed_received_sublots": removed})
    return {"shipment_id": str(shipment.id), "status": shipment.status.value}


def dispatch(session: Session, actor: AuthorizationContext, shipment_id: UUID, evidence_reference: str | None, key: str | None) -> dict:
    _require(actor, PermissionCode.SHIPMENT_DISPATCH, "dispatching a shipment")
    if (done := _replay(session, "shipment.dispatch", key)) is not None:
        return done
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    if shipment is None:
        raise TradeError("shipment not found", 404)
    if shipment.status != ShipmentStatus.OPEN:
        raise TradeError("shipment is not open")
    quantity = session.scalar(select(func.coalesce(func.sum(ShipmentSublot.accepted_quantity_kg), 0)).where(ShipmentSublot.shipment_id == shipment.id)) or ZERO
    if quantity <= 0:
        raise TradeError("shipment contains no accepted sublots")
    shipment.status, shipment.dispatched_at, shipment.dispatch_evidence_reference = ShipmentStatus.DISPATCHED, datetime.now(timezone.utc), evidence_reference
    result = {"shipment_id": str(shipment.id), "status": shipment.status.value, "dispatched_quantity_kg": str(quantity)}
    record_event(session, actor, "shipment.dispatched", "requirement", shipment.requirement_id,
                 {**result, "evidence_reference": evidence_reference, "evidence_verified": False}, idempotency_key=key)
    return _remember(session, "shipment.dispatch", key, result)


def record_delivery(session: Session, actor: AuthorizationContext, shipment_id: UUID, quantity: Decimal, delivered_at: datetime,
                    evidence_reference: str | None, key: str | None) -> dict:
    """Record what physically arrived. This is not the buyer's confirmation (see confirm_delivery)."""
    _require(actor, PermissionCode.DELIVERY_CONFIRM, "recording a delivery")
    if (done := _replay(session, "shipment.delivery", key)) is not None:
        return done
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    if (done := _replay(session, "shipment.delivery", key)) is not None:
        return done
    if shipment is None or shipment.status != ShipmentStatus.DISPATCHED:
        raise TradeError("shipment is not dispatched")
    if _aware(delivered_at) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise TradeError("a delivery cannot be recorded in the future", 422)
    dispatched = session.scalar(select(func.coalesce(func.sum(ShipmentSublot.accepted_quantity_kg), 0)).where(ShipmentSublot.shipment_id == shipment.id)) or ZERO
    if quantity < 0 or quantity > dispatched:
        raise TradeError(f"delivered quantity must be between 0 and the {dispatched} kg dispatched")
    delivery = Delivery(shipment_id=shipment.id, delivered_quantity_kg=quantity, delivered_at=delivered_at,
                        delivery_evidence_reference=evidence_reference, buyer_confirmed=False,
                        recorded_by_user_id=actor.user_id if isinstance(actor.user_id, UUID) else None)
    session.add(delivery)
    session.flush()
    shipment.status = ShipmentStatus.DELIVERED
    result = {"delivery_id": str(delivery.id), "shipment_id": str(shipment.id), "delivered_quantity_kg": str(quantity),
              "buyer_confirmation": "not yet confirmed",
              "delivery_verification": "evidence_recorded" if evidence_reference else "unverified"}
    record_event(session, actor, "delivery.recorded", "requirement", shipment.requirement_id, result, idempotency_key=key)
    return _remember(session, "shipment.delivery", key, result)


def _delivery_scope(session: Session, delivery_id: UUID) -> tuple[Delivery, Shipment, Requirement]:
    delivery = session.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update())
    if delivery is None:
        raise TradeError("delivery not found", 404)
    shipment = session.get(Shipment, delivery.shipment_id)
    return delivery, shipment, session.get(Requirement, shipment.requirement_id)


def adjust_delivery(session: Session, actor: AuthorizationContext, delivery_id: UUID, delta_kg: Decimal, reason: str,
                    evidence_reference: str | None) -> dict:
    _require(actor, PermissionCode.DELIVERY_CONFIRM, "correcting a delivery")
    delivery, shipment, requirement = _delivery_scope(session, delivery_id)
    if delta_kg == 0:
        raise TradeError("a correction must change the delivered quantity", 422)
    dispatched = session.scalar(select(func.coalesce(func.sum(ShipmentSublot.accepted_quantity_kg), 0)).where(ShipmentSublot.shipment_id == shipment.id)) or ZERO
    corrected = delivered_kg(session, delivery) + delta_kg
    if corrected < 0 or corrected > dispatched:
        raise TradeError(f"the corrected delivery must be between 0 and the {dispatched} kg dispatched")
    statement = current_confirmation(session, delivery.id)
    if statement is not None and statement.channel != ConfirmationChannel.LEGACY_UNQUANTIFIED and statement.confirmed_quantity_kg > corrected:
        raise TradeError("the buyer has confirmed more than the corrected quantity; record the buyer's new statement first")
    adjustment = DeliveryAdjustment(organization_id=actor.organization_id, delivery_id=delivery.id, delta_kg=delta_kg, reason=reason,
                                    evidence_reference=evidence_reference, recorded_by_user_id=actor.user_id)
    session.add(adjustment)
    session.flush()
    record_event(session, actor, "delivery.corrected", "requirement", requirement.id, {
        "delivery_id": str(delivery.id), "delta_kg": str(delta_kg), "delivered_kg": str(corrected), "reason": reason})
    return {"delivery_id": str(delivery.id), "delivered_quantity_kg": str(corrected), "adjustment_id": str(adjustment.id)}


def confirm_delivery(session: Session, actor: AuthorizationContext, delivery_id: UUID, quantity: Decimal, *,
                     discrepancy: bool = False, note: str | None = None, evidence_reference: str | None = None,
                     buyer_representative: str | None = None, communication_channel: str | None = None,
                     attestation: str | None = None, stated_at: datetime | None = None, key: str | None = None) -> dict:
    """The buyer's statement about a delivery: confirmation of a quantity, or a reported discrepancy (P5)."""
    if (done := _replay(session, "delivery.confirm", key)) is not None:
        return done
    delivery, shipment, requirement = _delivery_scope(session, delivery_id)
    if actor.role == RoleCode.BUYER:
        _require(actor, PermissionCode.DELIVERY_CONFIRM_OWN, "confirming a delivery")
        if actor.buyer_id is None or actor.buyer_id != requirement.buyer_id:
            raise TradeError("delivery not found", 404)
        channel = ConfirmationChannel.BUYER_ACCOUNT
        stated_at = datetime.now(timezone.utc)
    else:
        _require(actor, PermissionCode.BUYER_CONFIRMATION_RELAY, "recording a buyer's confirmation")
        missing = [name for name, value in (("buyer_representative", buyer_representative), ("communication_channel", communication_channel),
                                            ("attestation", attestation), ("stated_at", stated_at)) if not value]
        if missing:
            raise TradeError(f"a relayed confirmation must name {', '.join(missing)}", 422)
        if _aware(stated_at) > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise TradeError("the buyer's statement cannot be in the future", 422)
        channel = ConfirmationChannel.STAFF_RELAYED
    delivered = delivered_kg(session, delivery)
    if quantity < 0 or quantity > delivered:
        raise TradeError(f"a confirmation cannot exceed the {delivered} kg delivered")
    if discrepancy and not (note and note.strip()):
        raise TradeError("describe the discrepancy", 422)
    previous = current_confirmation(session, delivery.id)
    statement = BuyerConfirmation(
        organization_id=_organization(session, requirement), requirement_id=requirement.id, delivery_id=delivery.id,
        confirmed_quantity_kg=quantity, outcome=ConfirmationOutcome.DISCREPANCY if discrepancy else ConfirmationOutcome.CONFIRMED,
        channel=channel, buyer_representative=buyer_representative, communication_channel=communication_channel,
        attestation=attestation, stated_at=stated_at, note=note, evidence_reference=evidence_reference,
        recorded_by_user_id=actor.user_id if isinstance(actor.user_id, UUID) else None,
        supersedes_id=previous.id if previous else None)
    session.add(statement)
    session.flush()
    dispute_id = None
    if discrepancy:
        dispute = Dispute(organization_id=statement.organization_id, requirement_id=requirement.id, delivery_id=delivery.id,
                          raised_by_user_id=actor.user_id, raised_by_party="BUYER", quantity_kg=delivered - quantity,
                          description=note.strip(), blocking=True)
        session.add(dispute)
        session.flush()
        dispute_id = str(dispute.id)
    result = {"confirmation_id": str(statement.id), "delivery_id": str(delivery.id), "confirmed_quantity_kg": str(quantity),
              "delivered_quantity_kg": str(delivered), "outcome": statement.outcome.value, "channel": channel.value,
              "supersedes": str(previous.id) if previous else None, "dispute_id": dispute_id}
    record_event(session, actor, "delivery.discrepancy_reported" if discrepancy else "delivery.buyer_confirmed", "requirement",
                 requirement.id, result, idempotency_key=key)
    return _remember(session, "delivery.confirm", key, result)


# --- Disputes and audit flags ---------------------------------------------------------------------------------------

def raise_dispute(session: Session, actor: AuthorizationContext, requirement_id: UUID, description: str,
                  delivery_id: UUID | None = None, quantity_kg: Decimal | None = None) -> dict:
    requirement = _lock_requirement(session, requirement_id)
    if actor.role == RoleCode.BUYER:
        _require(actor, PermissionCode.DELIVERY_CONFIRM_OWN, "disputing a delivery")
        if actor.buyer_id is None or actor.buyer_id != requirement.buyer_id:
            raise TradeError("order not found", 404)
        party = "BUYER"
    else:
        _require(actor, PermissionCode.DISPUTE_RAISE, "raising a discrepancy")
        party = "STAFF"
    if delivery_id is not None:
        _, shipment, owner = _delivery_scope(session, delivery_id)
        if owner.id != requirement.id:
            raise TradeError("that delivery belongs to another order", 422)
    dispute = Dispute(organization_id=_organization(session, requirement), requirement_id=requirement.id, delivery_id=delivery_id,
                      raised_by_user_id=actor.user_id, raised_by_party=party, quantity_kg=quantity_kg,
                      description=description.strip(), blocking=True)
    session.add(dispute)
    session.flush()
    record_event(session, actor, "dispute.raised", "requirement", requirement.id, {
        "dispute_id": str(dispute.id), "delivery_id": str(delivery_id) if delivery_id else None, "party": party,
        "quantity_kg": str(quantity_kg) if quantity_kg is not None else None})
    return {"dispute_id": str(dispute.id), "status": "OPEN"}


def resolve_dispute(session: Session, actor: AuthorizationContext, dispute_id: UUID, outcome: str, resolution: str) -> dict:
    _require(actor, PermissionCode.TRADE_RECONCILE, "resolving a dispute")
    if outcome not in ("RESOLVED", "WITHDRAWN"):
        raise TradeError("outcome must be RESOLVED or WITHDRAWN", 422)
    dispute = session.scalar(select(Dispute).where(Dispute.id == dispute_id).with_for_update())
    if dispute is None or dispute.organization_id != actor.organization_id:
        raise TradeError("dispute not found", 404)
    if session.scalar(select(DisputeResolution.id).where(DisputeResolution.dispute_id == dispute.id)):
        raise TradeError("this dispute already has an outcome")
    row = DisputeResolution(organization_id=dispute.organization_id, dispute_id=dispute.id, outcome=outcome,
                            resolution=resolution.strip(), resolved_by_user_id=actor.user_id)
    session.add(row)
    session.flush()
    record_event(session, actor, "dispute.resolved", "requirement", dispute.requirement_id,
                 {"dispute_id": str(dispute.id), "outcome": outcome, "resolution": resolution})
    return {"dispute_id": str(dispute.id), "status": outcome}


def flag_for_audit(session: Session, actor: AuthorizationContext, subject: str, note: str, requirement_id: UUID | None) -> dict:
    _require(actor, PermissionCode.AUDIT_FLAG, "flagging an issue")
    flag = AuditFlag(organization_id=actor.organization_id, requirement_id=requirement_id, subject=subject.strip(),
                     note=note.strip(), raised_by_user_id=actor.user_id)
    session.add(flag)
    session.flush()
    return {"audit_flag_id": str(flag.id)}


# --- Reconciliation -------------------------------------------------------------------------------------------------

def effective_reconciliation(session: Session, requirement_id: UUID) -> ReconciliationRecord | None:
    return session.scalar(select(ReconciliationRecord).where(ReconciliationRecord.requirement_id == requirement_id,
                                                             ReconciliationRecord.status == "EFFECTIVE")
                          .order_by(ReconciliationRecord.version.desc()).limit(1))


def reconcile(session: Session, actor: AuthorizationContext, requirement_id: UUID, reason: str | None,
              evidence_reference: str | None, key: str | None) -> dict:
    """Append a new reconciliation version from current records (deterministic; never overwrites)."""
    _require(actor, PermissionCode.TRADE_RECONCILE, "reconciling an order")
    if (done := _replay(session, "requirement.reconcile", key)) is not None:
        return done
    requirement = _lock_requirement(session, requirement_id)
    if (done := _replay(session, "requirement.reconcile", key)) is not None:
        return done
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        raise TradeError("a cancelled order is not reconciled")
    figures, variances, basis = order_figures(session, requirement)
    if not basis["receipts"]:
        raise TradeError("nothing has been received for this order yet")
    if figures["ungraded_receipts"]:
        raise TradeError(f"{figures['ungraded_receipts']} receipt(s) are not graded yet")
    open_with_produce = session.scalar(select(func.count(Shipment.id)).join(ShipmentSublot, ShipmentSublot.shipment_id == Shipment.id)
                                       .where(Shipment.requirement_id == requirement.id, Shipment.status == ShipmentStatus.OPEN)) or 0
    if open_with_produce:
        raise TradeError("an open shipment still holds produce; dispatch it or cancel it with a reason")
    if session.scalar(select(func.count(Shipment.id)).where(Shipment.requirement_id == requirement.id,
                                                             Shipment.status == ShipmentStatus.DISPATCHED)):
        raise TradeError("a dispatched shipment has no recorded delivery yet")
    latest = session.scalar(select(ReconciliationRecord).where(ReconciliationRecord.requirement_id == requirement.id)
                            .order_by(ReconciliationRecord.version.desc()).limit(1))
    if latest is not None and latest.status == "PENDING_REVIEW":
        raise TradeError(f"version {latest.version} is waiting for review; review it before adding another")
    effective = effective_reconciliation(session, requirement.id)
    version = (latest.version if latest else 0) + 1
    if version > 1 and not (reason and len(reason.strip()) >= 3):
        raise TradeError("a corrected reconciliation must give a reason", 422)
    material = bool(effective) and any(effective.figures.get(k) != figures.get(k) for k in MATERIAL_FIGURES)
    record = ReconciliationRecord(
        organization_id=_organization(session, requirement), requirement_id=requirement.id, version=version,
        supersedes_id=effective.id if effective else None, status="PENDING_REVIEW" if material else "EFFECTIVE",
        figures=figures, variances=variances, basis=basis, reason=(reason or "").strip() or None,
        evidence_reference=evidence_reference, material_change=material, created_by_user_id=actor.user_id)
    session.add(record)
    session.flush()
    if record.status == "EFFECTIVE" and requirement.lifecycle_status not in ENDED:
        requirement.lifecycle_status = RequirementLifecycleStatus.RECONCILED
    result = {"reconciliation_id": str(record.id), "version": version, "status": record.status, "figures": figures,
              "variances": variances, "material_change": material,
              "completion": completion_check(session, requirement, figures)}
    record_event(session, actor, "reconciliation.recorded", "requirement", requirement.id,
                 {k: v for k, v in result.items() if k != "completion"}, idempotency_key=key)
    return _remember(session, "requirement.reconcile", key, result)


def review_reconciliation(session: Session, actor: AuthorizationContext, record_id: UUID, approve: bool, note: str) -> dict:
    """A second, different reconciler approves or rejects a material correction (P11)."""
    _require(actor, PermissionCode.TRADE_RECONCILE, "reviewing a reconciliation correction")
    record = session.scalar(select(ReconciliationRecord).where(ReconciliationRecord.id == record_id).with_for_update())
    if record is None or record.organization_id != actor.organization_id:
        raise TradeError("reconciliation not found", 404)
    if record.status != "PENDING_REVIEW":
        raise TradeError("this version is not waiting for review")
    if record.created_by_user_id == actor.user_id:
        raise TradeForbidden("a material correction must be reviewed by someone other than its author")
    record.status = "EFFECTIVE" if approve else "REJECTED"
    record.reviewed_by_user_id, record.reviewed_at = actor.user_id, datetime.now(timezone.utc)
    requirement = _lock_requirement(session, record.requirement_id)
    if approve and requirement.lifecycle_status not in ENDED:
        requirement.lifecycle_status = RequirementLifecycleStatus.RECONCILED
    record_event(session, actor, "reconciliation.reviewed", "requirement", record.requirement_id,
                 {"reconciliation_id": str(record.id), "version": record.version, "approved": approve, "note": note})
    return {"reconciliation_id": str(record.id), "status": record.status}


def completion_check(session: Session, requirement: Requirement, figures: dict | None = None) -> dict:
    """Whether the order may be closed as COMPLETED, and what stands in the way (P6)."""
    figures = figures or order_figures(session, requirement)[0]
    blockers = []
    if Decimal(figures["buyer_confirmed_kg"]) < requirement.required_quantity_kg:
        blockers.append(f"buyer-confirmed {figures['buyer_confirmed_kg']} kg of {format(requirement.required_quantity_kg.normalize(), 'f')} kg required")
    if figures["unconfirmed_deliveries"]:
        blockers.append(f"{figures['unconfirmed_deliveries']} delivery(ies) without the buyer's confirmation")
    if figures["deliveries_with_discrepancy"]:
        blockers.append(f"{figures['deliveries_with_discrepancy']} delivery(ies) with a reported discrepancy")
    if figures["open_disputes"]:
        blockers.append(f"{figures['open_disputes']} open dispute(s)")
    return {"can_complete": not blockers, "blockers": blockers}


def close_order(session: Session, actor: AuthorizationContext, requirement_id: UUID, *, accept_variance: bool,
                reason: str | None, key: str | None) -> dict:
    """End an order as COMPLETED, or CLOSED_WITH_VARIANCE through an authorized acceptance, and release what remains."""
    from src.backend.app.agents.application.orchestrator import close_tasks_for_order
    from src.backend.app.supply.application.release import release_remaining
    _require(actor, PermissionCode.TRADE_RECONCILE, "closing an order")
    if (done := _replay(session, "requirement.close", key)) is not None:
        return done
    requirement = _lock_requirement(session, requirement_id)
    if requirement.lifecycle_status in ENDED:
        raise TradeError(f"this order has already ended ({requirement.lifecycle_status.value.lower()})")
    effective = effective_reconciliation(session, requirement.id)
    if effective is None:
        raise TradeError("reconcile the order before closing it")
    figures, variances, basis = order_figures(session, requirement)
    if any(effective.figures.get(k) != figures.get(k) for k in MATERIAL_FIGURES + ("open_disputes", "unconfirmed_deliveries")):
        raise TradeError("records changed since the effective reconciliation; reconcile again before closing")
    if figures["open_disputes"]:
        raise TradeError("resolve or withdraw open disputes before closing")
    check = completion_check(session, requirement, figures)
    if check["can_complete"] and not accept_variance:
        outcome = RequirementLifecycleStatus.COMPLETED
    elif accept_variance:
        _require(actor, PermissionCode.TRADE_ACCEPT_VARIANCE, "closing an order with a variance")
        if not (reason and len(reason.strip()) >= 3):
            raise TradeError("accepting a variance needs a documented reason", 422)
        outcome = RequirementLifecycleStatus.CLOSED_WITH_VARIANCE
    else:
        raise TradeError("the order cannot be completed: " + "; ".join(check["blockers"]) + ". Close it with an accepted variance instead")
    organization_id = _organization(session, requirement)
    correlation = uuid4()
    released = ZERO
    for allocation in session.scalars(select(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement.id)
                                      .order_by(SupplyAllocation.id).with_for_update()).all():
        common = {"actor_id": str(actor.user_id), "actor_type": "user", "organization_id": organization_id, "correlation_id": correlation}
        if allocation.status in (AllocationStatus.COMMITTED, AllocationStatus.LOST):
            released += release_remaining(session, allocation, kind="close_out", reason=f"order {outcome.value.lower()}", **common)
        elif allocation.status == AllocationStatus.STANDBY:
            released += release_remaining(session, allocation, kind="standby_unused", reason="order closed; standby not needed", **common)
            allocation.status = AllocationStatus.RELEASED
        elif allocation.status in (AllocationStatus.PROPOSED, AllocationStatus.SOLICITED):
            released += release_remaining(session, allocation, kind="request_withdrawn", reason="order closed", **common)
            allocation.status = AllocationStatus.WITHDRAWN
    close_tasks_for_order(session, requirement.id, f"order {outcome.value.lower()}", str(actor.user_id))
    from src.backend.app.assurance.application.exceptions import resolve_for_ended_order
    resolve_for_ended_order(session, requirement, str(actor.user_id), outcome.value.lower().replace("_", " "))
    requirement.lifecycle_status = outcome
    result = {"requirement_id": str(requirement.id), "outcome": outcome.value, "reconciliation_version": effective.version,
              "figures": figures, "variances": variances, "released_kg": format(released.normalize(), "f"),
              "variance_reason": (reason or "").strip() or None, "unconfirmed_deliveries": basis["unconfirmed_deliveries"]}
    record_event(session, actor, "order.closed", "requirement", requirement.id, result, idempotency_key=key, correlation_id=correlation)
    return _remember(session, "requirement.close", key, result)
