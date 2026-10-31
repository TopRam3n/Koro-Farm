"""Recovery task orchestrator, run by the worker (app/worker.py). It proposes; it never executes.

Lifecycle of the single active task per order:
  QUEUED -> AWAITING_APPROVAL -> EXECUTING -> AWAITING_SUPPLIER -> ... -> COMPLETED
                                \-> (rejected, superseded or stale: re-plan)        \-> ESCALATED (a person must act)
  any active state -> CANCELLED (order cancelled, or a person cancels); bounded retries -> FAILED

* Triggers are durable: exceptions (capacity, dropout, quality rejection, overdue response, standby expiry) are
  written with their outbox events in the same transaction as the incident, and `on_event` turns
  `exception.opened` into a task or joins the order's active task. Other order events only wake the task.
* One active task per order (partial unique index): simultaneous exceptions on one order join one task, which
  always plans against the order's whole current shortfall, so two plans can never claim the same quantity.
* Each advance runs in one transaction under the task's row lock (SELECT ... FOR UPDATE SKIP LOCKED). Its steps,
  proposals and any execution commit together or not at all, so a worker restart resumes from the last committed
  step without repeating supplier requests or standby activation.
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.backend.app.agents.application import evidence as ev
from src.backend.app.agents.application.decision import Decider, DeterministicDecider, model_context, template_buyer_draft, template_supplier_draft
from src.backend.app.agents.application.policy import content_hash, current_policy, evaluate, policy_snapshot
from src.backend.app.agents.application.timeline import AGENT, add_step, agent_event, current_proposal
from src.backend.app.agents.domain.models import (
    ACTIVE_TASK_STATUSES, ProposalStatus, RecoveryIncident, RecoveryProposal, RecoveryTask, StepKind,
    TaskStatus,
)
from src.backend.app.assurance.application.exceptions import resolve_recovered
from src.backend.app.assurance.domain.exceptions import ExceptionStatus, SupplyException
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage, RecoveryRun, RecoveryStatus
from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus, SupplyHealth

log = logging.getLogger("korofarm.recovery")
MAX_ATTEMPTS = 5
MAX_PROPOSALS = 8
SUPPLIER_RECHECK = timedelta(minutes=5)
FRESH = {"populate_existing": True}

# Order events that may change what recovery should do. The agent's own recovery.* events are not listed.
WAKE_TOPICS = {
    "exception.updated", "exception.resolved", "supplier.accepted", "supplier.declined", "standby.authorized",
    "solicitation.expired", "solicitation.withdrawn", "standby.expired", "requirement.cancelled", "order.cancelled",
    "sublot.received",
}


class RecoveryError(ValueError):
    pass


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def active_task(session: Session, requirement_id: UUID, lock: bool = True) -> RecoveryTask | None:
    statement = select(RecoveryTask).where(RecoveryTask.requirement_id == requirement_id,
                                           RecoveryTask.status.in_(ACTIVE_TASK_STATUSES))
    if lock:
        statement = statement.with_for_update().execution_options(**FRESH)
    return session.scalar(statement)


def ensure_task(session: Session, requirement_id: UUID, kind: str, source_key: str, summary: str,
                quantity: Decimal = Decimal("0"), exception_id: UUID | None = None, source_event_id: UUID | None = None,
                now: datetime | None = None) -> RecoveryTask | None:
    """Create the order's recovery task, or join its active one, and record the incident once."""
    now = now or datetime.now(timezone.utc)
    requirement = session.get(Requirement, requirement_id)
    if requirement is None or requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        return None
    task = active_task(session, requirement_id)
    if task is None:
        organization_id = session.scalar(select(Buyer.organization_id).where(Buyer.id == requirement.buyer_id))
        task = RecoveryTask(organization_id=organization_id, requirement_id=requirement_id, status=TaskStatus.QUEUED,
                            next_run_at=now, created_at=now, updated_at=now)
        try:
            with session.begin_nested():
                session.add(task)
                session.flush()
        except IntegrityError:  # another worker created it first (partial unique index): join that one
            task = active_task(session, requirement_id)
            if task is None:
                raise
        else:
            add_step(session, task, StepKind.INCIDENT, AGENT, f"Recovery task opened: {summary}", {"kind": kind})
            agent_event(session, task, "recovery.task_opened", {"trigger": kind, "summary": summary})
    if session.scalar(select(RecoveryIncident.id).where(RecoveryIncident.task_id == task.id, RecoveryIncident.source_key == source_key)) is None:
        session.add(RecoveryIncident(task_id=task.id, organization_id=task.organization_id, requirement_id=requirement_id,
                                     kind=kind, source_key=source_key, exception_id=exception_id,
                                     source_event_id=source_event_id, quantity_kg=quantity, summary=summary[:500]))
        session.flush()
        if task.step_count > 1:
            add_step(session, task, StepKind.INCIDENT, AGENT, f"New incident joined this task: {summary}", {"kind": kind})
    task.next_run_at = now
    return task


