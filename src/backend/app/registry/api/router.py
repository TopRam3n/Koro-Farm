from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import DomainEvent, RecoveryRun
from src.backend.app.compliance.domain.models import ComplianceRule
from src.backend.app.demand.domain.models import Requirement, SupplyHealth
from src.backend.app.economics.domain.models import CostSnapshot
from src.backend.app.fulfilment.domain.models import FulfilmentNode, InspectionStatus, ReceivedSublot
from src.backend.app.main_dependencies import get_session
from src.backend.app.reconciliation.domain.models import Shipment
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import (
    AllocationRole,
    AllocationStatus,
    SupplyAllocation,
    SupplyPlan,
)

router = APIRouter(tags=["operational registries"])


def _money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


@router.get("/farmers")
def list_farmers(
    parish: str | None = None,
    active: bool | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    statement = select(Farmer).order_by(Farmer.name, Farmer.id)
    if parish:
        statement = statement.where(Farmer.parish == parish)
    if active is not None:
        statement = statement.where(Farmer.active == active)
    farmers = session.scalars(statement.offset(offset).limit(limit)).all()
    items = []
    for farmer in farmers:
        lot_count, available_kg = session.execute(
            select(func.count(ProductionLot.id), func.coalesce(func.sum(ProductionLot.available_quantity_kg), 0)).where(
                ProductionLot.farmer_id == farmer.id
            )
        ).one()
        committed_kg = session.scalar(
            select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0))
            .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
            .where(
                ProductionLot.farmer_id == farmer.id,
                SupplyAllocation.role == AllocationRole.COMMITTED,
                SupplyAllocation.status.in_([AllocationStatus.COMMITTED, AllocationStatus.ACTIVATED]),
            )
        ) or Decimal("0")
        items.append(
            {
                "id": str(farmer.id),
                "name": farmer.name,
                "parish": farmer.parish,
                "active": farmer.active,
                "production_lot_count": lot_count,
                "available_quantity_kg": str(available_kg),
                "committed_quantity_kg": str(committed_kg),
            }
        )
    return {"items": items, "offset": offset, "limit": limit}


@router.get("/allocations")
def list_allocations(
    requirement_id: UUID | None = None,
    role: AllocationRole | None = None,
    status: AllocationStatus | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    statement = (
        select(SupplyAllocation, ProductionLot, Farmer)
        .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .order_by(SupplyAllocation.created_at.desc(), SupplyAllocation.id)
    )
    if requirement_id:
        statement = statement.where(SupplyAllocation.requirement_id == requirement_id)
    if role:
        statement = statement.where(SupplyAllocation.role == role)
    if status:
        statement = statement.where(SupplyAllocation.status == status)
    rows = session.execute(statement.offset(offset).limit(limit)).all()
    return {
        "items": [
            {
                "id": str(allocation.id),
                "requirement_id": str(allocation.requirement_id),
                "supply_plan_id": str(allocation.supply_plan_id),
                "production_lot_id": str(lot.id),
                "farmer_id": str(farmer.id),
                "farmer_name": farmer.name,
                "parish": lot.parish,
                "role": allocation.role.value,
                "status": allocation.status.value,
                "quantity_kg": str(allocation.quantity_kg),
                "plan_version": allocation.plan_version,
            }
            for allocation, lot, farmer in rows
        ],
        "offset": offset,
        "limit": limit,
    }


def _recovery_case(run: RecoveryRun, session: Session) -> dict:
    plans = session.scalars(
        select(SupplyPlan).where(SupplyPlan.requirement_id == run.requirement_id).order_by(SupplyPlan.plan_version)
    ).all()
    costs = []
    for plan in plans:
        snapshot = session.scalar(select(CostSnapshot).where(CostSnapshot.supply_plan_id == plan.id))
        if snapshot:
            costs.append(snapshot.total_landed_cost_jmd)
    cost_delta = costs[-1] - costs[0] if len(costs) > 1 else None
    return {
        "id": str(run.id),
        "requirement_id": str(run.requirement_id),
        "status": run.status.value,
        "cause": run.cause,
        "lost_quantity_kg": str(run.lost_quantity_kg),
        "standby_activated_kg": str(run.standby_activated_kg),
        "new_supply_accepted_kg": str(run.new_supply_accepted_kg),
        "remaining_shortfall_kg": str(run.remaining_shortfall_kg),
        "landed_cost_delta_jmd": _money(cost_delta),
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


@router.get("/recovery-cases")
def list_recovery_cases(
    requirement_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    statement = select(RecoveryRun).order_by(RecoveryRun.created_at.desc(), RecoveryRun.id)
    if requirement_id:
        statement = statement.where(RecoveryRun.requirement_id == requirement_id)
    rows = session.scalars(statement.offset(offset).limit(limit)).all()
    return {"items": [_recovery_case(row, session) for row in rows], "offset": offset, "limit": limit}


@router.get("/recovery-cases/{recovery_id}")
def get_recovery_case(recovery_id: UUID, session: Session = Depends(get_session)) -> dict:
    run = session.get(RecoveryRun, recovery_id)
    if run is None:
        raise HTTPException(404, "recovery case not found")
    result = _recovery_case(run, session)
    result["events"] = [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "actor_type": event.actor_type,
            "payload": event.payload,
            "occurred_at": event.occurred_at,
        }
        for event in session.scalars(
            select(DomainEvent)
            .where(DomainEvent.aggregate_id == run.requirement_id)
            .order_by(DomainEvent.occurred_at, DomainEvent.id)
        ).all()
    ]
    return result


@router.get("/received-sublots")
def list_received_sublots(
    inspection_status: InspectionStatus | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    statement = (
        select(ReceivedSublot, SupplyAllocation, FulfilmentNode)
        .join(SupplyAllocation, SupplyAllocation.id == ReceivedSublot.allocation_id)
        .join(FulfilmentNode, FulfilmentNode.id == ReceivedSublot.fulfilment_node_id)
        .order_by(ReceivedSublot.received_at.desc(), ReceivedSublot.id)
    )
    if inspection_status:
        statement = statement.where(ReceivedSublot.inspection_status == inspection_status)
    rows = session.execute(statement.offset(offset).limit(limit)).all()
    return {
        "items": [
            {
                "id": str(sublot.id),
                "allocation_id": str(sublot.allocation_id),
                "requirement_id": str(allocation.requirement_id),
                "fulfilment_node": node.name,
                "received_quantity_kg": str(sublot.received_quantity_kg),
                "accepted_quantity_kg": str(sublot.accepted_quantity_kg),
                "rejected_quantity_kg": str(sublot.rejected_quantity_kg),
                "inspection_status": sublot.inspection_status.value,
                "assigned_grade": sublot.assigned_grade.value if sublot.assigned_grade else None,
                "received_at": sublot.received_at,
            }
            for sublot, allocation, node in rows
        ],
        "offset": offset,
        "limit": limit,
    }


@router.get("/shipments")
def list_shipments(
    requirement_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    statement = select(Shipment).order_by(Shipment.created_at.desc(), Shipment.id)
    if requirement_id:
        statement = statement.where(Shipment.requirement_id == requirement_id)
    rows = session.scalars(statement.offset(offset).limit(limit)).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "requirement_id": str(row.requirement_id),
                "reference": row.reference,
                "status": row.status.value,
                "dispatched_at": row.dispatched_at,
                "dispatch_evidence_reference": row.dispatch_evidence_reference,
            }
            for row in rows
        ],
        "offset": offset,
        "limit": limit,
    }


@router.get("/activity")
def list_activity(
    event_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    statement = select(DomainEvent).order_by(DomainEvent.occurred_at.desc(), DomainEvent.id)
    if event_type:
        statement = statement.where(DomainEvent.event_type == event_type)
    rows = session.scalars(statement.offset(offset).limit(limit)).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "aggregate_type": row.aggregate_type,
                "aggregate_id": str(row.aggregate_id),
                "correlation_id": str(row.correlation_id),
                "actor_type": row.actor_type,
                "payload": row.payload,
                "occurred_at": row.occurred_at,
            }
            for row in rows
        ],
        "offset": offset,
        "limit": limit,
    }


