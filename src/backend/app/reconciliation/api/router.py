from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.recovery import _coverage
from src.backend.app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage
from src.backend.app.demand.domain.models import Requirement, RequirementLifecycleStatus
from src.backend.app.fulfilment.domain.models import FulfilmentNode, ReceivedSublot
from src.backend.app.main_dependencies import get_session
from src.backend.app.reconciliation.domain.models import Delivery, RequirementReconciliation, Shipment, ShipmentStatus, ShipmentSublot
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import SupplyAllocation

router = APIRouter(tags=["shipments", "reconciliation", "trade-evidence"])

class ShipmentCreate(BaseModel):
    fulfilment_node_id: UUID
    reference: str = Field(min_length=3, max_length=80)

class AddSublot(BaseModel):
    received_sublot_id: UUID

class DispatchCommand(BaseModel):
    evidence_reference: str | None = Field(default=None, max_length=500)

class DeliveryCommand(BaseModel):
    delivered_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    delivered_at: datetime
    delivery_evidence_reference: str | None = Field(default=None, max_length=500)
    buyer_confirmed: bool = False
    buyer_confirmation_evidence: str | None = Field(default=None, max_length=500)

class ReconcileCommand(BaseModel):
    verification_evidence_reference: str = Field(min_length=3, max_length=500)
    dispute_status: str | None = Field(default=None, max_length=80)

def _event(session: Session, event_type: str, requirement_id: UUID, payload: dict) -> None:
    from uuid import uuid4
    event = DomainEvent(event_type=event_type, aggregate_type="requirement", aggregate_id=requirement_id,
        correlation_id=uuid4(), actor_type="operator", payload=payload, occurred_at=datetime.now(timezone.utc))
    session.add(event); session.flush(); session.add(OutboxMessage(event_id=event.id, topic=event_type, payload=payload))

@router.post("/requirements/{requirement_id}/shipments")
def create_shipment(requirement_id: UUID, payload: ShipmentCreate,
                    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                    session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "shipment.create", CommandDeduplication.idempotency_key == idempotency_key))
    if existing: return existing.result
    if session.get(Requirement, requirement_id) is None: raise HTTPException(404, "requirement not found")
    if session.get(FulfilmentNode, payload.fulfilment_node_id) is None: raise HTTPException(404, "fulfilment node not found")
    shipment = Shipment(requirement_id=requirement_id, fulfilment_node_id=payload.fulfilment_node_id, reference=payload.reference)
    session.add(shipment); session.flush(); result = {"shipment_id": str(shipment.id), "status": shipment.status.value, "reference": shipment.reference}
    _event(session, "shipment.created", requirement_id, result); session.add(CommandDeduplication(command_type="shipment.create", idempotency_key=idempotency_key, result=result)); session.commit()
    return result

@router.post("/shipments/{shipment_id}/sublots")
def add_sublot(shipment_id: UUID, payload: AddSublot,
               idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
               session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "shipment.add_sublot", CommandDeduplication.idempotency_key == idempotency_key))
    if existing: return existing.result
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    sublot = session.scalar(select(ReceivedSublot).where(ReceivedSublot.id == payload.received_sublot_id).with_for_update())
    if shipment is None or sublot is None: raise HTTPException(404, "shipment or received sublot not found")
    allocation = session.get(SupplyAllocation, sublot.allocation_id)
    if shipment.status != ShipmentStatus.OPEN or allocation.requirement_id != shipment.requirement_id: raise HTTPException(409, "sublot cannot be added to this shipment")
    if sublot.accepted_quantity_kg <= 0: raise HTTPException(409, "only graded, accepted quantity may be shipped")
    if session.scalar(select(ShipmentSublot).where(ShipmentSublot.received_sublot_id == sublot.id)): raise HTTPException(409, "sublot is already assigned to a shipment")
    result = {"shipment_id": str(shipment.id), "accepted_quantity_kg": str(sublot.accepted_quantity_kg)}
    session.add(ShipmentSublot(shipment_id=shipment.id, received_sublot_id=sublot.id, accepted_quantity_kg=sublot.accepted_quantity_kg)); _event(session, "shipment.sublot_added", shipment.requirement_id, {**result, "received_sublot_id": str(sublot.id)}); session.add(CommandDeduplication(command_type="shipment.add_sublot", idempotency_key=idempotency_key, result=result)); session.commit()
    return result

