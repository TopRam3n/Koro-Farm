"""Read-only agricultural profile and historical production data.

These records are NOT available supply and must never feed supply allocations.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Farm(Base):
    __tablename__ = "farms"
    __table_args__ = (UniqueConstraint("farmer_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parish: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FarmerCrop(Base):
    __tablename__ = "farmer_crops"
    __table_args__ = (UniqueConstraint("farmer_id", "crop"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False)
    crop: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HistoricalProduction(Base):
    __tablename__ = "historical_production"
    __table_args__ = (
        CheckConstraint("production_year BETWEEN 2000 AND 2100", name="valid_production_year"),
        CheckConstraint("production_quarter BETWEEN 1 AND 4", name="valid_production_quarter"),
        CheckConstraint("production_kg >= 0", name="valid_production_quantity"),
        UniqueConstraint("farmer_id", "crop", "production_year", "production_quarter", "data_source"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False)
    crop: Mapped[str] = mapped_column(String(100), nullable=False)
    production_year: Mapped[int] = mapped_column(Integer, nullable=False)
    production_quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    production_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    data_source: Mapped[str] = mapped_column(String(100), nullable=False, server_default="KOROFARM_DEMO")
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
