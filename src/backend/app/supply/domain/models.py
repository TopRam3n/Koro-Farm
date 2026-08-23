from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.domain.common import AvailabilityConfidence, Crop, DateWindow, Grade, QuantityKg
from src.backend.app.infrastructure.database.base import Base


class ProductionLotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    EXHAUSTED = "EXHAUSTED"


class Farmer(Base):
    __tablename__ = "farmers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parish: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProductionLot(Base):
    __tablename__ = "production_lots"
    __table_args__ = (
        CheckConstraint("expected_quantity_kg >= 0", name="ck_lot_expected_non_negative"),
        CheckConstraint("available_quantity_kg >= 0", name="ck_lot_available_non_negative"),
        CheckConstraint("reserved_quantity_kg >= 0", name="ck_lot_reserved_non_negative"),
        CheckConstraint("reserved_quantity_kg <= available_quantity_kg", name="ck_lot_reserved_within_available"),
        CheckConstraint("harvest_end >= harvest_start", name="ck_lot_valid_harvest_window"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False, index=True)
    crop: Mapped[Crop] = mapped_column(Enum(Crop, native_enum=False), nullable=False)
    harvest_start: Mapped[date] = mapped_column(Date, nullable=False)
    harvest_end: Mapped[date] = mapped_column(Date, nullable=False)
    expected_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    available_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reserved_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"), nullable=False)
    quality_grade_estimate: Mapped[Grade] = mapped_column(Enum(Grade, native_enum=False), nullable=False)
    availability_confidence: Mapped[AvailabilityConfidence] = mapped_column(
        Enum(AvailabilityConfidence, native_enum=False), nullable=False
    )
    parish: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ProductionLotStatus] = mapped_column(
        Enum(ProductionLotStatus, native_enum=False), default=ProductionLotStatus.AVAILABLE, nullable=False
    )
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def validate(self) -> None:
        QuantityKg(self.expected_quantity_kg)
        QuantityKg(self.available_quantity_kg)
        QuantityKg(self.reserved_quantity_kg)
        if self.reserved_quantity_kg > self.available_quantity_kg:
            raise ValueError("reserved quantity cannot exceed verified available quantity")
        DateWindow(self.harvest_start, self.harvest_end)
