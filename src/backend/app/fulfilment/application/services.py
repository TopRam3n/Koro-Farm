from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage
from src.backend.app.domain.common import Grade
from src.backend.app.fulfilment.domain.models import FulfilmentNode, InspectionStatus, ReceivedSublot
from src.backend.app.supply.domain.models import ProductionLot
from src.backend.app.demand.domain.models import Requirement, RequirementLifecycleStatus
from src.backend.app.supply.domain.planning_models import AllocationStatus, ConsentStatus, SupplyAllocation
from src.backend.app.assurance.application.recovery import record_quality_shortfall


def _event(session: Session, name: str, allocation: SupplyAllocation, payload: dict) -> None:
    event = DomainEvent(event_type=name, aggregate_type="requirement", aggregate_id=allocation.requirement_id,
        correlation_id=uuid4(), actor_type="operator", payload=payload, occurred_at=datetime.now(timezone.utc))
    session.add(event); session.flush(); session.add(OutboxMessage(event_id=event.id, topic=name, payload=payload))


def receive(session: Session, allocation_id: UUID, node_id: UUID, quantity: Decimal, received_at: datetime, evidence: str | None, key: str) -> dict:
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "sublot.receive", CommandDeduplication.idempotency_key == key))
    if existing: return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update())
        existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "sublot.receive", CommandDeduplication.idempotency_key == key))
        if existing: return existing.result
        if allocation is None: raise ValueError("allocation not found")
        # R1 WP4 (M1): produce is received only against an active supplier commitment of a live order.
        if allocation.status != AllocationStatus.COMMITTED or allocation.consent_status != ConsentStatus.RECORDED:
            raise ValueError(f"produce can be received only against an accepted commitment (this allocation is {allocation.status.value.lower()})")
        requirement = session.scalar(select(Requirement).where(Requirement.id == allocation.requirement_id).with_for_update())
        if requirement.lifecycle_status in (RequirementLifecycleStatus.CANCELLED, RequirementLifecycleStatus.COMPLETED,
                                            RequirementLifecycleStatus.CLOSED_WITH_VARIANCE, RequirementLifecycleStatus.CLOSED):
            raise ValueError("this order has ended; nothing more can be received against it")
        # Serialize with capacity reports on the same lot, which read the delivered quantity under this lock.
        session.scalar(select(ProductionLot).where(ProductionLot.id == allocation.production_lot_id).with_for_update())
        node = session.get(FulfilmentNode, node_id)
        if node is None: raise ValueError("fulfilment node not found")
        if not node.active: raise ValueError("this fulfilment site is deactivated")
        if quantity <= 0: raise ValueError("received quantity must be positive")
        received = session.scalar(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0)).where(ReceivedSublot.allocation_id == allocation_id)) or Decimal("0")
        if received + quantity > allocation.obligation_kg: raise ValueError("received quantity exceeds what the supplier committed")
        if requirement.lifecycle_status in (RequirementLifecycleStatus.PLANNING, RequirementLifecycleStatus.ACTIVE):
            requirement.lifecycle_status = RequirementLifecycleStatus.IN_FULFILMENT
        sublot = ReceivedSublot(allocation_id=allocation_id, fulfilment_node_id=node_id, received_quantity_kg=quantity,
            accepted_quantity_kg=Decimal("0"), rejected_quantity_kg=Decimal("0"), inspection_status=InspectionStatus.PENDING_INSPECTION,
            received_at=received_at, receipt_evidence_reference=evidence)
        session.add(sublot); session.flush()
        _event(session, "sublot.received", allocation, {"received_sublot_id": str(sublot.id), "allocation_id": str(allocation_id), "received_quantity_kg": str(quantity), "evidence_reference": evidence, "evidence_verified": False})
        result = {"received_sublot_id": str(sublot.id), "inspection_status": sublot.inspection_status.value, "received_quantity_kg": str(quantity)}
        session.add(CommandDeduplication(command_type="sublot.receive", idempotency_key=key, result=result))
        return result


def grade(session: Session, sublot_id: UUID, accepted: Decimal, rejected: Decimal, assigned_grade: Grade | None, rejection_reason: str | None, evidence: str | None, key: str) -> dict:
    if isinstance(sublot_id, str):
        sublot_id = UUID(sublot_id)
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "sublot.grade", CommandDeduplication.idempotency_key == key))
    if existing: return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        sublot = session.scalar(select(ReceivedSublot).where(ReceivedSublot.id == sublot_id).with_for_update())
        existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "sublot.grade", CommandDeduplication.idempotency_key == key))
        if existing: return existing.result
        if sublot is None: raise ValueError("received sublot not found")
        if sublot.entry_type != "RECEIPT": raise ValueError("a correction record cannot be graded")
        if sublot.graded_at is not None: raise ValueError("received sublot has already been graded; record a correction instead")
        if accepted < 0 or rejected < 0 or accepted + rejected != sublot.received_quantity_kg: raise ValueError("grading must account for exactly the received quantity")
        allocation = session.get(SupplyAllocation, sublot.allocation_id)
        sublot.accepted_quantity_kg = accepted; sublot.rejected_quantity_kg = rejected; sublot.assigned_grade = assigned_grade
        sublot.rejection_reason = rejection_reason; sublot.inspection_evidence_reference = evidence; sublot.graded_at = datetime.now(timezone.utc)
        sublot.inspection_status = InspectionStatus.ACCEPTED if rejected == 0 else InspectionStatus.REJECTED if accepted == 0 else InspectionStatus.PARTIALLY_ACCEPTED
        session.flush()
        event_name = "sublot.rejected" if accepted == 0 else "sublot.partially_accepted" if rejected else "sublot.graded"
        _event(session, event_name, allocation, {"received_sublot_id": str(sublot.id), "previous_status": InspectionStatus.PENDING_INSPECTION.value, "new_status": sublot.inspection_status.value, "accepted_quantity_kg": str(accepted), "rejected_quantity_kg": str(rejected), "evidence_reference": evidence, "evidence_verified": False})
        recovery = None
        if rejected:
            recovery = record_quality_shortfall(session, allocation.requirement_id, sublot.id, rejected, "quality_rejection")
        result = {"received_sublot_id": str(sublot.id), "inspection_status": sublot.inspection_status.value, "accepted_quantity_kg": str(accepted), "rejected_quantity_kg": str(rejected), "recovery": recovery}
        session.add(CommandDeduplication(command_type="sublot.grade", idempotency_key=key, result=result))
        return result