def wake(session: Session, requirement_id: UUID, now: datetime | None = None) -> RecoveryTask | None:
    task = active_task(session, requirement_id)
    if task is not None:
        task.next_run_at = now or datetime.now(timezone.utc)
    return task


def on_event(session: Session, message: OutboxMessage, now: datetime | None = None) -> None:
    """Outbox hook: exceptions open or join a task; other order events wake it."""
    event = session.get(DomainEvent, message.event_id)
    if event is None or event.aggregate_type != "requirement":
        return
    if message.topic == "exception.opened":
        payload = message.payload
        exception = session.get(SupplyException, UUID(payload["exception_id"]))
        if exception is None or exception.status != ExceptionStatus.OPEN:
            return
        reason = (exception.details or {}).get("reason")
        summary = f"{exception.summary} (reason recorded: {reason})" if reason else exception.summary
        ensure_task(session, event.aggregate_id, exception.kind.value, f"exception:{exception.id}", summary,
                    exception.shortfall_kg, exception.id, event.id, now)
    elif message.topic in WAKE_TOPICS:
        wake(session, event.aggregate_id, now)


def request_recovery(session: Session, actor, requirement_id: UUID, note: str | None) -> RecoveryTask:
    """A coordinator asks the agent to (re)plan. This only queues planning; it never executes anything."""
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise RecoveryError("order not found")
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        raise RecoveryError("the order has been cancelled")
    task = ensure_task(session, requirement_id, "MANUAL_REQUEST", f"manual:{datetime.now(timezone.utc).isoformat()}",
                       f"Re-plan requested by a coordinator{': ' + note if note else ''}")
    if task.status == TaskStatus.ESCALATED:
        task.status = TaskStatus.QUEUED
    add_step(session, task, StepKind.INCIDENT, str(actor.user_id), "A coordinator asked the agent to plan recovery",
             {"note": note})
    return task


def cancel_task(session: Session, actor, task_id: UUID, reason: str) -> RecoveryTask:
    task = session.scalar(select(RecoveryTask).where(RecoveryTask.id == task_id).with_for_update().execution_options(**FRESH))
    if task is None or task.status not in ACTIVE_TASK_STATUSES:
        raise RecoveryError("only an active recovery task can be cancelled")
    _supersede_pending(session, task, f"task cancelled: {reason}", ProposalStatus.SUPERSEDED)
    _close(session, task, TaskStatus.CANCELLED, f"cancelled by a coordinator: {reason}", str(actor.user_id))
    return task


# --- Advancing ------------------------------------------------------------------------------------------------

def _close(session: Session, task: RecoveryTask, status: TaskStatus, reason: str, actor: str = AGENT) -> None:
    now = datetime.now(timezone.utc)
    task.status, task.terminal_reason, task.closed_at, task.next_run_at = status, reason[:500], now, None
    kind = {TaskStatus.COMPLETED: StepKind.COMPLETE, TaskStatus.CANCELLED: StepKind.CANCEL}.get(status, StepKind.ERROR)
    add_step(session, task, kind, actor, reason)
    agent_event(session, task, f"recovery.task_{status.value.lower()}", {"reason": reason}, actor=actor)


def _supersede_pending(session: Session, task: RecoveryTask, reason: str, status: ProposalStatus) -> None:
    proposal = current_proposal(session, task)
    if proposal is not None and proposal.status in (ProposalStatus.PENDING, ProposalStatus.APPROVED):
        proposal.status, proposal.status_reason, proposal.decided_at = status, reason[:500], datetime.now(timezone.utc)
        add_step(session, task, StepKind.PLAN, AGENT, f"Proposal v{proposal.version} {status.value.lower()}: {reason}",
                 proposal_id=proposal.id)
        agent_event(session, task, "recovery.proposal_superseded", {"proposal_id": str(proposal.id), "reason": reason})


