"""Stock ledger check (R1 WP4, M8). Deterministic; never repairs anything.

Invariant, for every production lot:
    reserved_quantity_kg == sum(quantity_kg - released_quantity_kg) over allocations with holds_reservation
                            + sum(quantity_kg) over PLACED marketplace orders

A mismatch is recorded as an open StockLedgerFinding (lot, recorded, expected, difference) and makes monitoring
DEGRADED (assurance/application/operations.py, reason `stock_ledger_mismatch`). It is resolved only when a later
check finds the lot balanced again; correcting it is a deliberate, audited action (scripts/release_audit.py).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.marketplace.domain.models import MarketplaceOrder, MarketplaceOrderStatus
from src.backend.app.reconciliation.domain.models import StockLedgerFinding
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import SupplyAllocation

ZERO = Decimal("0")


def expected_reserved(session: Session, organization_id: UUID | None = None) -> dict[UUID, tuple[Decimal, Decimal, UUID]]:
    """lot id -> (recorded reserved, expected reserved, organization id).

    One statement, so under READ COMMITTED both sides come from the same snapshot and a reservation committed
    mid-check cannot show up as a false mismatch."""
    held = (select(func.coalesce(func.sum(SupplyAllocation.quantity_kg - func.coalesce(SupplyAllocation.released_quantity_kg, 0)), 0))
            .where(SupplyAllocation.production_lot_id == ProductionLot.id, SupplyAllocation.holds_reservation.is_(True))
            .scalar_subquery())
    placed = (select(func.coalesce(func.sum(MarketplaceOrder.quantity_kg), 0))
              .where(MarketplaceOrder.production_lot_id == ProductionLot.id, MarketplaceOrder.status == MarketplaceOrderStatus.PLACED)
              .scalar_subquery())
    lots = (select(ProductionLot.id, ProductionLot.reserved_quantity_kg, held, placed, Farmer.organization_id)
            .join(Farmer, Farmer.id == ProductionLot.farmer_id))
    if organization_id is not None:
        lots = lots.where(Farmer.organization_id == organization_id)
    return {lot_id: (Decimal(recorded or 0), Decimal(held_kg or 0) + Decimal(placed_kg or 0), org)
            for lot_id, recorded, held_kg, placed_kg, org in session.execute(lots).all()}


def mismatches(session: Session, organization_id: UUID | None = None) -> list[dict]:
    return [{"production_lot_id": str(lot_id), "organization_id": str(org), "recorded_reserved_kg": str(recorded),
             "expected_reserved_kg": str(expected), "difference_kg": str(recorded - expected)}
            for lot_id, (recorded, expected, org) in expected_reserved(session, organization_id).items() if recorded != expected]


def check_ledger(session: Session, organization_id: UUID | None = None, now: datetime | None = None) -> list[dict]:
    """Record open findings for mismatched lots and resolve findings for lots that balance again."""
    now = now or datetime.now(timezone.utc)
    found = mismatches(session, organization_id)
    by_lot = {UUID(m["production_lot_id"]): m for m in found}
    statement = select(StockLedgerFinding).where(StockLedgerFinding.resolved_at.is_(None))
    if organization_id is not None:
        statement = statement.where(StockLedgerFinding.organization_id == organization_id)
    open_findings = {f.production_lot_id: f for f in session.scalars(statement)}
    for lot_id, finding in open_findings.items():
        if lot_id not in by_lot:
            finding.resolved_at = now
    for lot_id, m in by_lot.items():
        finding = open_findings.get(lot_id)
        if finding is None:
            session.add(StockLedgerFinding(organization_id=UUID(m["organization_id"]), production_lot_id=lot_id,
                                           recorded_reserved_kg=Decimal(m["recorded_reserved_kg"]),
                                           expected_reserved_kg=Decimal(m["expected_reserved_kg"]),
                                           difference_kg=Decimal(m["difference_kg"]), detected_at=now, last_seen_at=now))
        else:
            finding.recorded_reserved_kg, finding.expected_reserved_kg = Decimal(m["recorded_reserved_kg"]), Decimal(m["expected_reserved_kg"])
            finding.difference_kg, finding.last_seen_at = Decimal(m["difference_kg"]), now
    session.flush()
    return found
