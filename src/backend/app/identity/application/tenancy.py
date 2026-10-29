"""Central, fail-closed organization scoping.

Every tenant-owned record resolves to exactly one organization through its ownership chain:

    buyer.organization_id
    requirement -> buyer
    supply_allocation -> requirement
    received_sublot -> allocation
    shipment -> requirement
    recovery_run -> requirement
    programme -> buyer
    farmer.organization_id
    production_lot -> farmer
    fulfilment_node / trade_corridor / compliance_rule .organization_id

`enforce_path_scope` is attached at router level. It resolves every ``*_id`` path parameter and
answers 404 for records that are missing *or* owned by another organization, so the two cases are
indistinguishable. An ``*_id`` parameter without a resolver is denied rather than allowed through.
Identifiers that arrive in request bodies are checked with `require_owned`.
"""
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context
from src.backend.app.main_dependencies import get_session


def _org_of_buyer(buyer_id) -> Select:
    from src.backend.app.demand.domain.models import Buyer
    return select(Buyer.organization_id).where(Buyer.id == buyer_id)


def _org_of_requirement(requirement_id) -> Select:
    from src.backend.app.demand.domain.models import Buyer, Requirement
    return select(Buyer.organization_id).join(Requirement, Requirement.buyer_id == Buyer.id).where(Requirement.id == requirement_id)


def _org_of_allocation(allocation_id) -> Select:
    from src.backend.app.demand.domain.models import Buyer, Requirement
    from src.backend.app.supply.domain.planning_models import SupplyAllocation
    return (select(Buyer.organization_id).join(Requirement, Requirement.buyer_id == Buyer.id)
            .join(SupplyAllocation, SupplyAllocation.requirement_id == Requirement.id)
            .where(SupplyAllocation.id == allocation_id))


def _org_of_sublot(sublot_id) -> Select:
    from src.backend.app.demand.domain.models import Buyer, Requirement
    from src.backend.app.fulfilment.domain.models import ReceivedSublot
    from src.backend.app.supply.domain.planning_models import SupplyAllocation
    return (select(Buyer.organization_id).join(Requirement, Requirement.buyer_id == Buyer.id)
            .join(SupplyAllocation, SupplyAllocation.requirement_id == Requirement.id)
            .join(ReceivedSublot, ReceivedSublot.allocation_id == SupplyAllocation.id)
            .where(ReceivedSublot.id == sublot_id))


def _org_of_shipment(shipment_id) -> Select:
    from src.backend.app.demand.domain.models import Buyer, Requirement
    from src.backend.app.reconciliation.domain.models import Shipment
    return (select(Buyer.organization_id).join(Requirement, Requirement.buyer_id == Buyer.id)
            .join(Shipment, Shipment.requirement_id == Requirement.id).where(Shipment.id == shipment_id))


def _org_of_recovery(recovery_id) -> Select:
    from src.backend.app.assurance.domain.models import RecoveryRun
    from src.backend.app.demand.domain.models import Buyer, Requirement
    return (select(Buyer.organization_id).join(Requirement, Requirement.buyer_id == Buyer.id)
            .join(RecoveryRun, RecoveryRun.requirement_id == Requirement.id).where(RecoveryRun.id == recovery_id))


def _org_of_programme(programme_id) -> Select:
    from src.backend.app.demand.domain.models import Buyer
    from src.backend.app.programmes.domain.models import Programme
    return select(Buyer.organization_id).join(Programme, Programme.buyer_id == Buyer.id).where(Programme.id == programme_id)


def _org_of_farmer(farmer_id) -> Select:
    from src.backend.app.supply.domain.models import Farmer
    return select(Farmer.organization_id).where(Farmer.id == farmer_id)


def _org_of_lot(lot_id) -> Select:
    from src.backend.app.supply.domain.models import Farmer, ProductionLot
    return select(Farmer.organization_id).join(ProductionLot, ProductionLot.farmer_id == Farmer.id).where(ProductionLot.id == lot_id)


def _org_of_node(node_id) -> Select:
    from src.backend.app.fulfilment.domain.models import FulfilmentNode
    return select(FulfilmentNode.organization_id).where(FulfilmentNode.id == node_id)


def _org_of_corridor(corridor_id) -> Select:
    from src.backend.app.trade_evidence.domain.corridors import TradeCorridor
    return select(TradeCorridor.organization_id).where(TradeCorridor.id == corridor_id)


# Kind -> ownership query. Path parameters use the same names with an ``_id`` suffix.
RESOLVERS: dict[str, Callable[[UUID], Select]] = {
    "buyer": _org_of_buyer,
    "requirement": _org_of_requirement,
    "allocation": _org_of_allocation,
    "sublot": _org_of_sublot,
    "received_sublot": _org_of_sublot,
    "shipment": _org_of_shipment,
    "recovery": _org_of_recovery,
    "programme": _org_of_programme,
    "farmer": _org_of_farmer,
    "lot": _org_of_lot,
    "production_lot": _org_of_lot,
    "fulfilment_node": _org_of_node,
    "corridor": _org_of_corridor,
    "trade_corridor": _org_of_corridor,
}


def organization_of(session: Session, kind: str, record_id: UUID) -> UUID | None:
    resolver = RESOLVERS.get(kind)
    if resolver is None:
        raise LookupError(f"no organization resolver for {kind!r}")
    return session.scalar(resolver(record_id))


def require_owned(session: Session, context: AuthorizationContext, kind: str, record_id: UUID | None,
                  detail: str | None = None) -> None:
    """Raise 404 unless the record exists and belongs to the caller's organization."""
    if record_id is None:
        return
    if organization_of(session, kind, record_id) != context.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail or f"{kind.replace('_', ' ')} not found")


def enforce_path_scope(
    request: Request,
    context: AuthorizationContext = Depends(get_authorization_context),
    session: Session = Depends(get_session),
) -> AuthorizationContext:
    for name, raw in request.path_params.items():
        if not name.endswith("_id"):
            continue
        kind = name.removesuffix("_id")
        if kind not in RESOLVERS:
            # Fail closed: an identifier this guard cannot attribute to an organization is refused.
            raise HTTPException(status.HTTP_403_FORBIDDEN, "resource scope cannot be verified")
        try:
            record_id = UUID(str(raw))
        except ValueError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{kind.replace('_', ' ')} not found") from None
        require_owned(session, context, kind, record_id)
    return context


def tenant_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> str | None:
    """Idempotency keys are namespaced per organization so one tenant cannot replay another's result."""
    if not idempotency_key:
        return None
    return f"{context.organization_id}:{idempotency_key}"


def farmers_in_requirement_organization(buyer_id: UUID) -> Select:
    """Farmers owned by the same organization as the requirement's buyer.

    Planning and recovery must only ever consider supply from the requirement's own organization.
    """
    from src.backend.app.demand.domain.models import Buyer
    from src.backend.app.supply.domain.models import Farmer
    return select(Farmer.id).join(Buyer, Buyer.organization_id == Farmer.organization_id).where(Buyer.id == buyer_id)
