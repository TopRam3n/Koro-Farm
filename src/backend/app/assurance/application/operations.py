"""Is supply-exception monitoring actually running?

The API never assumes the worker is up. It is OPERATIONAL only when a worker has beaten recently and nothing it
is responsible for is overdue or dead-lettered; otherwise DEGRADED, with the reasons.

* WORKER_STALE_SECONDS (default 30): a worker silent for longer is treated as stopped.
* PROCESSING_OVERDUE_SECONDS (default 60): a pending outbox message, an unanswered request past its deadline, or
  a standby authorization past its end date still untouched after this long means processing is behind.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage, WorkerHeartbeat
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.supply.domain.planning_models import AllocationStatus, ConsentStatus, SupplyAllocation


def _seconds(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def record_heartbeat(session: Session, worker_id: str, started_at: datetime, tick: dict, now: datetime) -> None:
    row = session.get(WorkerHeartbeat, worker_id)
    if row is None:
        session.add(WorkerHeartbeat(worker_id=worker_id, started_at=started_at, last_beat_at=now, last_tick=tick))
    else:
        row.last_beat_at, row.last_tick = now, tick


def operational_status(session: Session, now: datetime | None = None, organization_id: UUID | None = None) -> dict:
    """Monitoring state. Counts are limited to `organization_id` when given; worker liveness is platform-wide."""
    now = now or datetime.now(timezone.utc)
    stale_after = timedelta(seconds=_seconds("WORKER_STALE_SECONDS", 30))
    overdue_after = timedelta(seconds=_seconds("PROCESSING_OVERDUE_SECONDS", 60))

    last_beat = _aware(session.scalar(select(func.max(WorkerHeartbeat.last_beat_at))))
    live = session.scalar(select(func.count()).select_from(WorkerHeartbeat)
                          .where(WorkerHeartbeat.last_beat_at >= now - stale_after)) or 0
    worker_state = "NOT_SEEN" if last_beat is None else "RUNNING" if live else "STOPPED"

    def outbox(*conditions):
        statement = select(func.count()).select_from(OutboxMessage).where(*conditions)
        if organization_id is not None:
            statement = statement.join(DomainEvent, DomainEvent.id == OutboxMessage.event_id).where(
                DomainEvent.organization_id == organization_id)
        return session.scalar(statement) or 0

    overdue_messages = outbox(OutboxMessage.status == "PENDING", OutboxMessage.created_at < now - overdue_after)
    dead_letters = outbox(OutboxMessage.status == "DEAD")
    def allocations(*conditions):
        statement = select(func.count()).select_from(SupplyAllocation).where(*conditions)
        if organization_id is not None:
            statement = (statement.join(Requirement, Requirement.id == SupplyAllocation.requirement_id)
                         .join(Buyer, Buyer.id == Requirement.buyer_id).where(Buyer.organization_id == organization_id))
        return session.scalar(statement) or 0

    overdue_deadlines = allocations(SupplyAllocation.status == AllocationStatus.SOLICITED,
                                    SupplyAllocation.response_due_at < now - overdue_after)
    overdue_standby = allocations(SupplyAllocation.status == AllocationStatus.STANDBY,
                                  SupplyAllocation.consent_status == ConsentStatus.RECORDED,
                                  SupplyAllocation.authorization_valid_until < (now - overdue_after).date())

    reasons = []
    if worker_state != "RUNNING":
        reasons.append("worker_not_running" if worker_state == "STOPPED" else "worker_never_started")
    if overdue_messages:
        reasons.append("processing_overdue")
    if overdue_deadlines or overdue_standby:
        reasons.append("deadlines_overdue")
    if dead_letters:
        reasons.append("dead_letters")
    return {
        "status": "DEGRADED" if reasons else "OPERATIONAL",
        "reasons": reasons,
        "checked_at": now,
        "worker": {"state": worker_state, "last_beat_at": last_beat, "live_workers": live,
                   "stale_after_seconds": int(stale_after.total_seconds())},
        "processing": {"overdue_messages": overdue_messages, "dead_letters": dead_letters,
                       "overdue_deadlines": overdue_deadlines + overdue_standby,
                       "overdue_after_seconds": int(overdue_after.total_seconds())},
    }

