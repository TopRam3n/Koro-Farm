import hashlib
import os
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.core.auth import get_current_user
from src.backend.app.identity.application.authorization import (
    AuthorizationContext,
    forbid_platform_admin_assignment,
    get_authorization_context,
    require_permission,
)
from src.backend.app.identity.domain.models import (
    AccessRequest,
    AccessRequestStatus,
    DEFAULT_ORGANIZATION_ID,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    UserAccount,
)
from src.backend.app.identity.domain.permissions import PermissionCode, ROLE_PERMISSIONS, RoleCode
from src.backend.app.main_dependencies import get_session
from src.backend.app.demand.domain.models import Buyer
from src.backend.app.supply.domain.models import Farmer

router = APIRouter(tags=["identity and access"])


class InviteCommand(BaseModel):
    user_id: UUID
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=2, max_length=200)
    role: RoleCode
    farmer_id: UUID | None = None
    buyer_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("valid email is required")
        return value.lower()


class RoleChangeCommand(BaseModel):
    role: RoleCode
    farmer_id: UUID | None = None
    buyer_id: UUID | None = None


class AcceptInvitationCommand(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class AccessRequestCommand(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    requested_role: RoleCode

    @field_validator("requested_role")
    @classmethod
    def self_service_role(cls, value: RoleCode) -> RoleCode:
        if value not in {RoleCode.FARMER, RoleCode.BUYER}:
            raise ValueError("only farmer and customer access can be requested")
        return value


class AccessRequestDecision(BaseModel):
    farmer_id: UUID | None = None
    buyer_id: UUID | None = None


def _access_request_view(request: AccessRequest, user: UserAccount) -> dict:
    return {
        "id": str(request.id),
        "user_id": str(user.id),
        "name": user.display_name,
        "email": user.email,
        "requested_role": request.requested_role.value,
        "status": request.status.value,
        "created_at": request.created_at,
        "reviewed_at": request.reviewed_at,
    }


def _require_request_reviewer(context: AuthorizationContext, session: Session) -> None:
    reviewer_email = os.getenv("ACCESS_REQUEST_REVIEWER_EMAIL", "allensava13@gmail.com").strip().lower()
    reviewer = session.get(UserAccount, context.user_id)
    if (reviewer is None or reviewer.email.lower() != reviewer_email
            or PermissionCode.USER_INVITE not in context.permissions):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "designated access reviewer permission required")


def _membership_view(membership: OrganizationMembership, user: UserAccount) -> dict:
    return {
        "membership_id": str(membership.id), "user_id": str(user.id), "name": user.display_name,
        "email": user.email, "role": membership.role_code.value, "status": membership.status.value,
        "farmer_id": str(membership.farmer_id) if membership.farmer_id else None,
        "buyer_id": str(membership.buyer_id) if membership.buyer_id else None,
        "last_active_at": user.last_active_at, "invited_at": membership.invited_at,
        "accepted_at": membership.accepted_at,
    }


def _validate_role_binding(
    role: RoleCode,
    farmer_id: UUID | None,
    buyer_id: UUID | None,
    organization_id: UUID,
    session: Session,
) -> None:
    if role == RoleCode.FARMER:
        if farmer_id is None or buyer_id is not None:
            raise HTTPException(422, "farmer membership requires only a farmer_id")
        farmer = session.scalar(select(Farmer).where(
            Farmer.id == farmer_id, Farmer.organization_id == organization_id,
        ))
        if farmer is None:
            raise HTTPException(404, "farmer not found")
    elif role == RoleCode.BUYER:
        if buyer_id is None or farmer_id is not None:
            raise HTTPException(422, "buyer membership requires only a buyer_id")
        buyer = session.scalar(select(Buyer).where(
            Buyer.id == buyer_id, Buyer.organization_id == organization_id,
        ))
        if buyer is None:
            raise HTTPException(404, "buyer not found")
    elif farmer_id is not None or buyer_id is not None:
        raise HTTPException(422, "farmer_id and buyer_id are only valid for their matching role")


@router.get("/me")
def profile(context: AuthorizationContext = Depends(get_authorization_context),
            session: Session = Depends(get_session)) -> dict:
    user = session.get(UserAccount, context.user_id)
    memberships = session.execute(
        select(OrganizationMembership, Organization)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(OrganizationMembership.user_id == context.user_id,
               OrganizationMembership.status == MembershipStatus.ACTIVE)
        .order_by(Organization.name)
    ).all()
    return {
        "id": str(user.id), "email": user.email, "name": user.display_name,
        "active_organization_id": str(context.organization_id), "active_role": context.role.value,
        "active_farmer_id": str(context.farmer_id) if context.farmer_id else None,
        "active_buyer_id": str(context.buyer_id) if context.buyer_id else None,
        "organizations": [{"id": str(org.id), "name": org.name, "role": member.role_code.value,
                   "farmer_id": str(member.farmer_id) if member.farmer_id else None,
                   "buyer_id": str(member.buyer_id) if member.buyer_id else None}
                          for member, org in memberships],
    }


@router.post("/access-requests", status_code=status.HTTP_201_CREATED)
def submit_access_request(
    payload: AccessRequestCommand,
    identity: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    email = str(identity.get("email") or "").strip().lower()
    confirmed_at = identity.get("email_confirmed_at") or identity.get("confirmed_at")
    if not email or not confirmed_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verify your email address before requesting access")
    try:
        user_id = UUID(str(identity.get("id")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid authenticated identity") from exc

    organization = session.get(Organization, DEFAULT_ORGANIZATION_ID)
    if organization is None or not organization.active:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "access requests are not configured")
    user = session.get(UserAccount, user_id)
    if user is None:
        user = UserAccount(id=user_id, email=email, display_name=payload.display_name.strip())
        session.add(user)
        session.flush()
    elif user.email.lower() != email:
        raise HTTPException(status.HTTP_409_CONFLICT, "authenticated email does not match the existing account")
    else:
        user.display_name = payload.display_name.strip()

    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.organization_id == DEFAULT_ORGANIZATION_ID,
    ))
    if membership is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "an organization membership already exists for this account")

    existing = session.scalar(select(AccessRequest).where(
        AccessRequest.user_id == user_id,
        AccessRequest.organization_id == DEFAULT_ORGANIZATION_ID,
        AccessRequest.status == AccessRequestStatus.PENDING,
    ).order_by(AccessRequest.created_at.desc()))
    if existing is not None:
        if existing.requested_role != payload.requested_role:
            raise HTTPException(status.HTTP_409_CONFLICT, "a different access request is already pending")
        session.commit()
        return {"id": str(existing.id), "requested_role": existing.requested_role.value,
                "status": existing.status.value, "created_at": existing.created_at}

    request = AccessRequest(
        organization_id=DEFAULT_ORGANIZATION_ID,
        user_id=user_id,
        requested_role=payload.requested_role,
        status=AccessRequestStatus.PENDING,
    )
    session.add(request)
    session.commit()
    return {"id": str(request.id), "requested_role": request.requested_role.value,
            "status": request.status.value, "created_at": request.created_at}


