from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class ShipmentStatus(StrEnum):
    OPEN = "OPEN"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"


class Shipment(Base):
    __tablename__ = "shipments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    fulfilment_node_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment_nodes.id"), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus, native_enum=False), nullable=False, default=ShipmentStatus.OPEN)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ShipmentSublot(Base):
    __tablename__ = "shipment_sublots"
    __table_args__ = (UniqueConstraint("shipment_id", "received_sublot_id", name="uq_shipment_sublot"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id"), nullable=False, index=True)
    received_sublot_id: Mapped[UUID] = mapped_column(ForeignKey("received_sublots.id"), nullable=False, unique=True)
    accepted_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (CheckConstraint("delivered_quantity_kg >= 0", name="ck_delivery_non_negative"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("shipments.id"), nullable=False, unique=True)
    delivered_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    buyer_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    buyer_confirmation_evidence: Mapped[str | None] = mapped_column(String(500))


class RequirementReconciliation(Base):
    __tablename__ = "requirement_reconciliations"
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), primary_key=True)
    committed_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    delivered_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    accepted_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_variance_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    accepted_fulfilment_rate_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    on_time: Mapped[bool | None] = mapped_column(Boolean)
    buyer_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dispute_status: Mapped[str | None] = mapped_column(String(80))
    verification_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
