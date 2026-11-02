"""Time-based lot checks run by the worker (R1 WP4, P9). Deterministic; one lot per transaction, re-checked under
the lot's row lock.

* Stale harvest: once HARVEST_REVERIFY_DAYS (default 7) have passed since harvest_end, a lot that still has free
  or reserved stock needs a current confirmation: a capacity report or declaration within the last
  HARVEST_REVERIFY_DAYS. Without one it is flagged for re-verification, which only excludes it from new planning,
  requests and activation. Time alone never marks a lot exhausted and never changes a commitment.
  (The period is one setting for every crop in R1; a per-crop policy is planned.)
* Verified limits: a lot past its verified viable_until date becomes EXHAUSTED and every order with undelivered
  commitments on it gets a LOT_UNAVAILABLE exception (assess_lot_eligibility). Withdrawal is applied immediately by
  the API; the timer only catches viability dates that pass.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.backend.app.supply.application.capacity import refresh_lot_status, require_reverification
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus


def reverify_after_days() -> int:
    return int(os.getenv("HARVEST_REVERIFY_DAYS", "7"))


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def _stale(lot: ProductionLot, now: datetime) -> bool:
    grace = timedelta(days=reverify_after_days())
    if lot.reverification_required or lot.withdrawn_at is not None or lot.status == ProductionLotStatus.EXHAUSTED:
        return False
    if lot.status != ProductionLotStatus.AVAILABLE and lot.reserved_quantity_kg <= 0:
        return False  # nothing left to plan or protect
    if now.date() <= lot.harvest_end + grace:
        return False
    verified = _aware(lot.last_verified_at)
    return verified is None or verified < now - grace


def stale_harvest_candidates(session: Session, now: datetime) -> list[UUID]:
    cutoff = now.date() - timedelta(days=reverify_after_days())
    return list(session.scalars(select(ProductionLot.id).where(
        ProductionLot.harvest_end < cutoff, ProductionLot.reverification_required.is_(False),
        ProductionLot.withdrawn_at.is_(None), ProductionLot.status != ProductionLotStatus.EXHAUSTED)))


def flag_stale_harvest(session: Session, lot_id: UUID, now: datetime) -> bool:
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == lot_id).with_for_update()
                         .execution_options(populate_existing=True))
    if lot is None or not _stale(lot, now):
        return False
    require_reverification(lot, f"harvest ended {lot.harvest_end.isoformat()} and usable stock has not been confirmed "
                                f"in the last {reverify_after_days()} days", now)
    from src.backend.app.assurance.application.events import record_system_event
    from src.backend.app.supply.domain.models import Farmer
    organization_id = session.get(Farmer, lot.farmer_id).organization_id
    record_system_event(session, organization_id, "production_lot.reverification_required", "production_lot", lot.id, {
        "production_lot_id": str(lot.id), "reason": lot.reverification_reason, "cause": "harvest_window_ended"})
    return True


def viability_candidates(session: Session, now: datetime) -> list[UUID]:
    return list(session.scalars(select(ProductionLot.id).where(
        ProductionLot.viable_until.is_not(None), ProductionLot.viable_until < now.date(),
        or_(ProductionLot.status != ProductionLotStatus.EXHAUSTED, ProductionLot.status.is_(None)))))


def expire_viability(session: Session, lot_id: UUID, now: datetime) -> bool:
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == lot_id).with_for_update()
                         .execution_options(populate_existing=True))
    if lot is None or lot.viable_until is None or lot.viable_until >= now.date() or lot.status == ProductionLotStatus.EXHAUSTED:
        return False
    refresh_lot_status(lot, now.date())
    session.flush()
    from src.backend.app.assurance.application.exceptions import assess_lot_eligibility
    assess_lot_eligibility(session, lot.id)
    return True
