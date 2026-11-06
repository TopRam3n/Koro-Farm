"""Evidence-linked receipts against accepted marketplace farmer offers.

Do not mingle this ledger with legacy ReceivedSublot(SupplyAllocation).
A future reconciliation migration may explicitly bridge them, with no double counting.
"""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.common import Grade
from app.infrastructure.database.base import Base


class MarketplaceInspectionStatus(StrEnum):
    PENDING_INSPECTION = "PENDING_INSPECTION"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"


class MarketplaceReceipt(Base):
    __tablename__ = "marketplace_receipts"
    __table_args__ = (
        CheckConstraint("received_quantity_kg > 0", name="ck_marketplace_receipt_positive"),
        CheckConstraint("accepted_quantity_kg >= 0", name="ck_marketplace_receipt_accepted_nonnegative"),
        CheckConstraint("rejected_quantity_kg >= 0", name="ck_marketplace_receipt_rejected_nonnegative"),
        CheckConstraint("accepted_quantity_kg + rejected_quantity_kg <= received_quantity_kg", name="ck_marketplace_receipt_graded_within_received"),
        UniqueConstraint("organization_id", "receipt_key", name="uq_marketplace_receipt_command"),
        UniqueConstraint("organization_id", "inspection_key", name="uq_marketplace_inspection_command"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    offer_id: Mapped[UUID] = mapped_column(ForeignKey("farmer_offers.id"), nullable=False, index=True)
    fulfilment_node_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment_nodes.id"), nullable=False, index=True)
    received_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    receipt_evidence_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    receipt_key: Mapped[str] = mapped_column(String(150), nullable=False)
    received_by: Mapped[UUID] = mapped_column(nullable=False)
    inspection_status: Mapped[MarketplaceInspectionStatus] = mapped_column(
        Enum(MarketplaceInspectionStatus, native_enum=False), nullable=False,
        default=MarketplaceInspectionStatus.PENDING_INSPECTION,
    )
    accepted_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    rejected_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    assigned_grade: Mapped[Grade | None] = mapped_column(Enum(Grade, native_enum=False), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inspection_evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    inspection_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    inspected_by: Mapped[UUID | None] = mapped_column(nullable=True)
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
