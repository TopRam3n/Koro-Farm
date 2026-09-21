from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.core.auth import get_current_user
from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import PermissionCode, ROLE_PERMISSIONS, RoleCode
from src.backend.app.main_dependencies import get_session


@dataclass(frozen=True)
class AuthorizationContext:
    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    role: RoleCode
    permissions: frozenset[PermissionCode]
    farmer_id: UUID | None = None


def get_authorization_context(
    identity: dict[str, Any] = Depends(get_current_user),
    organization_header: str | None = Header(default=None, alias="X-Organization-ID"),
    session: Session = Depends(get_session),
) -> AuthorizationContext:
    try:
        user_id = UUID(str(identity.get("id")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authenticated identity is not a valid user") from exc
    user = session.get(UserAccount, user_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "active account required")
    memberships = session.scalars(select(OrganizationMembership).where(
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.status == MembershipStatus.ACTIVE,
    )).all()
    if organization_header:
        try:
            organization_id = UUID(organization_header)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid X-Organization-ID") from exc
        membership = next((item for item in memberships if item.organization_id == organization_id), None)
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        membership = None
    if membership is None:
        # Deliberately identical for missing/inactive/cross-tenant membership.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "active organization membership required")
    organization = session.get(Organization, membership.organization_id)
    if organization is None or not organization.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "active organization membership required")
    user.last_active_at = datetime.now(timezone.utc)
    session.flush()
    return AuthorizationContext(
        user_id=user_id,
        organization_id=membership.organization_id,
        membership_id=membership.id,
        role=membership.role_code,
        permissions=ROLE_PERMISSIONS[membership.role_code],
        farmer_id=membership.farmer_id,
    )


def require_permission(permission: PermissionCode) -> Callable:
    def dependency(context: AuthorizationContext = Depends(get_authorization_context)) -> AuthorizationContext:
        if permission not in context.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "permission denied")
        return context

    return dependency


def forbid_platform_admin_assignment(actor: AuthorizationContext, requested_role: RoleCode) -> None:
    if requested_role == RoleCode.PLATFORM_ADMIN and actor.role != RoleCode.PLATFORM_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform administrator role is internally managed")
