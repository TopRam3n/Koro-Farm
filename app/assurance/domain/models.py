from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


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
