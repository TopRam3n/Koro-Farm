"""Outbound notifications and consent to be contacted (R1 WP5, M3). Staff only; organization-scoped.

Addresses are always masked in responses. Recording consent needs the permission that manages the subject
(supply.manage for farmers, requirement.update for buyers); reading needs the matching view permission.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.notifications.application import service
from src.backend.app.notifications.domain.models import ContactChannel, ContactConsent, Notification, NotificationStatus, SubjectType

router = APIRouter(tags=["notifications"])


class ConsentCommand(BaseModel):
    channel: ContactChannel
    address: str = Field(min_length=3, max_length=320)
    granted: bool
    purposes: list[str] = Field(default_factory=list, max_length=10)
    wording_version: str = Field(min_length=1, max_length=40, description="The consent wording the person agreed to")
    how_given: str = Field(min_length=3, max_length=200, description="e.g. signed form, recorded phone call")
    evidence_reference: str | None = Field(default=None, max_length=500)


def _record(session: Session, context: AuthorizationContext, subject_type: SubjectType, subject_id: UUID,
            payload: ConsentCommand) -> dict:
    try:
        consent = service.record_consent(session, context, subject_type, subject_id, channel=payload.channel.value,
                                         address=payload.address, granted=payload.granted, purposes=payload.purposes,
                                         wording_version=payload.wording_version, how_given=payload.how_given,
                                         evidence_reference=payload.evidence_reference)
    except service.ConsentError as exc:
        session.rollback()
        raise HTTPException(exc.status, str(exc)) from exc
    session.commit()
    return service.consent_view(consent)


def _history(session: Session, context: AuthorizationContext, subject_type: SubjectType, subject_id: UUID) -> list[dict]:
    rows = session.scalars(select(ContactConsent).where(
        ContactConsent.organization_id == context.organization_id, ContactConsent.subject_type == subject_type,
        ContactConsent.subject_id == subject_id).order_by(ContactConsent.created_at.desc(), ContactConsent.id.desc())).all()
    return [service.consent_view(row) for row in _newest_first(rows)]


def _newest_first(rows: list[ContactConsent]) -> list[ContactConsent]:
    """Newest first per channel, following the supersedes chain so equal timestamps cannot reorder history."""
    successor = {row.supersedes_id: row for row in rows if row.supersedes_id is not None}
    ordered: list[ContactConsent] = []
    for head in [row for row in rows if row.id not in successor]:
        node = head
        while node is not None and node not in ordered:
            ordered.append(node)
            node = next((row for row in rows if row.id == node.supersedes_id), None)
    return ordered + [row for row in rows if row not in ordered]


@router.get("/farmers/{farmer_id}/contact-consents", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def farmer_consents(farmer_id: UUID, session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> list[dict]:
    return _history(session, context, SubjectType.FARMER, farmer_id)


@router.post("/farmers/{farmer_id}/contact-consents", status_code=201,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def record_farmer_consent(farmer_id: UUID, payload: ConsentCommand, session: Session = Depends(get_session),
                          context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _record(session, context, SubjectType.FARMER, farmer_id, payload)


@router.get("/buyers/{buyer_id}/contact-consents", dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_VIEW))])
def buyer_consents(buyer_id: UUID, session: Session = Depends(get_session),
                   context: AuthorizationContext = Depends(get_authorization_context)) -> list[dict]:
    return _history(session, context, SubjectType.BUYER, buyer_id)


@router.post("/buyers/{buyer_id}/contact-consents", status_code=201,
             dependencies=[Depends(require_permission(PermissionCode.REQUIREMENT_UPDATE))])
def record_buyer_consent(buyer_id: UUID, payload: ConsentCommand, session: Session = Depends(get_session),
                         context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _record(session, context, SubjectType.BUYER, buyer_id, payload)


@router.get("/notifications", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def list_notifications(status: NotificationStatus | None = None, limit: int = 100, session: Session = Depends(get_session),
                       context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    from src.backend.app.notifications.application.providers import configured_provider
    statement = select(Notification).where(Notification.organization_id == context.organization_id)
    if status is not None:
        statement = statement.where(Notification.status == status.value)
    rows = session.scalars(statement.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(min(max(limit, 1), 500))).all()
    provider = configured_provider()
    return {"provider": provider.name, "provider_sends_messages": provider.sends,
            "notifications": [service.notification_view(session, row) for row in rows]}


@router.get("/notifications/{notification_id}", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def get_notification(notification_id: UUID, session: Session = Depends(get_session)) -> dict:
    notification = session.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(404, "notification not found")
    return service.notification_view(session, notification, with_history=True)