@router.post("/shipments/{shipment_id}/dispatch")
def dispatch(shipment_id: UUID, payload: DispatchCommand,
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
             session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "shipment.dispatch", CommandDeduplication.idempotency_key == idempotency_key))
    if existing: return existing.result
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    if shipment is None: raise HTTPException(404, "shipment not found")
    if shipment.status != ShipmentStatus.OPEN: raise HTTPException(409, "shipment is not open")
    quantity = session.scalar(select(func.coalesce(func.sum(ShipmentSublot.accepted_quantity_kg), 0)).where(ShipmentSublot.shipment_id == shipment.id)) or Decimal("0")
    if quantity <= 0: raise HTTPException(409, "shipment contains no accepted sublots")
    shipment.status = ShipmentStatus.DISPATCHED; shipment.dispatched_at = datetime.now(timezone.utc); shipment.dispatch_evidence_reference = payload.evidence_reference
    result = {"shipment_id": str(shipment.id), "status": shipment.status.value, "dispatched_quantity_kg": str(quantity)}
    _event(session, "shipment.dispatched", shipment.requirement_id, {**result, "evidence_reference": payload.evidence_reference, "evidence_verified": False}); session.add(CommandDeduplication(command_type="shipment.dispatch", idempotency_key=idempotency_key, result=result)); session.commit()
    return result

@router.post("/shipments/{shipment_id}/delivery")
def deliver(shipment_id: UUID, payload: DeliveryCommand, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "shipment.delivery", CommandDeduplication.idempotency_key == idempotency_key))
    if existing: return existing.result
    shipment = session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "shipment.delivery", CommandDeduplication.idempotency_key == idempotency_key))
    if existing: return existing.result
    if shipment is None or shipment.status != ShipmentStatus.DISPATCHED: raise HTTPException(409, "shipment is not dispatched")
    dispatched = session.scalar(select(func.coalesce(func.sum(ShipmentSublot.accepted_quantity_kg), 0)).where(ShipmentSublot.shipment_id == shipment.id)) or Decimal("0")
    if payload.delivered_quantity_kg > dispatched: raise HTTPException(409, "delivered quantity exceeds dispatched quantity")
    if payload.buyer_confirmed and not payload.buyer_confirmation_evidence: raise HTTPException(422, "buyer confirmation evidence is required")
    delivery = Delivery(shipment_id=shipment.id, **payload.model_dump()); session.add(delivery); session.flush(); shipment.status = ShipmentStatus.DELIVERED
    result = {"delivery_id": str(delivery.id), "shipment_id": str(shipment.id), "buyer_confirmed": delivery.buyer_confirmed, "delivery_verification": "unverified" if not payload.delivery_evidence_reference else "evidence_recorded"}
    _event(session, "delivery.confirmed", shipment.requirement_id, result); session.add(CommandDeduplication(command_type="shipment.delivery", idempotency_key=idempotency_key, result=result)); session.commit(); return result

@router.post("/requirements/{requirement_id}/reconcile")
def reconcile(requirement_id: UUID, payload: ReconcileCommand,
              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
              session: Session = Depends(get_session)) -> dict:
    if not idempotency_key: raise HTTPException(400, "Idempotency-Key header is required")
    existing = session.scalar(select(CommandDeduplication).where(CommandDeduplication.command_type == "requirement.reconcile", CommandDeduplication.idempotency_key == idempotency_key))
    if existing: return existing.result
    requirement = session.scalar(select(Requirement).where(Requirement.id == requirement_id).with_for_update())
    if requirement is None: raise HTTPException(404, "requirement not found")
    committed = _coverage(session, requirement_id)
    accepted = session.scalar(select(func.coalesce(func.sum(ReceivedSublot.accepted_quantity_kg), 0)).join(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement_id)) or Decimal("0")
    deliveries = session.execute(select(Delivery, Shipment).join(Shipment).where(Shipment.requirement_id == requirement_id)).all()
    delivered = sum((delivery.delivered_quantity_kg for delivery, _ in deliveries), Decimal("0"))
    buyer_confirmed = bool(deliveries) and all(delivery.buyer_confirmed for delivery, _ in deliveries)
    evidence_complete = bool(deliveries) and all(delivery.delivery_evidence_reference and delivery.buyer_confirmation_evidence for delivery, _ in deliveries)
    if not buyer_confirmed or not evidence_complete:
        raise HTTPException(409, "verified buyer-confirmed delivery evidence is required before reconciliation")
    on_time = all(delivery.delivered_at.date() <= requirement.delivery_window_end for delivery, _ in deliveries) if deliveries else None
    recon = session.get(RequirementReconciliation, requirement_id) or RequirementReconciliation(requirement_id=requirement_id, committed_quantity_kg=0, delivered_quantity_kg=0, accepted_quantity_kg=0, quantity_variance_kg=0, accepted_fulfilment_rate_pct=0)
    recon.committed_quantity_kg=committed; recon.delivered_quantity_kg=delivered; recon.accepted_quantity_kg=accepted; recon.quantity_variance_kg=accepted-requirement.required_quantity_kg; recon.accepted_fulfilment_rate_pct=(accepted * Decimal("100") / requirement.required_quantity_kg); recon.on_time=on_time; recon.buyer_confirmed=buyer_confirmed; recon.dispute_status=payload.dispute_status; recon.verification_evidence_reference=payload.verification_evidence_reference
    result = {"committed_quantity_kg": str(committed), "delivered_quantity_kg": str(delivered), "accepted_quantity_kg": str(accepted), "quantity_variance_kg": str(recon.quantity_variance_kg), "accepted_fulfilment_rate_pct": str(recon.accepted_fulfilment_rate_pct), "on_time": on_time, "buyer_confirmed": buyer_confirmed, "dispute_status": payload.dispute_status, "verification_status": "verified"}
    session.add(recon); requirement.lifecycle_status=RequirementLifecycleStatus.RECONCILED; _event(session, "trade.reconciled", requirement_id, result); session.add(CommandDeduplication(command_type="requirement.reconcile", idempotency_key=idempotency_key, result=result)); session.commit()
    return result

