"""Consent to be contacted, notifications from outbox events, and dispatch (R1 WP5, M3).

Rules (WP5 M3 acceptance criteria):
* No message is queued, let alone sent, without a current GRANTED consent for the recipient covering the template's
  purpose. Without one the notification is recorded as BLOCKED_NO_CONSENT, so the gap is visible.
* Consent is checked again immediately before sending: a withdrawal stops messages already queued.
* Notifications come only from domain events in the transactional outbox, i.e. from actions people took or approved.
  Events written by the recovery agent itself (actor_type "agent") never produce a message: agent drafts reach a
  supplier only after the existing approval, as the gateway's execution events.
* A failed send is retried a bounded number of times, then marked FAILED; every status change is kept.
* Nothing leaves the system: the only providers are `none` and `synthetic` (providers.py).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.models import Organization
from src.backend.app.notifications.application.providers import NotificationProvider, OutboundMessage
from src.backend.app.notifications.application.templates import TEMPLATES
from src.backend.app.notifications.domain.models import (
    ConsentState, ContactChannel, ContactConsent, Notification, NotificationPurpose, NotificationStatus,
    NotificationStatusEvent, SubjectType,
)
from src.backend.app.reconciliation.domain.models import Shipment
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import SupplyAllocation

MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 60
EVENT_TEMPLATES = {
    "solicitation.sent": "SUPPLIER_REQUEST",
    "solicitation.reminder_due": "SUPPLIER_REMINDER",
    "solicitation.deadline_changed": "SUPPLIER_DEADLINE_CHANGED",
    "supplier.release_agreed": "RELEASE_AGREEMENT_RECORDED",
    "delivery.recorded": "BUYER_DELIVERY_RECORDED",
}


class ConsentError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def mask(address: str) -> str:
    """Enough to recognise an address, not enough to use it: +1876•••4567, ab•••@example.org."""
    if "@" in address:
        local, _, domain = address.partition("@")
        return f"{local[:2]}•••@{domain}"
    return f"{address[:5]}•••{address[-4:]}" if len(address) > 9 else "•••"


def _subject_in_organization(session: Session, organization_id: UUID, subject_type: str, subject_id: UUID) -> bool:
    model = Farmer if subject_type == SubjectType.FARMER else Buyer
    return session.scalar(select(model.id).where(model.id == subject_id, model.organization_id == organization_id)) is not None


def current_consent(session: Session, organization_id: UUID, subject_type: str, subject_id: UUID,
                    channel: str) -> ContactConsent | None:
    """The newest consent row for (subject, channel): the one no later row supersedes (timestamps can tie)."""
    scope = (ContactConsent.organization_id == organization_id, ContactConsent.subject_type == subject_type,
             ContactConsent.subject_id == subject_id, ContactConsent.channel == channel)
    superseded = select(ContactConsent.supersedes_id).where(*scope, ContactConsent.supersedes_id.is_not(None))
    return session.scalar(select(ContactConsent).where(*scope, ContactConsent.id.not_in(superseded))
                          .order_by(ContactConsent.created_at.desc(), ContactConsent.id.desc()).limit(1))


def usable_consent(session: Session, organization_id: UUID, subject_type: str, subject_id: UUID,
                   purpose: str) -> ContactConsent | None:
    """The first channel (SMS, WhatsApp, email) whose current consent is GRANTED for this purpose."""
    for channel in ContactChannel:
        consent = current_consent(session, organization_id, subject_type, subject_id, channel.value)
        if consent is not None and consent.state == ConsentState.GRANTED and purpose in (consent.purposes or []):
            return consent
    return None


def record_consent(session: Session, context: AuthorizationContext, subject_type: str, subject_id: UUID, *,
                   channel: str, address: str, granted: bool, purposes: list[str], wording_version: str,
                   how_given: str, evidence_reference: str | None) -> ContactConsent:
    from src.backend.app.assurance.application.events import record_event
    if not _subject_in_organization(session, context.organization_id, subject_type, subject_id):
        raise ConsentError(f"{subject_type.lower()} not found", 404)
    unknown = set(purposes) - {p.value for p in NotificationPurpose}
    if unknown:
        raise ConsentError(f"unknown purposes: {sorted(unknown)}")
    if granted and not purposes:
        raise ConsentError("say what the person agreed to be contacted about")
    previous = current_consent(session, context.organization_id, subject_type, subject_id, channel)
    consent = ContactConsent(
        organization_id=context.organization_id, subject_type=subject_type, subject_id=subject_id, channel=channel,
        address=address.strip(), state=ConsentState.GRANTED if granted else ConsentState.WITHDRAWN,
        purposes=sorted(set(purposes)) if granted else [], wording_version=wording_version.strip(),
        how_given=how_given.strip(), evidence_reference=evidence_reference, recorded_by_user_id=context.user_id,
        supersedes_id=previous.id if previous else None, created_at=_now())
    session.add(consent)
    session.flush()
    aggregate = "farmer" if subject_type == SubjectType.FARMER else "buyer"
    record_event(session, context, "contact_consent.recorded", aggregate, subject_id, {
        "consent_id": str(consent.id), "channel": channel, "state": consent.state, "purposes": consent.purposes,
        "wording_version": consent.wording_version})  # the address stays out of the event stream
    return consent


def consent_view(consent: ContactConsent) -> dict:
    return {"id": str(consent.id), "subject_type": consent.subject_type, "subject_id": str(consent.subject_id),
            "channel": consent.channel, "address": mask(consent.address), "state": consent.state,
            "purposes": consent.purposes, "wording_version": consent.wording_version, "how_given": consent.how_given,
            "evidence_reference": consent.evidence_reference, "supersedes_id": str(consent.supersedes_id) if consent.supersedes_id else None,
            "recorded_by_user_id": str(consent.recorded_by_user_id), "created_at": consent.created_at}


def _now() -> datetime:
    """Status events carry Python's microsecond clock: the database default can tie within one second (SQLite)."""
    return datetime.now(timezone.utc)


