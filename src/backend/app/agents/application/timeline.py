"""Shared recording helpers: every task step is an append-only row, and every material step is also a domain event
on the order, so it appears in the order history and the audit trail."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.agents.domain.models import RecoveryProposal, RecoveryStep, RecoveryTask, StepKind
from src.backend.app.assurance.application.events import record_system_event

AGENT = "recovery-agent"
GATEWAY = "recovery-gateway"


def add_step(session: Session, task: RecoveryTask, kind: StepKind, actor: str, summary: str, detail: dict | None = None,
             proposal_id: UUID | None = None) -> RecoveryStep:
    task.step_count += 1
    task.updated_at = datetime.now(timezone.utc)
    step = RecoveryStep(task_id=task.id, organization_id=task.organization_id, sequence=task.step_count, kind=kind,
                        actor=actor, summary=summary[:1000], detail=detail or {}, proposal_id=proposal_id)
    session.add(step)
    session.flush()
    return step


def agent_event(session: Session, task: RecoveryTask, event_type: str, payload: dict, actor: str = AGENT) -> None:
    """actor is "recovery-agent", "recovery-gateway" or a person's user id; people are recorded as users."""
    actor_type = "agent" if actor in (AGENT, GATEWAY) else "user"
    record_system_event(session, task.organization_id, event_type, "requirement", task.requirement_id,
                        {"recovery_task_id": str(task.id), **payload}, actor_id=actor, actor_type=actor_type)


def current_proposal(session: Session, task: RecoveryTask) -> RecoveryProposal | None:
    session.flush()  # populate_existing below must not discard unflushed changes (sessions run without autoflush)
    return session.scalar(select(RecoveryProposal).where(RecoveryProposal.task_id == task.id)
                          .order_by(RecoveryProposal.version.desc()).limit(1)
                          .with_for_update().execution_options(populate_existing=True))
