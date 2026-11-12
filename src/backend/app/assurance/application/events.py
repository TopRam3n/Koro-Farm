"""One way for commands to record what happened.

`record_event` writes an attributable DomainEvent and its OutboxMessage in the caller's transaction.
`replay_or_none` / `remember` give create/update commands optional Idempotency-Key semantics using the
existing CommandDeduplication table (keys arrive already namespaced per organization).
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import CommandDeduplication, DomainEvent, OutboxMessage
from src.backend.app.identity.application.authorization import AuthorizationContext


def record_event(session: Session, context: AuthorizationContext, event_type: str, aggregate_type: str,
                 aggregate_id: UUID, payload: dict, *, idempotency_key: str | None = None,
                 correlation_id: UUID | None = None, causation_id: UUID | None = None,
                 actor_type: str = "user") -> DomainEvent:
    event = DomainEvent(
        event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        correlation_id=correlation_id or uuid4(), causation_id=causation_id, actor_type=actor_type,
        actor_id=str(context.user_id), organization_id=context.organization_id, payload=payload,
        idempotency_key=idempotency_key, occurred_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.flush()
    session.add(OutboxMessage(event_id=event.id, topic=event_type, payload=payload))
    return event


def replay_or_none(session: Session, command_type: str, idempotency_key: str | None) -> dict | None:
    if not idempotency_key:
        return None
    existing = session.scalar(select(CommandDeduplication).where(
        CommandDeduplication.command_type == command_type, CommandDeduplication.idempotency_key == idempotency_key))
    return existing.result if existing else None


def remember(session: Session, command_type: str, idempotency_key: str | None, result: dict) -> None:
    if idempotency_key:
        session.add(CommandDeduplication(command_type=command_type, idempotency_key=idempotency_key, result=result))
