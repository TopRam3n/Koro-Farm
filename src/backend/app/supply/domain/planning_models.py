from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class SupplyPlanStatus(StrEnum):
    FINALIZED = "FINALIZED"


class AllocationRole(StrEnum):
    COMMITTED = "COMMITTED"
    STANDBY = "STANDBY"


class AllocationStatus(StrEnum):
    PROPOSED = "PROPOSED"
    SOLICITED = "SOLICITED"
    ACCEPTED = "ACCEPTED"
    COMMITTED = "COMMITTED"
    STANDBY = "STANDBY"
    ACTIVATED = "ACTIVATED"
    LOST = "LOST"
    RELEASED = "RELEASED"
    CANCELLED = "CANCELLED"


class SupplyPlan(Base):
    __tablename__ = "supply_plans"
    __table_args__ = (
        CheckConstraint("required_quantity_kg > 0", name="ck_plan_required_positive"),
        CheckConstraint("committed_quantity_kg >= 0", name="ck_plan_committed_non_negative"),
        CheckConstraint("standby_quantity_kg >= 0", name="ck_plan_standby_non_negative"),
        CheckConstraint("unfilled_quantity_kg >= 0", name="ck_plan_unfilled_non_negative"),
        CheckConstraint("plan_version > 0", name="ck_plan_version_positive"),
        UniqueConstraint("requirement_id", "plan_version", name="uq_supply_plan_requirement_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    planner_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[SupplyPlanStatus] = mapped_column(Enum(SupplyPlanStatus, native_enum=False), nullable=False)
    required_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    committed_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    standby_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unfilled_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupplyAllocation(Base):
    __tablename__ = "supply_allocations"
    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_allocation_quantity_positive"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    supply_plan_id: Mapped[UUID] = mapped_column(ForeignKey("supply_plans.id"), nullable=False, index=True)
    production_lot_id: Mapped[UUID] = mapped_column(ForeignKey("production_lots.id"), nullable=False, index=True)
    role: Mapped[AllocationRole] = mapped_column(Enum(AllocationRole, native_enum=False), nullable=False)
    status: Mapped[AllocationStatus] = mapped_column(Enum(AllocationStatus, native_enum=False), nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    consent_evidence_id: Mapped[UUID | None] = mapped_column(nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
