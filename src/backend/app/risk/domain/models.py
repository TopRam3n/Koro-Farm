"""Immutable, explainable supply-plan risk indicators (not predictions)."""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class RiskLabel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    supply_plan_id: Mapped[UUID] = mapped_column(ForeignKey("supply_plans.id"), nullable=False, unique=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    committed_farmer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    standby_farmer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    committed_parish_count: Mapped[int] = mapped_column(Integer, nullable=False)
    standby_parish_count: Mapped[int] = mapped_column(Integer, nullable=False)
    largest_farmer_share_pct: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    largest_parish_share_pct: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    standby_coverage_pct: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    replacement_depth_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    average_availability_confidence: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    committed_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    standby_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    required_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    risk_label: Mapped[RiskLabel] = mapped_column(Enum(RiskLabel, native_enum=False), nullable=False)
    rules_triggered: Mapped[list] = mapped_column(JSON, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
