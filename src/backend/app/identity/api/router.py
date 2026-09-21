import hashlib
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
from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import PermissionCode, ROLE_PERMISSIONS, RoleCode
from src.backend.app.main_dependencies import get_session

router = APIRouter(tags=["identity and access"])


class InviteCommand(BaseModel):
    user_id: UUID
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=2, max_length=200)
    role: RoleCode
    farmer_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("valid email is required")
        return value.lower()


class RoleChangeCommand(BaseModel):
    role: RoleCode


class AcceptInvitationCommand(BaseModel):
    token: str = Field(min_length=32, max_length=200)


def _membership_view(membership: OrganizationMembership, user: UserAccount) -> dict:
    return {
        "membership_id": str(membership.id), "user_id": str(user.id), "name": user.display_name,
        "email": user.email, "role": membership.role_code.value, "status": membership.status.value,
        "farmer_id": str(membership.farmer_id) if membership.farmer_id else None,
        "last_active_at": user.last_active_at, "invited_at": membership.invited_at,
        "accepted_at": membership.accepted_at,
    }


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
        "organizations": [{"id": str(org.id), "name": org.name, "role": member.role_code.value}
                          for member, org in memberships],
    }


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


@router.post("/admin/users/invitations", status_code=status.HTTP_201_CREATED)
def invite_user(payload: InviteCommand,
                context: AuthorizationContext = Depends(require_permission(PermissionCode.USER_INVITE)),
                session: Session = Depends(get_session)) -> dict:
    forbid_platform_admin_assignment(context, payload.role)
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
        status=MembershipStatus.INVITED, farmer_id=payload.farmer_id, invited_by=context.user_id,
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
    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.id == membership_id,
        OrganizationMembership.organization_id == context.organization_id,
    ))
    if membership is None:
        raise HTTPException(404, "membership not found")
    if membership.role_code == RoleCode.PLATFORM_ADMIN and context.role != RoleCode.PLATFORM_ADMIN:
        raise HTTPException(403, "platform administrator role is internally managed")
    membership.role_code = payload.role
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
