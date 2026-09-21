from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class SourceChannel(StrEnum):
    PORTAL = "PORTAL"
    SECURE_LINK = "SECURE_LINK"
    COORDINATOR_ENTRY = "COORDINATOR_ENTRY"
    PHONE = "PHONE"
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    CSV_IMPORT = "CSV_IMPORT"
    API = "API"
    WAREHOUSE = "WAREHOUSE"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    SENSOR = "SENSOR"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    SELF_REPORTED = "SELF_REPORTED"
    COORDINATOR_CONFIRMED = "COORDINATOR_CONFIRMED"
    WAREHOUSE_VERIFIED = "WAREHOUSE_VERIFIED"
    BUYER_CONFIRMED = "BUYER_CONFIRMED"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    VERIFIED_SOURCE = "VERIFIED_SOURCE"


class FreshnessStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


class IngestionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


class SecureActionPurpose(StrEnum):
    CONFIRM_QUANTITY = "CONFIRM_QUANTITY"
    CHANGE_AVAILABLE_QUANTITY = "CHANGE_AVAILABLE_QUANTITY"
    CONFIRM_HARVEST_DATE = "CONFIRM_HARVEST_DATE"
    AUTHORIZE_STANDBY = "AUTHORIZE_STANDBY"
    DECLINE_STANDBY = "DECLINE_STANDBY"
    CONFIRM_PICKUP_READINESS = "CONFIRM_PICKUP_READINESS"
    DECLINE = "DECLINE"


class IngestionRecord(Base):
    __tablename__ = "ingestion_records"
    __table_args__ = (UniqueConstraint("organization_id", "channel", "external_reference",
                                       name="uq_ingestion_external_reference"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    channel: Mapped[SourceChannel] = mapped_column(Enum(SourceChannel, native_enum=False), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    farmer_id: Mapped[UUID | None] = mapped_column(ForeignKey("farmers.id"))
    target_entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_entity_id: Mapped[UUID | None] = mapped_column(index=True)
    payload_schema: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_version: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_result: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[IngestionStatus] = mapped_column(Enum(IngestionStatus, native_enum=False), nullable=False)
    domain_command: Mapped[str | None] = mapped_column(String(120))
    resulting_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("domain_events.id"))
    correlation_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OperationalObservation(Base):
    __tablename__ = "operational_observations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    ingestion_record_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_records.id"), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_entity_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_actor: Mapped[str] = mapped_column(String(200), nullable=False)
    source_channel: Mapped[SourceChannel] = mapped_column(Enum(SourceChannel, native_enum=False), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False), nullable=False
    )
    verification_method: Mapped[str | None] = mapped_column(String(200))
    freshness_status: Mapped[FreshnessStatus] = mapped_column(Enum(FreshnessStatus, native_enum=False), nullable=False)
    freshness_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supporting_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SecureActionLink(Base):
    __tablename__ = "secure_action_links"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False, index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[SecureActionPurpose] = mapped_column(Enum(SecureActionPurpose, native_enum=False), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_entity_id: Mapped[UUID] = mapped_column(nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    farmer_id: Mapped[UUID] = mapped_column(ForeignKey("farmers.id"), nullable=False)
    secure_action_link_id: Mapped[UUID | None] = mapped_column(ForeignKey("secure_action_links.id"))
    intent: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[SourceChannel] = mapped_column(Enum(SourceChannel, native_enum=False), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(200))
    delivery_state: Mapped[str] = mapped_column(String(40), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