@router.get("/access-requests/mine")
def my_access_requests(identity: dict = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> dict:
    try:
        user_id = UUID(str(identity.get("id")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid authenticated identity") from exc
    user = session.get(UserAccount, user_id)
    if user is None:
        return {"items": []}
    rows = session.execute(
        select(AccessRequest, UserAccount)
        .join(UserAccount, UserAccount.id == AccessRequest.user_id)
        .where(AccessRequest.user_id == user_id)
        .order_by(AccessRequest.created_at.desc())
    ).all()
    return {"items": [_access_request_view(request, account) for request, account in rows]}


@router.get("/admin/access-requests")
def list_access_requests(context: AuthorizationContext = Depends(get_authorization_context),
                         session: Session = Depends(get_session)) -> dict:
    _require_request_reviewer(context, session)
    rows = session.execute(
        select(AccessRequest, UserAccount)
        .join(UserAccount, UserAccount.id == AccessRequest.user_id)
        .where(AccessRequest.organization_id == context.organization_id,
               AccessRequest.status == AccessRequestStatus.PENDING)
        .order_by(AccessRequest.created_at, AccessRequest.id)
    ).all()
    return {"items": [_access_request_view(request, user) for request, user in rows]}


@router.post("/admin/access-requests/{request_id}/approve")
def approve_access_request(
    request_id: UUID,
    payload: AccessRequestDecision,
    context: AuthorizationContext = Depends(get_authorization_context),
    session: Session = Depends(get_session),
) -> dict:
    _require_request_reviewer(context, session)
    request = session.scalar(select(AccessRequest).where(
        AccessRequest.id == request_id,
        AccessRequest.organization_id == context.organization_id,
        AccessRequest.status == AccessRequestStatus.PENDING,
    ).with_for_update())
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pending access request not found")
    _validate_role_binding(request.requested_role, payload.farmer_id, payload.buyer_id,
                           context.organization_id, session)
    if session.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.user_id == request.user_id,
        OrganizationMembership.organization_id == context.organization_id,
    )):
        raise HTTPException(status.HTTP_409_CONFLICT, "an organization membership already exists")

    now = datetime.now(timezone.utc)
    membership = OrganizationMembership(
        user_id=request.user_id,
        organization_id=context.organization_id,
        role_code=request.requested_role,
        status=MembershipStatus.ACTIVE,
        farmer_id=payload.farmer_id,
        buyer_id=payload.buyer_id,
        invited_by=context.user_id,
        accepted_at=now,
    )
    request.status = AccessRequestStatus.APPROVED
    request.reviewed_by = context.user_id
    request.reviewed_at = now
    session.add(membership)
    session.commit()
    return {"request_id": str(request.id), "membership_id": str(membership.id),
            "role": membership.role_code.value, "status": request.status.value}


@router.post("/admin/access-requests/{request_id}/reject")
def reject_access_request(request_id: UUID,
                          context: AuthorizationContext = Depends(get_authorization_context),
                          session: Session = Depends(get_session)) -> dict:
    _require_request_reviewer(context, session)
    request = session.scalar(select(AccessRequest).where(
        AccessRequest.id == request_id,
        AccessRequest.organization_id == context.organization_id,
        AccessRequest.status == AccessRequestStatus.PENDING,
    ).with_for_update())
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pending access request not found")
    request.status = AccessRequestStatus.REJECTED
    request.reviewed_by = context.user_id
    request.reviewed_at = datetime.now(timezone.utc)
    session.commit()
    return {"request_id": str(request.id), "status": request.status.value}


@router.get("/admin/users")
def list_users(context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_VIEW)),
               session: Session = Depends(get_session)) -> dict:
    rows = session.execute(
        select(OrganizationMembership, UserAccount)
        .join(UserAccount, UserAccount.id == OrganizationMembership.user_id)
        .where(OrganizationMembership.organization_id == context.organization_id)
        .order_by(UserAccount.display_name)
    ).all()
    return {"items": [_membership_view(member, user) for member, user in rows]}


