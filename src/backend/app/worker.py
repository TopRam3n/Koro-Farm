"""Supply-exception worker and recovery orchestrator.

Exception detection, deadlines and the recovery gateway are deterministic. The recovery agent may consult an
optional language model only to choose among deterministic options and draft messages (agents/infrastructure/
model.py); it never executes anything, and every proposal needs human approval before the gateway acts.

Run it next to the API:  APP_ENV=... DATABASE_URL=... python -m src.backend.app.worker

* Outbox: each PENDING message is claimed with SELECT ... FOR UPDATE SKIP LOCKED, so several workers never
  handle the same message. The handler runs in a savepoint: on failure its changes roll back, the attempt is
  recorded with a backoff, and after MAX_ATTEMPTS the message is marked DEAD. Handlers are idempotent
  (exceptions are de-duplicated by key), so a retried or replayed message cannot open duplicates.
* Timers: response reminders (half-way), overdue responses (deadline), standby expiry, stale harvest windows
  (re-verification) and passed viability dates (supply/application/lot_timers.py), one item per transaction,
  each re-checked under a row lock.
* Stock ledger: every LEDGER_CHECK_SECONDS (default 3600) the reservation invariant is checked for every lot;
  mismatches are recorded as findings and degrade monitoring, never repaired (supply/application/ledger.py).
* Recovery: exception events open or join the order's recovery task; due tasks are advanced one transaction each
  (agents/application/orchestrator.py). Approved proposals are executed by the gateway inside that step.
* Heartbeat: every tick records this process's liveness (worker_heartbeats). GET /health/worker and
  GET /system/status report monitoring as DEGRADED when no worker has beaten recently, processing is overdue or
  messages are dead-lettered (app/assurance/application/operations.py).
"""
import logging
import os
import signal
import socket
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import src.backend.app.main  # noqa: F401  (registers every mapped model and validates configuration)
from src.backend.app.agents.application.decision import Decider
from src.backend.app.agents.application.orchestrator import advance_due, on_event
from src.backend.app.agents.infrastructure.model import build_decider
from src.backend.app.assurance.application.exceptions import (
    expire_overdue_response, expire_standby, reevaluate_lot, send_reminder,
)
from src.backend.app.assurance.application.operations import operational_status, record_heartbeat
from src.backend.app.assurance.domain.models import OutboxMessage
from src.backend.app.infrastructure.database.session import create_session_factory
from src.backend.app.supply.application.ledger import check_ledger
from src.backend.app.supply.application.lot_timers import (
    expire_viability, flag_stale_harvest, stale_harvest_candidates, viability_candidates,
)
from src.backend.app.supply.domain.planning_models import AllocationStatus, ConsentStatus, SupplyAllocation

log = logging.getLogger("korofarm.worker")
MAX_ATTEMPTS = 5
_ledger_checked_at: datetime | None = None


def _handle(session: Session, message: OutboxMessage) -> None:
    if message.topic == "lot.capacity_reported":
        if message.payload.get("applied", True):
            reevaluate_lot(session, UUID(message.payload["production_lot_id"]), message.event_id)
    elif message.topic == "sublot.received":
        # Deliveries can cover what a capacity report left exposed; re-check the lot.
        allocation = session.get(SupplyAllocation, UUID(message.payload["allocation_id"]))
        if allocation is not None:
            reevaluate_lot(session, allocation.production_lot_id, message.event_id)
    # Exceptions open or join the order's recovery task; other order events wake it.
    on_event(session, message)


def process_next_message(factory: sessionmaker[Session], now: datetime | None = None) -> bool:
    """Claim and handle one pending outbox message. Returns False when none is ready."""
    now = now or datetime.now(timezone.utc)
    with factory() as session, session.begin():
        message = session.scalar(
            select(OutboxMessage)
            .where(OutboxMessage.status == "PENDING",
                   (OutboxMessage.available_at.is_(None)) | (OutboxMessage.available_at <= now))
            .order_by(OutboxMessage.created_at, OutboxMessage.id)
            .limit(1)
            .with_for_update(skip_locked=True))
        if message is None:
            return False
        try:
            with session.begin_nested():
                _handle(session, message)
            message.status, message.processed_at, message.last_error = "PROCESSED", now, None
        except Exception as exc:  # recorded and retried; never silently dropped
            message.attempts += 1
            message.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if message.attempts >= MAX_ATTEMPTS:
                message.status = "DEAD"
                log.error("outbox message %s dead after %s attempts: %s", message.id, message.attempts, message.last_error)
            else:
                message.available_at = now + timedelta(seconds=2 ** message.attempts)
                log.warning("outbox message %s failed (attempt %s): %s", message.id, message.attempts, message.last_error)
        return True