def _incidents(session: Session, task: RecoveryTask) -> list[dict]:
    rows = session.scalars(select(RecoveryIncident).where(RecoveryIncident.task_id == task.id).order_by(RecoveryIncident.recorded_at)).all()
    return [{"kind": r.kind, "quantity_kg": ev.kg(r.quantity_kg), "note": r.summary} for r in rows]


def _excluded(session: Session, task: RecoveryTask) -> set[str]:
    """Targets of rejected proposals: a reviewer's rejection is respected when re-planning."""
    excluded: set[str] = set()
    for content in session.scalars(select(RecoveryProposal.content).where(RecoveryProposal.task_id == task.id,
                                                                          RecoveryProposal.status == ProposalStatus.REJECTED)):
        for action in content["actions"]:
            if action["type"] == ev.ACTIVATE_STANDBY:
                excluded.add(action["allocation_id"])
            elif action["type"] == ev.SOLICIT_SUPPLY:
                excluded.add(action["production_lot_id"])
    return excluded


def still_feasible(evidence: ev.Evidence, content: dict) -> list[str]:
    """Why a pending proposal no longer matches the order (empty when it still does)."""
    problems = []
    if content["basis"]["net_need_kg"] != evidence.basis.as_dict()["net_need_kg"]:
        problems.append(f"the order's need changed from {content['basis']['net_need_kg']} to {evidence.basis.as_dict()['net_need_kg']} kg")
    standby = {str(c.allocation.id): c.activatable_kg for c in evidence.standby}
    supply = {str(c.lot.id): c.free_kg for c in evidence.supply}
    releases = {str(r.allocation.id): r.exposed_kg for r in evidence.releases}
    for action in content["actions"]:
        quantity = Decimal(action["quantity_kg"])
        if action["type"] == ev.ACTIVATE_STANDBY and standby.get(action["allocation_id"], Decimal("0")) < quantity:
            problems.append(f"standby from {action['farmer_name']} no longer has {action['quantity_kg']} kg available")
        if action["type"] == ev.SOLICIT_SUPPLY and supply.get(action["production_lot_id"], Decimal("0")) < quantity:
            problems.append(f"{action['farmer_name']}'s lot no longer has {action['quantity_kg']} kg free")
        if action["type"] == ev.RELEASE_EXPOSED and releases.get(action["allocation_id"], Decimal("0")) < quantity:
            problems.append(f"{action['farmer_name']}'s exposed commitment changed")
    return problems


def _escalate(session: Session, task: RecoveryTask, requirement: Requirement, residual: Decimal, reason: str) -> None:
    if task.status == TaskStatus.ESCALATED and task.escalated_kg == residual:
        return  # nothing new to say; avoid repeating the same escalation on every wake
    task.status, task.escalated_kg, task.next_run_at = TaskStatus.ESCALATED, residual, None
    requirement.supply_health = SupplyHealth.ESCALATION_REQUIRED
    run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id,
                                                   RecoveryRun.status == RecoveryStatus.RUNNING).with_for_update())
    if run is not None:
        run.status, run.active_key, run.remaining_shortfall_kg = RecoveryStatus.ESCALATED, None, residual
        run.completed_at = datetime.now(timezone.utc)
    add_step(session, task, StepKind.ESCALATE, AGENT, f"Escalated {ev.kg(residual)} kg to a coordinator: {reason}",
             {"residual_kg": ev.kg(residual)})
    agent_event(session, task, "recovery.escalated", {"remaining_shortfall_kg": ev.kg(residual), "reason": reason})


def _complete(session: Session, task: RecoveryTask, requirement: Requirement, basis: ev.Basis) -> None:
    resolved = resolve_recovered(session, requirement, AGENT, f"Order shortfall covered (recovery task {str(task.id)[:8]})")
    run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id,
                                                   RecoveryRun.status.in_([RecoveryStatus.RUNNING, RecoveryStatus.ESCALATED]))
                         .with_for_update())
    if run is not None:
        run.status, run.active_key, run.remaining_shortfall_kg = RecoveryStatus.COMPLETED, None, Decimal("0")
        run.completed_at = datetime.now(timezone.utc)
    session.flush()
    still_open = session.scalar(select(SupplyException.id).where(SupplyException.requirement_id == requirement.id,
                                                                 SupplyException.status == ExceptionStatus.OPEN).limit(1))
    if still_open is None and requirement.supply_health != SupplyHealth.COVERED:
        requirement.supply_health = SupplyHealth.COVERED
    handled = task.proposals_made > 0
    _close(session, task, TaskStatus.COMPLETED,
           f"Order shortfall covered: {ev.kg(basis.assured_kg)} kg assured of {ev.kg(basis.required_kg)} kg required"
           if handled else "No shortfall left to recover; nothing was proposed")
    if resolved:
        add_step(session, task, StepKind.COMPLETE, AGENT, f"Closed {resolved} incident exception(s) on the order")


