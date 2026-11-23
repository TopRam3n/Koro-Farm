from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class ExceptionKind(StrEnum):
    CAPACITY_SHORTFALL = "CAPACITY_SHORTFALL"  # confirmed commitments exceed reported capacity
    RESPONSE_OVERDUE = "RESPONSE_OVERDUE"      # a supplier did not answer before the deadline
    STANDBY_EXPIRED = "STANDBY_EXPIRED"        # an expired authorization leaves an active recovery short


class ExceptionStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class SupplyException(Base):
    """An actionable supply exception opened by the deterministic detector (app/worker.py).

    The partial unique index on dedupe_key (OPEN rows only) means repeated or concurrent detection of the same
    condition updates one exception instead of opening duplicates.
    """
    __tablename__ = "supply_exceptions"
    __table_args__ = (
        CheckConstraint("shortfall_kg >= 0", name="ck_exception_shortfall_non_negative"),
        Index("uq_supply_exceptions_open_dedupe", "dedupe_key", unique=True,
              postgresql_where=text("status = 'OPEN'"), sqlite_where=text("status = 'OPEN'")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    kind: Mapped[ExceptionKind] = mapped_column(Enum(ExceptionKind, native_enum=False, length=40), nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(Enum(ExceptionStatus, native_enum=False, length=20), nullable=False,
                                                    default=ExceptionStatus.OPEN)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    shortfall_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_event_id: Mapped[UUID | None] = mapped_column(nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(500), nullable=True)
