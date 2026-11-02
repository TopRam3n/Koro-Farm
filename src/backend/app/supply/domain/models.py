from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.domain.common import AvailabilityConfidence, Crop, DateWindow, Grade, QuantityKg
from src.backend.app.domain.common import CropCode
from src.backend.app.domain.common.types import CropCodeType
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.identity.domain.models import DEFAULT_ORGANIZATION_ID


class ProductionLotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    EXHAUSTED = "EXHAUSTED"


class Farmer(Base):
    __tablename__ = "farmers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, default=DEFAULT_ORGANIZATION_ID, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parish: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CapacityVerification(StrEnum):
    """How the lot's capacity is known. UNSPECIFIED marks records created before this was captured."""
    DECLARED = "DECLARED"
    VERIFIED = "VERIFIED"
    UNSPECIFIED = "UNSPECIFIED"


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
    crop: Mapped[CropCode] = mapped_column(CropCodeType(), nullable=False)
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
    capacity_verification: Mapped[CapacityVerification] = mapped_column(
        Enum(CapacityVerification, native_enum=False, length=20), nullable=False,
        default=CapacityVerification.UNSPECIFIED, server_default=CapacityVerification.UNSPECIFIED.value)
    provenance_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attestation_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Latest supplier-reported capacity (supply/application/capacity.py). Kept apart from reserved stock so a
    # reduction never silently cancels commitments; NULL means no capacity report has been received.
    reported_capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    capacity_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Excluded from new planning until usable capacity is confirmed again (after a release, or a harvest window
    # that ended without a current confirmation). Cleared by a capacity report or a new declaration.
    reverification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    reverification_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    reverification_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Verified physical limits: produce not usable after viable_until; withdrawn stock is never planned again.
    viable_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
