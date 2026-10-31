from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class CapacityChannel(StrEnum):
    """FARMER_PORTAL: the farmer reported it while signed in. COORDINATOR_RELAYED: a coordinator recorded what
    the farmer told them, with an attestation; that is not independent farmer confirmation."""
    FARMER_PORTAL = "FARMER_PORTAL"
    COORDINATOR_RELAYED = "COORDINATOR_RELAYED"


class CapacityVerification(StrEnum):
    SELF_REPORTED = "SELF_REPORTED"                # reported by the farmer themselves
    COORDINATOR_ATTESTED = "COORDINATOR_ATTESTED"  # relayed by a coordinator; not independently verified


class CapacityReport(Base):
    """Immutable record of a supplier capacity report. Never updated or deleted."""
    __tablename__ = "capacity_reports"
    __table_args__ = (CheckConstraint("reported_capacity_kg >= 0", name="ck_capacity_report_non_negative"),
                      CheckConstraint("delivered_at_report_kg >= 0", name="ck_capacity_report_delivered_non_negative"))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    production_lot_id: Mapped[UUID] = mapped_column(ForeignKey("production_lots.id"), nullable=False, index=True)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False)
    # What the supplier said they could still supply (excluding anything already delivered).
    reported_capacity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    # Received against the lot when the report was made; reported + delivered is the lot's capacity ceiling.
    delivered_at_report_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"),
                                                            server_default="0")
    # The lot's capacity ceiling before this report (delivered plus still to supply).
    previous_reported_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    committed_at_report_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    channel: Mapped[CapacityChannel] = mapped_column(Enum(CapacityChannel, native_enum=False, length=30), nullable=False)
    original_source: Mapped[str] = mapped_column(String(200), nullable=False)
    attestation_method: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[CapacityVerification] = mapped_column(
        Enum(CapacityVerification, native_enum=False, length=30), nullable=False)
    # False when a newer report already exists: a stale report is kept as history but changes nothing.
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