@router.get("/farmers/{farmer_id}/trade-performance-passport")
def passport(farmer_id: UUID, session: Session = Depends(get_session)) -> dict:
    if session.get(Farmer, farmer_id) is None: raise HTTPException(404, "farmer not found")
    rows = session.execute(select(ReceivedSublot, SupplyAllocation).join(SupplyAllocation).join(ProductionLot)
        .join(ShipmentSublot, ShipmentSublot.received_sublot_id == ReceivedSublot.id)
        .join(Shipment, Shipment.id == ShipmentSublot.shipment_id)
        .join(Delivery, Delivery.shipment_id == Shipment.id)
        .join(RequirementReconciliation, RequirementReconciliation.requirement_id == SupplyAllocation.requirement_id)
        .where(ProductionLot.farmer_id == farmer_id, RequirementReconciliation.buyer_confirmed.is_(True),
               RequirementReconciliation.verification_evidence_reference.is_not(None),
               or_(RequirementReconciliation.dispute_status.is_(None), RequirementReconciliation.dispute_status == "RESOLVED"))).all()
    received=sum((s.received_quantity_kg for s, _ in rows), Decimal("0")); accepted=sum((s.accepted_quantity_kg for s, _ in rows), Decimal("0")); trades=len({a.requirement_id for _, a in rows if a.requirement_id})
    quality_rate=(accepted * Decimal("100") / received) if received else None
    return {"farmer_id": str(farmer_id), "completed_institutional_trades": trades, "quantity_fulfilment_rate_pct": str(quality_rate) if quality_rate is not None else None, "quality_acceptance_rate_pct": str(quality_rate) if quality_rate is not None else None, "on_time_delivery_rate_pct": None, "fulfilment_reliability_index": None if trades < 3 else str(quality_rate), "history_maturity": "BUILDING_HISTORY" if trades < 3 else "ESTABLISHED_HISTORY", "financing_eligibility": "NOT_ASSESSED"}


@router.get("/shipments/{shipment_id}/traceability")
def shipment_traceability(shipment_id: UUID, session: Session = Depends(get_session)) -> dict:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None: raise HTTPException(404, "shipment not found")
    rows = session.execute(select(ShipmentSublot, ReceivedSublot, SupplyAllocation, ProductionLot, Farmer)
        .join(ReceivedSublot, ReceivedSublot.id == ShipmentSublot.received_sublot_id)
        .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
        .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .where(ShipmentSublot.shipment_id == shipment_id)).all()
    return {"shipment_id": str(shipment_id), "status": shipment.status.value, "sources": [{
        "shipment_sublot_id": str(link.id), "received_sublot_id": str(sublot.id),
        "allocation_id": str(allocation.id), "production_lot_id": str(lot.id),
        "farmer_id": str(farmer.id), "farmer_name": farmer.name,
        "accepted_quantity_kg": str(link.accepted_quantity_kg),
    } for link, sublot, allocation, lot, farmer in rows]}


@router.get("/production-lots/{lot_id}/shipments")
def lot_shipments(lot_id: UUID, session: Session = Depends(get_session)) -> dict:
    if session.get(ProductionLot, lot_id) is None: raise HTTPException(404, "production lot not found")
    rows = session.execute(select(Shipment, ShipmentSublot, ReceivedSublot)
        .join(ShipmentSublot, ShipmentSublot.shipment_id == Shipment.id)
        .join(ReceivedSublot, ReceivedSublot.id == ShipmentSublot.received_sublot_id)
        .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
        .where(SupplyAllocation.production_lot_id == lot_id)).all()
    return {"production_lot_id": str(lot_id), "shipments": [{
        "shipment_id": str(shipment.id), "reference": shipment.reference,
        "status": shipment.status.value, "received_sublot_id": str(sublot.id),
        "accepted_quantity_kg": str(link.accepted_quantity_kg),
    } for shipment, link, sublot in rows]}
