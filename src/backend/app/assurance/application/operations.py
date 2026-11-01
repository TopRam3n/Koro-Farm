"""Is supply-exception monitoring actually running?

The API never assumes the worker is up. It is OPERATIONAL only when a worker has beaten recently and nothing it
is responsible for is overdue or dead-lettered; otherwise DEGRADED, with the reasons.

* WORKER_STALE_SECONDS (default 30): a worker silent for longer is treated as stopped.
* PROCESSING_OVERDUE_SECONDS (default 60): a pending outbox message, an unanswered request past its deadline, or
  a standby authorization past its end date still untouched after this long means processing is behind.
* Recovery: a recovery task due for longer than PROCESSING_OVERDUE_SECONDS, or a FAILED task that no newer task
  for the same order has replaced, also makes monitoring DEGRADED (an incident would otherwise go unhandled).
* Models (warnings only, never DEGRADED: deterministic decisions keep recovery working): per provider and model,
  calls, fallbacks, latency and estimated cost over MODEL_WINDOW_HOURS (default 24); a warning when at least
  MODEL_WARNING_MIN_CALLS calls (default 5) fell back at a rate of MODEL_FALLBACK_WARNING_RATE (default 0.5) or more.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from src.backend.app.agents.domain.models import ACTIVE_TASK_STATUSES, RecoveryModelCall, RecoveryTask, TaskStatus
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

    def tasks(*conditions):
        statement = select(func.count()).select_from(RecoveryTask).where(*conditions)
        if organization_id is not None:
            statement = statement.where(RecoveryTask.organization_id == organization_id)
        return session.scalar(statement) or 0

    newer = aliased(RecoveryTask)
    overdue_tasks = tasks(RecoveryTask.status.in_(ACTIVE_TASK_STATUSES), RecoveryTask.next_run_at.is_not(None),
                          RecoveryTask.next_run_at < now - overdue_after)
    failed_tasks = tasks(RecoveryTask.status == TaskStatus.FAILED, ~select(newer.id).where(
        newer.requirement_id == RecoveryTask.requirement_id, newer.created_at > RecoveryTask.created_at).exists())

    since = now - timedelta(hours=_seconds("MODEL_WINDOW_HOURS", 24))
    model_query = select(RecoveryModelCall.provider, RecoveryModelCall.configured_model, func.count(),
                         func.sum(case((RecoveryModelCall.outcome == "fallback", 1), else_=0)),
                         func.avg(RecoveryModelCall.latency_ms), func.sum(RecoveryModelCall.estimated_cost_usd)
                         ).where(RecoveryModelCall.created_at >= since).group_by(RecoveryModelCall.provider, RecoveryModelCall.configured_model)
    if organization_id is not None:
        model_query = model_query.where(RecoveryModelCall.organization_id == organization_id)
    models, warnings = [], []
    threshold = float(os.getenv("MODEL_FALLBACK_WARNING_RATE", "0.5"))
    for provider, model, calls, fallbacks, latency, cost in session.execute(model_query).all():
        rate = (fallbacks or 0) / calls if calls else 0
        models.append({"provider": provider, "model": model, "calls": calls, "fallbacks": int(fallbacks or 0),
                       "fallback_rate": round(rate, 3), "average_latency_ms": int(latency) if latency is not None else None,
                       "estimated_cost_usd": str(cost) if cost is not None else None})
        if calls >= _seconds("MODEL_WARNING_MIN_CALLS", 5) and rate >= threshold:
            warnings.append(f"model_fallbacks_high:{provider}:{model}")

    reasons = []
    if worker_state != "RUNNING":
        reasons.append("worker_not_running" if worker_state == "STOPPED" else "worker_never_started")
    if overdue_messages:
        reasons.append("processing_overdue")
    if overdue_deadlines or overdue_standby:
        reasons.append("deadlines_overdue")
    if dead_letters:
        reasons.append("dead_letters")
    if overdue_tasks:
        reasons.append("recovery_overdue")
    if failed_tasks:
        reasons.append("recovery_failed")
    return {
        "status": "DEGRADED" if reasons else "OPERATIONAL",
        "reasons": reasons,
        "checked_at": now,
        "worker": {"state": worker_state, "last_beat_at": last_beat, "live_workers": live,
                   "stale_after_seconds": int(stale_after.total_seconds())},
        "processing": {"overdue_messages": overdue_messages, "dead_letters": dead_letters,
                       "overdue_deadlines": overdue_deadlines + overdue_standby,
                       "overdue_after_seconds": int(overdue_after.total_seconds())},
        "recovery": {"overdue_tasks": overdue_tasks, "failed_tasks": failed_tasks},
        "warnings": warnings,
        "models": {"window_hours": _seconds("MODEL_WINDOW_HOURS", 24), "by_model": models,
                   "cost_note": "estimates from published list prices, not account charges"},
    }

