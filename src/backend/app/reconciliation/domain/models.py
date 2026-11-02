from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class ShipmentStatus(StrEnum):
    OPEN = "OPEN"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"  # an open shipment abandoned before dispatch, with a reason


class Shipment(Base):
    __tablename__ = "shipments"
    # References are unique per fulfilment site (and so per organization), never across tenants.
    __table_args__ = (UniqueConstraint("fulfilment_node_id", "reference", name="uq_shipment_site_reference"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    fulfilment_node_id: Mapped[UUID] = mapped_column(ForeignKey("fulfilment_nodes.id"), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus, native_enum=False), nullable=False, default=ShipmentStatus.OPEN)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
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
    # Legacy (before WP4): a yes/no flag with no quantity. Buyer confirmation is now a BuyerConfirmation record.
    buyer_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    buyer_confirmation_evidence: Mapped[str | None] = mapped_column(String(500))
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)


class DeliveryAdjustment(Base):
    """A correction to a recorded delivery quantity. The delivery itself is never edited."""
    __tablename__ = "delivery_adjustments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("deliveries.id"), nullable=False, index=True)
    delta_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    recorded_by_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConfirmationChannel(StrEnum):
    BUYER_ACCOUNT = "BUYER_ACCOUNT"              # the authenticated buyer confirmed in their own account
    STAFF_RELAYED = "STAFF_RELAYED"              # staff recorded what the buyer's representative said elsewhere, attested
    LEGACY_UNQUANTIFIED = "LEGACY_UNQUANTIFIED"  # migrated yes/no flag from before WP4; not quantified confirmation


class ConfirmationOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"      # the buyer confirms receiving confirmed_quantity_kg
    DISCREPANCY = "DISCREPANCY"  # the buyer reports a difference; confirmed_quantity_kg is what they accept receiving


class BuyerConfirmation(Base):
    """The buyer's statement about one delivery. Immutable; a later statement supersedes an earlier one."""
    __tablename__ = "buyer_confirmations"
    __table_args__ = (CheckConstraint("confirmed_quantity_kg >= 0", name="ck_confirmation_non_negative"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("deliveries.id"), nullable=False, index=True)
    confirmed_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    outcome: Mapped[ConfirmationOutcome] = mapped_column(Enum(ConfirmationOutcome, native_enum=False, length=20), nullable=False)
    channel: Mapped[ConfirmationChannel] = mapped_column(Enum(ConfirmationChannel, native_enum=False, length=30), nullable=False)
    buyer_representative: Mapped[str | None] = mapped_column(String(200))   # required for STAFF_RELAYED
    communication_channel: Mapped[str | None] = mapped_column(String(100))  # required for STAFF_RELAYED
    attestation: Mapped[str | None] = mapped_column(String(300))            # required for STAFF_RELAYED
    stated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # when the buyer said it
    note: Mapped[str | None] = mapped_column(String(1000))
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("buyer_confirmations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RequirementReconciliation(Base):
    """Legacy (before WP4): one mutable row per order. Read-only now; migrated to ReconciliationRecord version 1."""
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


class ReconciliationRecord(Base):
    """A versioned, immutable comparison of contractual, physical and buyer-confirmed quantities (P6, P11).

    A correction is a new version naming the version it supersedes, with a reason. A material correction (one that
    changes commercial or farmer-performance figures) stays PENDING_REVIEW until a second, different person with
    trade.reconcile approves it; until then the previous version stays effective.
    """
    __tablename__ = "reconciliation_records"
    __table_args__ = (UniqueConstraint("requirement_id", "version", name="uq_reconciliation_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("reconciliation_records.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # EFFECTIVE | PENDING_REVIEW | SUPERSEDED
    figures: Mapped[dict] = mapped_column(JSON, nullable=False)
    variances: Mapped[dict] = mapped_column(JSON, nullable=False)
    basis: Mapped[dict] = mapped_column(JSON, nullable=False)        # ids of receipts, shipments, deliveries, confirmations
    reason: Mapped[str | None] = mapped_column(String(500))          # required from version 2
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    material_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Dispute(Base):
    """A discrepancy raised by the buyer or by authorized staff. Never edited; its outcome is a DisputeResolution."""
    __tablename__ = "disputes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    delivery_id: Mapped[UUID | None] = mapped_column(ForeignKey("deliveries.id"), nullable=True)
    raised_by_user_id: Mapped[UUID] = mapped_column(nullable=False)
    raised_by_party: Mapped[str] = mapped_column(String(20), nullable=False)  # BUYER | STAFF
    quantity_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DisputeResolution(Base):
    __tablename__ = "dispute_resolutions"
    __table_args__ = (UniqueConstraint("dispute_id", name="uq_dispute_resolution_once"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    dispute_id: Mapped[UUID] = mapped_column(ForeignKey("disputes.id"), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # RESOLVED | WITHDRAWN
    resolution: Mapped[str] = mapped_column(String(1000), nullable=False)
    resolved_by_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditFlag(Base):
    """An auditor's note about an order or record. Separate from disputes; changes nothing operational."""
    __tablename__ = "audit_flags"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID | None] = mapped_column(ForeignKey("requirements.id"), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False)
    raised_by_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StockLedgerFinding(Base):
    """A lot whose reserved quantity does not match what holds reservations on it (supply/application/ledger.py).
    Never auto-corrected; resolved only when a later check finds the lot balanced again."""
    __tablename__ = "stock_ledger_findings"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    production_lot_id: Mapped[UUID] = mapped_column(ForeignKey("production_lots.id"), nullable=False, index=True)
    recorded_reserved_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    expected_reserved_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    difference_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