def _plan(session: Session, task: RecoveryTask, requirement: Requirement, decider: Decider, now: datetime) -> None:
    evidence = ev.gather(session, requirement, now)
    basis = evidence.basis
    if basis.net_need_kg <= 0:
        if basis.in_flight_kg > 0:
            if task.status != TaskStatus.AWAITING_SUPPLIER:
                add_step(session, task, StepKind.WAIT, AGENT,
                         f"Waiting for suppliers to answer requests for {ev.kg(basis.in_flight_kg)} kg", basis.as_dict())
            task.status, task.next_run_at = TaskStatus.AWAITING_SUPPLIER, now + SUPPLIER_RECHECK
            return
        _complete(session, task, requirement, basis)
        return
    if task.proposals_made >= MAX_PROPOSALS:
        _escalate(session, task, requirement, basis.net_need_kg, f"{MAX_PROPOSALS} proposals made without covering the order")
        return
    options = ev.build_options(evidence, _excluded(session, task))
    replaceable = any(Decimal(o["standby_activated_kg"]) + Decimal(o["requested_kg"]) > 0 for o in options)
    if not replaceable and not evidence.releases:
        reason = "no authorized standby or eligible unreserved supply is available"
        if basis.in_flight_kg > 0:
            reason += f"; {ev.kg(basis.in_flight_kg)} kg of requests are still awaiting suppliers"
        _escalate(session, task, requirement, basis.net_need_kg, reason)
        return

    incidents = _incidents(session, task)
    context = model_context(evidence, options, incidents)
    decision = decider.decide(context)
    option = next(o for o in options if o["id"] == decision.option_id)
    add_step(session, task, StepKind.DECISION, AGENT,
             f"Chose option {option['id']} of {len(options)} ({decision.mode}{', ' + decision.model if decision.model else ''})",
             {"options_offered": [o["id"] for o in options], "rationale": decision.rationale,
              "violations": decision.violations, "fallback_reason": decision.fallback_reason})
    if not option["actions"]:
        _escalate(session, task, requirement, basis.net_need_kg, f"decision recommends escalation: {decision.rationale}")
        return

    window = f"{requirement.delivery_window_start.isoformat()} to {requirement.delivery_window_end.isoformat()}"
    crop = str(requirement.crop).replace("_", " ").lower()
    actions = []
    for action in option["actions"]:
        if action["type"] == ev.SOLICIT_SUPPLY:
            action = {**action, "message": decision.supplier_drafts.get(action["supplier_label"]) or template_supplier_draft(action, crop, window)}
        actions.append(action)
    has_writes = bool(actions)
    policy = policy_snapshot(current_policy(session, evidence.organization_id))
    tier, reasons = evaluate(option["cost"], policy, has_writes)
    expires = ev.expiry_for(evidence, option, now)
    version = task.proposals_made + 1
    content = {
        "schema": "recovery-proposal-v1", "task_id": str(task.id), "requirement_id": str(requirement.id),
        "organization_id": str(task.organization_id), "version": version, "created_at": now.isoformat(),
        "expires_at": expires.isoformat(), "basis": basis.as_dict(), "incidents": incidents, "options": options,
        "chosen_option_id": option["id"], "actions": actions, "escalation_kg": option["escalation_kg"], "cost": option["cost"],
        "approval": {"tier": tier.value, "reasons": reasons, "policy": policy,
                     "required": "one approver with recovery.approve" if tier.value == "ORDINARY"
                     else "two different approvers, at least one with recovery.approve_elevated"},
        "decision": {"mode": decision.mode, "model": decision.model, "rationale": decision.rationale,
                     "recommend_escalation": decision.recommend_escalation,
                     "information_requests": decision.information_requests, "violations": decision.violations,
                     "fallback_reason": decision.fallback_reason},
        "drafts": {"buyer": decision.buyer_draft or template_buyer_draft(context, option),
                   "status": "Draft only. Not sent to anyone; external messages are not sent automatically."},
    }
    proposal = RecoveryProposal(task_id=task.id, organization_id=task.organization_id, requirement_id=requirement.id,
                                version=version, status=ProposalStatus.PENDING, tier=tier, content=content,
                                content_hash=content_hash(content), expires_at=expires, created_at=now)
    session.add(proposal)
    session.flush()
    task.proposals_made = version
    task.status, task.next_run_at = TaskStatus.AWAITING_APPROVAL, expires
    add_step(session, task, StepKind.PROPOSE, AGENT,
             f"Proposal v{version} awaits {tier.value.lower()} approval: {len(actions)} action(s), "
             f"{option['escalation_kg']} kg left for escalation", {"hash": proposal.content_hash, "tier": tier.value,
                                                                   "reasons": reasons}, proposal.id)
    agent_event(session, task, "recovery.proposed", {"proposal_id": str(proposal.id), "version": version, "tier": tier.value,
                                                     "option": option["id"], "hash": proposal.content_hash,
                                                     "escalation_kg": option["escalation_kg"]})
    if Decimal(option["escalation_kg"]) > 0:
        task.escalated_kg = Decimal(option["escalation_kg"])


