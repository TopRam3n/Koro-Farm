from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage
from src.backend.app.domain.common import Grade
from src.backend.app.fulfilment.domain.models import FulfilmentNode, InspectionStatus, ReceivedSublot
from src.backend.app.supply.domain.planning_models import SupplyAllocation


def _event(session: Session, name: str, allocation: SupplyAllocation, payload: dict) -> None:
    event = DomainEvent(event_type=name, aggregate_type="requirement", aggregate_id=allocation.requirement_id,
        correlation_id=uuid4(), actor_type="operator", payload=payload, occurred_at=datetime.now(timezone.utc))
    session.add(event); session.flush(); session.add(OutboxMessage(event_id=event.id, topic=name, payload=payload))


def receive(session: Session, allocation_id: UUID, node_id: UUID, quantity: Decimal, received_at: datetime, evidence: str | None, key: str) -> dict:
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "sublot.receive", CommandDeduplication.idempotency_key == key))
    if existing: return existing.result
    with session.begin_nested() if session.in_transaction() else session.begin():
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.id == allocation_id).with_for_update())
        if allocation is None: raise ValueError("allocation not found")
        if session.get(FulfilmentNode, node_id) is None: raise ValueError("fulfilment node not found")
        if quantity < 0: raise ValueError("received quantity cannot be negative")
        received = session.scalar(select(func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0)).where(ReceivedSublot.allocation_id == allocation_id)) or Decimal("0")
        if received + quantity > allocation.quantity_kg: raise ValueError("received quantity exceeds allocation quantity")
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
        if sublot is None: raise ValueError("received sublot not found")
        if sublot.graded_at is not None: raise ValueError("received sublot has already been graded")
        if accepted < 0 or rejected < 0 or accepted + rejected != sublot.received_quantity_kg: raise ValueError("grading must account for exactly the received quantity")
        allocation = session.get(SupplyAllocation, sublot.allocation_id)
        sublot.accepted_quantity_kg = accepted; sublot.rejected_quantity_kg = rejected; sublot.assigned_grade = assigned_grade
        sublot.rejection_reason = rejection_reason; sublot.inspection_evidence_reference = evidence; sublot.graded_at = datetime.now(timezone.utc)
        sublot.inspection_status = InspectionStatus.ACCEPTED if rejected == 0 else InspectionStatus.REJECTED if accepted == 0 else InspectionStatus.PARTIALLY_ACCEPTED
        session.flush()
        event_name = "sublot.rejected" if accepted == 0 else "sublot.partially_accepted" if rejected else "sublot.graded"
        _event(session, event_name, allocation, {"received_sublot_id": str(sublot.id), "previous_status": InspectionStatus.PENDING_INSPECTION.value, "new_status": sublot.inspection_status.value, "accepted_quantity_kg": str(accepted), "rejected_quantity_kg": str(rejected), "evidence_reference": evidence, "evidence_verified": False})
        result = {"received_sublot_id": str(sublot.id), "inspection_status": sublot.inspection_status.value, "accepted_quantity_kg": str(accepted), "rejected_quantity_kg": str(rejected)}
        session.add(CommandDeduplication(command_type="sublot.grade", idempotency_key=key, result=result))
        return result