@router.get("/admin/users/assignable-entities")
def assignable_entities(context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_INVITE)),
                        session: Session = Depends(get_session)) -> dict:
    farmers = session.scalars(select(Farmer).where(
        Farmer.organization_id == context.organization_id, Farmer.active.is_(True),
    ).order_by(Farmer.name)).all()
    buyers = session.scalars(select(Buyer).where(
        Buyer.organization_id == context.organization_id,
    ).order_by(Buyer.name)).all()
    return {
        "farmers": [{"id": str(item.id), "name": item.name, "parish": item.parish} for item in farmers],
        "buyers": [{"id": str(item.id), "name": item.name} for item in buyers],
    }


@router.post("/admin/users/invitations", status_code=status.HTTP_201_CREATED)
def invite_user(payload: InviteCommand,
                context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_INVITE)),
                session: Session = Depends(get_session)) -> dict:
    forbid_platform_admin_assignment(context, payload.role)
    _validate_role_binding(payload.role, payload.farmer_id, payload.buyer_id, context.organization_id, session)
    if session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.user_id == payload.user_id,
        OrganizationMembership.organization_id == context.organization_id,
    )):
        raise HTTPException(409, "membership already exists")
    user = session.get(UserAccount, payload.user_id)
    if user is None:
        user = UserAccount(id=payload.user_id, email=str(payload.email), display_name=payload.display_name)
        session.add(user)
    token = secrets.token_urlsafe(32)
    membership = OrganizationMembership(
        user_id=payload.user_id, organization_id=context.organization_id, role_code=payload.role,
        status=MembershipStatus.INVITED, farmer_id=payload.farmer_id, buyer_id=payload.buyer_id,
        invited_by=context.user_id,
        invitation_token_hash=hashlib.sha256(token.encode()).hexdigest(), invited_at=datetime.now(timezone.utc),
    )
    session.add(membership)
    session.commit()
    return {"membership_id": str(membership.id), "status": membership.status.value,
            "invitation_token": token, "delivery": "RETURNED_ONCE_FOR_PILOT_DELIVERY"}


