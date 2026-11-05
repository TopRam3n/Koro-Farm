"""Outbound notifications and consent to be contacted (R1 WP5, M3).

Provider-independent. Nothing here talks to an SMS, WhatsApp or email service: the providers in
notifications/application/providers.py are a disabled one (the default) and a synthetic one that only records.

* ContactConsent: a person's recorded agreement (or withdrawal) to be contacted on one channel and address, for named
  purposes, with the wording version they agreed to and how it was given. Append-only: a change adds a row that
  supersedes the previous one; the current state is the newest row for (subject, channel).
* Notification: one message for one recipient, created from a domain event in the transactional outbox. It records
  the template and version, the rendered text and its status. The address is not stored here: it is read from the
  current consent at send time, so a withdrawn or changed consent applies to messages still waiting.
* NotificationStatusEvent: every status change with its detail. Append-only.
"""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class ContactChannel(StrEnum):
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"


class SubjectType(StrEnum):
    FARMER = "FARMER"
    BUYER = "BUYER"


class ConsentState(StrEnum):
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"


class NotificationPurpose(StrEnum):
    SUPPLY_REQUESTS = "SUPPLY_REQUESTS"    # requests, reminders, deadline changes
    RELEASE_AGREEMENTS = "RELEASE_AGREEMENTS"
    DELIVERY_UPDATES = "DELIVERY_UPDATES"  # buyers: a delivery was recorded and awaits their confirmation


class NotificationStatus(StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"                          # accepted by the provider
    DELIVERED = "DELIVERED"                # provider reported delivery (none of the current providers do)
    FAILED = "FAILED"                      # gave up after bounded retries, or the provider refused it permanently
    BLOCKED_NO_CONSENT = "BLOCKED_NO_CONSENT"
    NOT_SENT_PROVIDER_DISABLED = "NOT_SENT_PROVIDER_DISABLED"


class ContactConsent(Base):
    __tablename__ = "contact_consents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(String(320), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    purposes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    wording_version: Mapped[str] = mapped_column(String(40), nullable=False)
    how_given: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("contact_consents.id"), nullable=True)
    recorded_by_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("source_event_id", "template_key", "recipient_type", "recipient_id",
                                       name="uq_notification_per_event_recipient"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    source_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("domain_events.id"), nullable=True, index=True)
    requirement_id: Mapped[UUID | None] = mapped_column(ForeignKey("requirements.id"), nullable=True, index=True)
    template_key: Mapped[str] = mapped_column(String(60), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_id: Mapped[UUID] = mapped_column(nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consent_id: Mapped[UUID | None] = mapped_column(ForeignKey("contact_consents.id"), nullable=True)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
                                                 nullable=False)


class NotificationStatusEvent(Base):
    __tablename__ = "notification_status_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(ForeignKey("notifications.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