def _status(session: Session, notification: Notification, status: str, detail: str | None = None,
            provider: str | None = None) -> None:
    notification.status = status
    session.add(NotificationStatusEvent(notification_id=notification.id, status=status, detail=detail, provider=provider,
                                        created_at=_now()))


def _quantity(value) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _crop(requirement: Requirement) -> str:
    crop = requirement.crop.value if hasattr(requirement.crop, "value") else str(requirement.crop)
    return crop.replace("_", " ").lower()


def _due(value: str | None) -> str:
    if not value:
        return "the date your coordinator gave"
    moment = datetime.fromisoformat(value)
    jamaica = moment.astimezone(timezone(timedelta(hours=-5)))
    return jamaica.strftime("%d %b %Y, %I:%M %p")


def _recipients(session: Session, event: DomainEvent) -> list[tuple[str, UUID, UUID | None, dict]]:
    """(recipient type, recipient id, requirement id, template values) for the event's notification."""
    payload = event.payload or {}
    if event.event_type == "delivery.recorded":
        requirement = session.get(Requirement, event.aggregate_id)
        shipment = session.get(Shipment, UUID(payload["shipment_id"])) if payload.get("shipment_id") else None
        if requirement is None:
            return []
        return [(SubjectType.BUYER, requirement.buyer_id, requirement.id, {
            "quantity_kg": _quantity(payload.get("delivered_quantity_kg", "0")), "crop": _crop(requirement),
            "reference": shipment.reference if shipment else "unknown"})]
    allocation = session.get(SupplyAllocation, UUID(payload["allocation_id"])) if payload.get("allocation_id") else None
    if allocation is None:
        return []
    lot = session.get(ProductionLot, allocation.production_lot_id)
    requirement = session.get(Requirement, allocation.requirement_id)
    quantity = payload.get("quantity_kg") or allocation.quantity_kg
    return [(SubjectType.FARMER, lot.farmer_id, requirement.id, {
        "quantity_kg": _quantity(quantity), "crop": _crop(requirement), "due": _due(payload.get("response_due_at"))})]