@router.post("/invitations/accept")
def accept_invitation(payload: AcceptInvitationCommand, identity: dict = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> dict:
    try:
        user_id = UUID(str(identity.get("id")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "invalid authenticated identity") from exc
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.invitation_token_hash == token_hash,
        OrganizationMembership.status == MembershipStatus.INVITED,
    ))
    if membership is None:
        raise HTTPException(404, "invitation not found")
    membership.status = MembershipStatus.ACTIVE
    membership.accepted_at = datetime.now(timezone.utc)
    membership.invitation_token_hash = None
    session.commit()
    return {"membership_id": str(membership.id), "organization_id": str(membership.organization_id),
            "status": membership.status.value}


@router.patch("/admin/users/{membership_id}/role")
def change_role(membership_id: UUID, payload: RoleChangeCommand,
                context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_MANAGE_ROLE)),
                session: Session = Depends(get_session)) -> dict:
    forbid_platform_admin_assignment(context, payload.role)
    _validate_role_binding(payload.role, payload.farmer_id, payload.buyer_id, context.organization_id, session)
    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.id == membership_id,
        OrganizationMembership.organization_id == context.organization_id,
    ))
    if membership is None:
        raise HTTPException(404, "membership not found")
    if membership.role_code == RoleCode.PLATFORM_ADMIN and context.role != RoleCode.PLATFORM_ADMIN:
        raise HTTPException(403, "platform administrator role is internally managed")
    membership.role_code = payload.role
    membership.farmer_id = payload.farmer_id
    membership.buyer_id = payload.buyer_id
    session.commit()
    return {"membership_id": str(membership.id), "role": membership.role_code.value}


@router.post("/admin/users/{membership_id}/deactivate")
def deactivate_membership(membership_id: UUID,
                          context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_MANAGE_ROLE)),
                          session: Session = Depends(get_session)) -> dict:
    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.id == membership_id,
        OrganizationMembership.organization_id == context.organization_id,
    ))
    if membership is None:
        raise HTTPException(404, "membership not found")
    if membership.user_id == context.user_id:
        raise HTTPException(409, "cannot deactivate the active membership")
    if membership.role_code == RoleCode.PLATFORM_ADMIN and context.role != RoleCode.PLATFORM_ADMIN:
        raise HTTPException(403, "platform administrator role is internally managed")
    membership.status = MembershipStatus.INACTIVE
    session.commit()
    return {"membership_id": str(membership.id), "status": membership.status.value}


@router.get("/admin/roles")
def list_roles(context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_VIEW))) -> dict:
    roles = [role for role in RoleCode if role != RoleCode.PLATFORM_ADMIN or context.role == RoleCode.PLATFORM_ADMIN]
    return {"items": [{"code": role.value, "permissions": sorted(item.value for item in ROLE_PERMISSIONS[role])}
                      for role in roles]}


@router.get("/admin/organization")
def get_organization(context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_VIEW)),
                     session: Session = Depends(get_session)) -> dict:
    organization = session.get(Organization, context.organization_id)
    return {"id": str(organization.id), "name": organization.name, "slug": organization.slug,
            "active": organization.active}