def advance_task(session: Session, task: RecoveryTask, decider: Decider, now: datetime) -> None:
    from src.backend.app.agents.application.gateway import execute
    task.next_run_at = None
    requirement = session.scalar(select(Requirement).where(Requirement.id == task.requirement_id).with_for_update().execution_options(**FRESH))
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        _supersede_pending(session, task, "order cancelled", ProposalStatus.SUPERSEDED)
        _close(session, task, TaskStatus.CANCELLED, "The order was cancelled")
        return
    proposal = current_proposal(session, task)
    if task.status == TaskStatus.EXECUTING and proposal is not None and proposal.status == ProposalStatus.APPROVED:
        execute(session, task, proposal, requirement, now)
        if task.status == TaskStatus.QUEUED:  # stale or partially applied: re-plan from current facts now
            _plan(session, task, requirement, decider, now)
        return
    if task.status == TaskStatus.AWAITING_APPROVAL and proposal is not None and proposal.status == ProposalStatus.PENDING:
        if _aware(proposal.expires_at) <= now:
            _supersede_pending(session, task, "the approval window expired", ProposalStatus.SUPERSEDED)
        else:
            problems = still_feasible(ev.gather(session, requirement, now), proposal.content)
            if not problems:
                task.next_run_at = proposal.expires_at
                return
            _supersede_pending(session, task, "; ".join(problems), ProposalStatus.SUPERSEDED)
    _plan(session, task, requirement, decider, now)


def advance_due(factory: sessionmaker[Session], now: datetime | None = None, decider: Decider | None = None,
                limit: int = 50) -> int:
    """Advance every task whose next run is due. Each task in its own transaction; failures retry with backoff."""
    now = now or datetime.now(timezone.utc)
    decider = decider or DeterministicDecider()
    with factory() as session:
        due = session.scalars(select(RecoveryTask.id).where(
            RecoveryTask.status.in_(ACTIVE_TASK_STATUSES), RecoveryTask.next_run_at.is_not(None),
            RecoveryTask.next_run_at <= now).order_by(RecoveryTask.next_run_at).limit(limit)).all()
    advanced = 0
    for task_id in due:
        try:
            with factory() as session, session.begin():
                task = session.scalar(select(RecoveryTask).where(RecoveryTask.id == task_id).with_for_update(skip_locked=True))
                if task is None or task.status not in ACTIVE_TASK_STATUSES or task.next_run_at is None or _aware(task.next_run_at) > now:
                    continue
                try:
                    with session.begin_nested():
                        advance_task(session, task, decider, now)
                    task.attempts, task.last_error = 0, None
                except Exception as exc:  # recorded and retried; never silently dropped
                    task.attempts += 1
                    task.last_error = f"{type(exc).__name__}: {exc}"[:1000]
                    log.warning("recovery task %s failed (attempt %s): %s", task.id, task.attempts, task.last_error)
                    if task.attempts >= MAX_ATTEMPTS:
                        _close(session, task, TaskStatus.FAILED, f"failed after {task.attempts} attempts: {task.last_error}")
                    else:
                        task.next_run_at = now + timedelta(seconds=2 ** task.attempts)
                advanced += 1
        except Exception:
            log.exception("recovery task %s could not be advanced", task_id)
    return advanced


def overdue_tasks_query(threshold: datetime):
    return select(RecoveryTask.id).where(RecoveryTask.status.in_(ACTIVE_TASK_STATUSES), RecoveryTask.next_run_at.is_not(None),
                                         RecoveryTask.next_run_at < threshold)