@router.get("/compliance-rules")
def list_compliance_rules(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(
        select(ComplianceRule).order_by(ComplianceRule.destination, ComplianceRule.crop, ComplianceRule.rule_name)
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "origin": row.origin,
                "destination": row.destination,
                "crop": row.crop.value,
                "product_form": row.product_form,
                "rule_name": row.rule_name,
                "issuing_body": row.issuing_body,
                "description": row.description,
                "required_before": row.required_before,
                "lead_time": row.lead_time,
                "effective_from": row.effective_from,
                "effective_until": row.effective_until,
                "source_citation": row.source_citation,
                "source_version": row.source_version,
                "last_verified_at": row.last_verified_at,
                "verified_by": row.verified_by,
            }
            for row in rows
        ]
    }


@router.get("/command-center/summary")
def command_center_summary(session: Session = Depends(get_session)) -> dict:
    health_counts = {health.value: 0 for health in SupplyHealth}
    for health, count in session.execute(select(Requirement.supply_health, func.count()).group_by(Requirement.supply_health)):
        health_counts[health.value] = count

    committed_kg = session.scalar(
        select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).where(
            SupplyAllocation.role == AllocationRole.COMMITTED,
            SupplyAllocation.status.in_([AllocationStatus.COMMITTED, AllocationStatus.ACTIVATED]),
        )
    ) or Decimal("0")
    received_kg, accepted_kg, rejected_kg = session.execute(
        select(
            func.coalesce(func.sum(ReceivedSublot.received_quantity_kg), 0),
            func.coalesce(func.sum(ReceivedSublot.accepted_quantity_kg), 0),
            func.coalesce(func.sum(ReceivedSublot.rejected_quantity_kg), 0),
        )
    ).one()
    concentration = session.execute(
        select(ProductionLot.parish, func.sum(SupplyAllocation.quantity_kg).label("quantity"))
        .join(ProductionLot, ProductionLot.id == SupplyAllocation.production_lot_id)
        .where(
            SupplyAllocation.role == AllocationRole.COMMITTED,
            SupplyAllocation.status.in_([AllocationStatus.COMMITTED, AllocationStatus.ACTIVATED]),
        )
        .group_by(ProductionLot.parish)
        .order_by(func.sum(SupplyAllocation.quantity_kg).desc())
    ).all()
    recent_events = session.scalars(select(DomainEvent).order_by(DomainEvent.occurred_at.desc()).limit(10)).all()
    return {
        "requirements": {
            "total": sum(health_counts.values()),
            "by_supply_health": health_counts,
            "needs_attention": health_counts[SupplyHealth.AT_RISK.value]
            + health_counts[SupplyHealth.RECOVERING.value]
            + health_counts[SupplyHealth.ESCALATION_REQUIRED.value],
        },
        "physical_flow_kg": {
            "committed": str(committed_kg),
            "received": str(received_kg),
            "accepted": str(accepted_kg),
            "rejected": str(rejected_kg),
        },
        "committed_concentration_by_parish": [
            {"parish": parish, "quantity_kg": str(quantity)} for parish, quantity in concentration
        ],
        "recent_activity": [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "aggregate_id": str(event.aggregate_id),
                "actor_type": event.actor_type,
                "occurred_at": event.occurred_at,
            }
            for event in recent_events
        ],
    }
