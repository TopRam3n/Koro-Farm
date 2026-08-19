from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.common import Crop, DateWindow, Grade, QuantityKg
from app.infrastructure.database.base import Base


class RequirementLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    IN_FULFILMENT = "IN_FULFILMENT"
    RECONCILED = "RECONCILED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class SupplyHealth(StrEnum):
    UNPLANNED = "UNPLANNED"
    COVERED = "COVERED"
    AT_RISK = "AT_RISK"
    RECOVERING = "RECOVERING"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    buyer_type: Mapped[str] = mapped_column(String(80), nullable=False)
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (CheckConstraint("required_quantity_kg > 0", name="ck_requirement_quantity_positive"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(ForeignKey("buyers.id"), nullable=False, index=True)
    crop: Mapped[Crop] = mapped_column(Enum(Crop, native_enum=False), nullable=False)
    grade: Mapped[Grade] = mapped_column(Enum(Grade, native_enum=False), nullable=False)
    required_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    delivery_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    lifecycle_status: Mapped[RequirementLifecycleStatus] = mapped_column(
        Enum(RequirementLifecycleStatus, native_enum=False), default=RequirementLifecycleStatus.DRAFT, nullable=False
    )
    supply_health: Mapped[SupplyHealth] = mapped_column(
        Enum(SupplyHealth, native_enum=False), default=SupplyHealth.UNPLANNED, nullable=False
    )
    plan_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def validate(self) -> None:
        QuantityKg(self.required_quantity_kg)
        if self.required_quantity_kg <= 0:
            raise ValueError("required quantity must be greater than zero")
        DateWindow(self.delivery_window_start, self.delivery_window_end)
