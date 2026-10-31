from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from src.backend.app.infrastructure.database.base import Base


class RecoveryStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"


class DomainEvent(Base):
    __tablename__ = "domain_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Filled from the aggregate's ownership chain on flush when the writer does not set it (see below).
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    causation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(String(300), nullable=True)


# Aggregate type -> tenancy resolver kind (identity/application/tenancy.py).
_EVENT_AGGREGATE_KINDS = {
    "requirement": "requirement", "buyer_requirements": "requirement", "buyer": "buyer",
    "production_lot": "lot", "production_lots": "lot", "farmer": "farmer", "farmers": "farmer",
    "allocation": "allocation", "shipment": "shipment",
}


@event.listens_for(Session, "before_flush")
def _attribute_event_organization(session: Session, _flush_context, _instances) -> None:
    from src.backend.app.identity.application.tenancy import organization_of
    for obj in session.new:
        if isinstance(obj, DomainEvent) and obj.organization_id is None:
            kind = _EVENT_AGGREGATE_KINDS.get(obj.aggregate_type)
            if kind is not None:
                with session.no_autoflush:
                    obj.organization_id = organization_of(session, kind, obj.aggregate_id)


class CommandDeduplication(Base):
    __tablename__ = "command_deduplications"
    __table_args__ = (UniqueConstraint("command_type", "idempotency_key", name="uq_command_idempotency"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    command_type: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecoveryRun(Base):
    __tablename__ = "recovery_runs"
    __table_args__ = (UniqueConstraint("requirement_id", "active_key", name="uq_active_recovery_per_requirement"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    status: Mapped[RecoveryStatus] = mapped_column(Enum(RecoveryStatus, native_enum=False), nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(10), nullable=True)  # RUNNING or null when terminal
    lost_quantity_kg: Mapped[object] = mapped_column(Numeric(12, 3), nullable=False)
    cause: Mapped[str] = mapped_column(String(200), nullable=False)
    standby_activated_kg: Mapped[object] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    new_supply_accepted_kg: Mapped[object] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    remaining_shortfall_kg: Mapped[object] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("domain_events.id"), nullable=False, unique=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Processing state for the exception worker (app/worker.py): PENDING -> PROCESSED, or DEAD after bounded retries.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkerHeartbeat(Base):
    """Liveness of each supply-exception worker process (app/worker.py), written on every tick."""
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_tick: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