def _each(factory: sessionmaker[Session], ids, action) -> int:
    done = 0
    for item_id in ids:
        try:
            with factory() as session, session.begin():
                if action(session, item_id):
                    done += 1
        except Exception:  # one bad item must not block the others; it is retried on the next tick
            log.exception("timer action failed for %s", item_id)
    return done


def _expired(action, session: Session, allocation_id: UUID, now: datetime) -> bool:
    before = session.get(SupplyAllocation, allocation_id).status
    action(session, allocation_id, now.date())
    return before == AllocationStatus.STANDBY and session.get(SupplyAllocation, allocation_id).status == AllocationStatus.EXPIRED


def run_timers(factory: sessionmaker[Session], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    with factory() as session:
        open_requests = session.execute(select(SupplyAllocation.id, SupplyAllocation.response_due_at).where(
            SupplyAllocation.status == AllocationStatus.SOLICITED, SupplyAllocation.response_due_at.is_not(None))).all()
        expiring = session.scalars(select(SupplyAllocation.id).where(
            SupplyAllocation.status == AllocationStatus.STANDBY, SupplyAllocation.consent_status == ConsentStatus.RECORDED,
            SupplyAllocation.authorization_valid_until.is_not(None),
            SupplyAllocation.authorization_valid_until < now.date())).all()
        stale = stale_harvest_candidates(session, now)
        past_viability = viability_candidates(session, now)

    def due(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    overdue = [row.id for row in open_requests if due(row.response_due_at) <= now]
    pending = [row.id for row in open_requests if due(row.response_due_at) > now]
    return {
        "reminders": _each(factory, pending, lambda s, i: send_reminder(s, i, now)),
        "expired_requests": _each(factory, overdue, lambda s, i: expire_overdue_response(s, i, now) is not None),
        # Counts standby authorizations checked and expired this tick (recovery-impact exceptions are a subset).
        "standby_expired": _each(factory, expiring, lambda s, i: _expired(expire_standby, s, i, now)),
        "lots_reverification_required": _each(factory, stale, lambda s, i: flag_stale_harvest(s, i, now)),
        "lots_past_viability": _each(factory, past_viability, lambda s, i: expire_viability(s, i, now)),
        "ledger_mismatches": run_ledger_check(factory, now),
    }


def run_ledger_check(factory: sessionmaker[Session], now: datetime, force: bool = False) -> int:
    """Check the reservation invariant at most every LEDGER_CHECK_SECONDS. Returns the number of mismatched lots."""
    global _ledger_checked_at
    interval = timedelta(seconds=int(os.getenv("LEDGER_CHECK_SECONDS", "3600")))
    if not force and _ledger_checked_at is not None and abs(now - _ledger_checked_at) < interval:
        return 0
    try:
        with factory() as session, session.begin():
            found = check_ledger(session, now=now)
    except Exception:  # a failed check is retried next tick; it never blocks other work
        log.exception("stock ledger check failed")
        return 0
    _ledger_checked_at = now
    for mismatch in found:
        log.error("stock ledger mismatch: %s", mismatch)
    return len(found)


def run_once(factory: sessionmaker[Session], now: datetime | None = None, max_messages: int = 500,
             decider: Decider | None = None) -> dict:
    processed = 0
    while processed < max_messages and process_next_message(factory, now):
        processed += 1
    timers = run_timers(factory, now)
    # Timers can open exceptions (overdue responses): hand their events to the orchestrator in the same tick.
    while processed < max_messages and process_next_message(factory, now):
        processed += 1
    advanced = advance_due(factory, now, decider)
    # Drain what recovery just recorded, so a tick leaves nothing of its own pending.
    while processed < max_messages and process_next_message(factory, now):
        processed += 1
    return {"messages": processed, **timers, "recovery_tasks": advanced}


def beat(factory: sessionmaker[Session], worker_id: str, started_at: datetime, tick: dict,
         now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    with factory() as session, session.begin():
        record_heartbeat(session, worker_id, started_at, tick, now)


def main() -> None:
    logging.basicConfig(level=os.getenv("WORKER_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    interval = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    factory = create_session_factory()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    started_at = datetime.now(timezone.utc)
    stopping = False
    alerted: set[str] = set()
    decider = build_decider()

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    log.info("supply-exception worker started (poll every %ss; recovery decisions: %s)", interval, decider.mode)
    while not stopping:
        try:
            result = run_once(factory, decider=decider)
            if any(result.values()):
                log.info("tick %s", result)
            beat(factory, worker_id, started_at, result)
            with factory() as session:
                reasons = set(operational_status(session)["reasons"]) - {"worker_not_running", "worker_never_started"}
            for reason in sorted(reasons - alerted):  # alert once per condition until it clears
                log.error("supply-exception monitoring degraded: %s", reason)
            alerted = reasons
        except Exception:
            log.exception("worker tick failed; retrying")
        time.sleep(interval)
    log.info("supply-exception worker stopped")


if __name__ == "__main__":
    main()