def on_event(session: Session, message: OutboxMessage) -> list[Notification]:
    """Outbox hook: record the notification an event calls for. Idempotent per (event, template, recipient)."""
    template_key = EVENT_TEMPLATES.get(message.topic)
    if template_key is None:
        return []
    event = session.get(DomainEvent, message.event_id)
    if event is None or event.organization_id is None or event.actor_type == "agent":
        return []
    template = TEMPLATES[template_key]
    organization = session.get(Organization, event.organization_id)
    created = []
    for recipient_type, recipient_id, requirement_id, values in _recipients(session, event):
        exists = session.scalar(select(Notification.id).where(
            Notification.source_event_id == event.id, Notification.template_key == template.key,
            Notification.recipient_type == recipient_type, Notification.recipient_id == recipient_id))
        if exists is not None:
            continue
        consent = usable_consent(session, event.organization_id, recipient_type, recipient_id, template.purpose.value)
        notification = Notification(
            organization_id=event.organization_id, source_event_id=event.id, requirement_id=requirement_id,
            template_key=template.key, template_version=template.version, purpose=template.purpose.value,
            recipient_type=recipient_type, recipient_id=recipient_id, channel=consent.channel if consent else None,
            consent_id=consent.id if consent else None, body=template.render({"organization": organization.name, **values}),
            status=NotificationStatus.QUEUED, next_attempt_at=datetime.now(timezone.utc))
        session.add(notification)
        session.flush()
        if consent is None:
            _status(session, notification, NotificationStatus.BLOCKED_NO_CONSENT,
                    f"no current consent covering {template.purpose.value}")
        else:
            _status(session, notification, NotificationStatus.QUEUED, f"consent {consent.id} via {consent.channel}")
        created.append(notification)
    return created


def dispatch_due(session: Session, provider: NotificationProvider, now: datetime | None = None, limit: int = 50) -> dict:
    """Send queued notifications that are due. Consent is re-checked; the address comes from the current consent."""
    now = now or datetime.now(timezone.utc)
    counts = {"sent": 0, "failed": 0, "blocked": 0, "not_sent": 0, "retrying": 0}
    due = session.scalars(select(Notification).where(
        Notification.status == NotificationStatus.QUEUED,
        (Notification.next_attempt_at.is_(None)) | (Notification.next_attempt_at <= now))
        .order_by(Notification.created_at, Notification.id).limit(limit).with_for_update(skip_locked=True)).all()
    for notification in due:
        consent = usable_consent(session, notification.organization_id, notification.recipient_type,
                                 notification.recipient_id, notification.purpose)
        if consent is None:
            _status(session, notification, NotificationStatus.BLOCKED_NO_CONSENT, "consent withdrawn or changed before sending")
            counts["blocked"] += 1
            continue
        notification.channel, notification.consent_id = consent.channel, consent.id
        notification.attempts += 1
        notification.provider = provider.name
        result = provider.send(OutboundMessage(str(notification.id), consent.channel, consent.address, notification.body))
        if result.accepted:
            notification.provider_message_id, notification.sent_at, notification.last_error = result.provider_message_id, now, None
            _status(session, notification, NotificationStatus.SENT, f"accepted by {provider.name}", provider.name)
            counts["sent"] += 1
        elif not provider.sends and result.permanent:
            _status(session, notification, NotificationStatus.NOT_SENT_PROVIDER_DISABLED, result.error, provider.name)
            counts["not_sent"] += 1
        elif result.permanent or notification.attempts >= MAX_ATTEMPTS:
            notification.last_error = result.error
            _status(session, notification, NotificationStatus.FAILED, result.error, provider.name)
            counts["failed"] += 1
        else:
            notification.last_error = result.error
            notification.next_attempt_at = now + timedelta(seconds=RETRY_BASE_SECONDS * 2 ** (notification.attempts - 1))
            session.add(NotificationStatusEvent(notification_id=notification.id, status="RETRY_SCHEDULED",
                                                detail=result.error, provider=provider.name, created_at=_now()))
            counts["retrying"] += 1
    return counts


def notification_view(session: Session, notification: Notification, with_history: bool = False) -> dict:
    model = Farmer if notification.recipient_type == SubjectType.FARMER else Buyer
    recipient = session.get(model, notification.recipient_id)
    consent = session.get(ContactConsent, notification.consent_id) if notification.consent_id else None
    view = {"id": str(notification.id), "template_key": notification.template_key, "template_version": notification.template_version,
            "purpose": notification.purpose, "recipient_type": notification.recipient_type,
            "recipient_id": str(notification.recipient_id), "recipient_name": recipient.name if recipient else None,
            "channel": notification.channel, "address": mask(consent.address) if consent else None,
            "requirement_id": str(notification.requirement_id) if notification.requirement_id else None,
            "body": notification.body, "status": notification.status, "provider": notification.provider,
            "attempts": notification.attempts, "last_error": notification.last_error, "sent_at": notification.sent_at,
            "created_at": notification.created_at}
    if with_history:
        view["history"] = [{"status": e.status, "detail": e.detail, "provider": e.provider, "created_at": e.created_at}
                           for e in session.scalars(select(NotificationStatusEvent).where(
                               NotificationStatusEvent.notification_id == notification.id)
                               .order_by(NotificationStatusEvent.created_at, NotificationStatusEvent.id))]
    return view
