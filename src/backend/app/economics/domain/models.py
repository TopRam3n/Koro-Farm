from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class LotCostInput(Base):
    """Current planning inputs. Historical results belong in CostSnapshot."""

    __tablename__ = "lot_cost_inputs"
    __table_args__ = (
        CheckConstraint("farmgate_price_per_kg_jmd >= 0", name="ck_cost_farmgate_non_negative"),
        CheckConstraint("pickup_cost_jmd >= 0", name="ck_cost_pickup_non_negative"),
        CheckConstraint("handling_grading_cost_per_kg_jmd >= 0", name="ck_cost_handling_non_negative"),
        CheckConstraint("packaging_cost_per_kg_jmd >= 0", name="ck_cost_packaging_non_negative"),
        CheckConstraint("transport_cost_jmd >= 0", name="ck_cost_transport_non_negative"),
        CheckConstraint("expected_rejection_pct >= 0 AND expected_rejection_pct <= 1", name="ck_cost_rejection_pct"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_lot_id: Mapped[UUID] = mapped_column(ForeignKey("production_lots.id"), nullable=False, unique=True)
    farmgate_price_per_kg_jmd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    pickup_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    handling_grading_cost_per_kg_jmd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    packaging_cost_per_kg_jmd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transport_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expected_rejection_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CostSnapshot(Base):
    __tablename__ = "cost_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    supply_plan_id: Mapped[UUID] = mapped_column(ForeignKey("supply_plans.id"), nullable=False, unique=True)
    produce_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    pickup_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    handling_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    packaging_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    transport_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    expected_rejection_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_landed_cost_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    landed_cost_per_kg_jmd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
