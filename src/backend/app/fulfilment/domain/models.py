from datetime import datetime
from uuid import UUID, uuid4

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base
from src.backend.app.domain.common import Grade


class FulfilmentNode(Base):
    __tablename__ = "fulfilment_nodes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    node_type: Mapped[str] = mapped_column(String(80), nullable=False)
    parish: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InspectionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PENDING_INSPECTION = "PENDING_INSPECTION"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"


class ReceivedSublot(Base):
    __tablename__ = "received_sublots"
    __table_args__ = (
        CheckConstraint("received_quantity_kg >= 0", name="ck_sublot_received_non_negative"),
        CheckConstraint("accepted_quantity_kg >= 0", name="ck_sublot_accepted_non_negative"),
        CheckConstraint("rejected_quantity_kg >= 0", name="ck_sublot_rejected_non_negative"),
        CheckConstraint("accepted_quantity_kg + rejected_quantity_kg <= received_quantity_kg", name="ck_sublot_accounted_within_received"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    allocation_id: Mapped[UUID] = mapped_column(ForeignKey("supply_allocations.id"), nullable=False, index=True)
    fulfilment_node_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment_nodes.id"), nullable=False, index=True)
    received_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    accepted_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    rejected_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    assigned_grade: Mapped[Grade | None] = mapped_column(Enum(Grade, native_enum=False), nullable=True)
    inspection_status: Mapped[InspectionStatus] = mapped_column(Enum(InspectionStatus, native_enum=False), nullable=False, default=InspectionStatus.PENDING_INSPECTION)
    rejection_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    inspection_evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