def adjust_receipt(session: Session, actor, sublot_id: UUID, *, received_delta: Decimal, accepted_delta: Decimal,
                   rejected_delta: Decimal, reason: str, evidence: str | None) -> dict:
    """Correct a receipt or its grading without editing it: an ADJUSTMENT row holds the signed differences, so every
    total includes it. Refused once the produce is in a dispatched shipment (correct the delivery instead)."""
    from src.backend.app.reconciliation.domain.models import Shipment, ShipmentStatus, ShipmentSublot
    if not reason or len(reason.strip()) < 3:
        raise ValueError("a correction needs a reason")
    with session.begin_nested() if session.in_transaction() else session.begin():
        sublot = session.scalar(select(ReceivedSublot).where(ReceivedSublot.id == sublot_id).with_for_update())
        if sublot is None or sublot.entry_type != "RECEIPT":
            raise ValueError("received sublot not found")
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == sublot.allocation_id).with_for_update())
        session.scalar(select(ProductionLot).where(ProductionLot.id == allocation.production_lot_id).with_for_update())
        shipped = session.scalar(select(Shipment.status).join(ShipmentSublot, ShipmentSublot.shipment_id == Shipment.id)
                                 .where(ShipmentSublot.received_sublot_id == sublot.id))
        if shipped in (ShipmentStatus.DISPATCHED, ShipmentStatus.DELIVERED):
            raise ValueError("this produce has been dispatched; correct the delivery record instead")
        if shipped == ShipmentStatus.OPEN:
            raise ValueError("remove this produce from its open shipment before correcting it")
        rows = session.execute(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0),
                                      func.coalesce(func.sum(ReceivedSublot.accepted_quantity_kg), 0),
                                      func.coalesce(func.sum(ReceivedSublot.rejected_quantity_kg), 0))
                               .where((ReceivedSublot.id == sublot.id) | (ReceivedSublot.adjusts_sublot_id == sublot.id))).one()
        received, accepted, rejected = (Decimal(v or 0) + d for v, d in zip(rows, (received_delta, accepted_delta, rejected_delta)))
        if min(received, accepted, rejected) < 0:
            raise ValueError("a correction cannot make any quantity negative")
        if sublot.graded_at is not None and accepted + rejected != received:
            raise ValueError("after the correction, accepted plus rejected must equal received")
        if sublot.graded_at is None and (accepted_delta or rejected_delta):
            raise ValueError("grade the receipt first; corrections to grading apply to graded receipts")
        total = session.scalar(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0))
                               .where(ReceivedSublot.allocation_id == allocation.id)) or Decimal("0")
        if total + received_delta > allocation.obligation_kg:
            raise ValueError("the corrected receipts would exceed what the supplier committed")
        if not (received_delta or accepted_delta or rejected_delta):
            raise ValueError("a correction must change at least one quantity")
        row = ReceivedSublot(allocation_id=allocation.id, fulfilment_node_id=sublot.fulfilment_node_id, entry_type="ADJUSTMENT",
                             adjusts_sublot_id=sublot.id, received_quantity_kg=received_delta, accepted_quantity_kg=accepted_delta,
                             rejected_quantity_kg=rejected_delta, inspection_status=sublot.inspection_status,
                             received_at=datetime.now(timezone.utc), adjustment_reason=reason.strip(),
                             receipt_evidence_reference=evidence, recorded_by_user_id=getattr(actor, "user_id", None),
                             graded_at=sublot.graded_at)
        session.add(row)
        session.flush()
        _event(session, "receipt.corrected", allocation, {
            "received_sublot_id": str(sublot.id), "adjustment_id": str(row.id), "received_delta_kg": str(received_delta),
            "accepted_delta_kg": str(accepted_delta), "rejected_delta_kg": str(rejected_delta), "reason": reason.strip(),
            "received_kg": str(received), "accepted_kg": str(accepted), "rejected_kg": str(rejected)})
        if rejected_delta > 0:
            record_quality_shortfall(session, allocation.requirement_id, sublot.id, rejected_delta, "quality_rejection_correction")
        return {"adjustment_id": str(row.id), "received_kg": str(received), "accepted_kg": str(accepted), "rejected_kg": str(rejected)}
