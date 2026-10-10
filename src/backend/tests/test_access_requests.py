from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from src.backend.app.core.auth import get_current_user
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context
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
from src.backend.app.main import app
from src.backend.app.demand.domain.models import Buyer
from src.backend.app.supply.domain.models import Farmer


def _organization(session) -> None:
    if session.get(Organization, DEFAULT_ORGANIZATION_ID) is None:
        session.add(Organization(
            id=DEFAULT_ORGANIZATION_ID,
            name="Request Test Organization",
            slug=f"request-test-{uuid4().hex[:8]}",
        ))
        session.commit()


def test_verified_user_can_request_only_farmer_or_buyer_role(client, session) -> None:
    _organization(session)
    applicant_id = uuid4()
    identity = {
        "id": str(applicant_id),
        "email": "applicant@example.test",
        "email_confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    app.dependency_overrides[get_current_user] = lambda: identity

    response = client.post("/access-requests", json={"display_name": "Farm Applicant", "requested_role": "FARMER"})
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    request = session.get(AccessRequest, UUID(response.json()["id"]))
    assert request.user_id == applicant_id
    assert request.organization_id == DEFAULT_ORGANIZATION_ID

    mine = client.get("/access-requests/mine")
    assert mine.status_code == 200
    assert mine.json()["items"][0]["email"] == identity["email"]

    forbidden_role = client.post("/access-requests", json={
        "display_name": "Developer Applicant", "requested_role": "PLATFORM_ADMIN",
    })
    assert forbidden_role.status_code == 422


def test_unverified_email_cannot_request_access(client, session) -> None:
    _organization(session)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(uuid4()), "email": "unverified@example.test",
    }
    response = client.post("/access-requests", json={
        "display_name": "Unverified Applicant", "requested_role": "BUYER",
    })
    assert response.status_code == 403


def test_only_designated_reviewer_can_approve_and_bind_request(client, session, monkeypatch) -> None:
    _organization(session)
    monkeypatch.setenv("ACCESS_REQUEST_REVIEWER_EMAIL", "reviewer@example.test")
    applicant = UserAccount(id=uuid4(), email="farmer@example.test", display_name="Farm Applicant")
    reviewer = UserAccount(id=uuid4(), email="reviewer@example.test", display_name="Access Reviewer")
    farmer = Farmer(organization_id=DEFAULT_ORGANIZATION_ID, name="Applicant Farm", parish="St. Mary")
    session.add_all([applicant, reviewer, farmer])
    session.flush()
    request = AccessRequest(
        organization_id=DEFAULT_ORGANIZATION_ID,
        user_id=applicant.id,
        requested_role=RoleCode.FARMER,
        status=AccessRequestStatus.PENDING,
    )
    session.add(request)
    session.commit()

    def reviewer_context():
        return AuthorizationContext(
            user_id=reviewer.id,
            organization_id=DEFAULT_ORGANIZATION_ID,
            membership_id=uuid4(),
            role=RoleCode.ORGANIZATION_ADMIN,
            permissions=ROLE_PERMISSIONS[RoleCode.ORGANIZATION_ADMIN],
        )

    app.dependency_overrides[get_authorization_context] = reviewer_context
    queue = client.get("/admin/access-requests")
    assert queue.status_code == 200
    assert queue.json()["items"][0]["email"] == applicant.email

    approval = client.post(f"/admin/access-requests/{request.id}/approve", json={"farmer_id": str(farmer.id)})
    assert approval.status_code == 200
    session.refresh(request)
    membership = session.scalar(select(OrganizationMembership).where(
        OrganizationMembership.user_id == applicant.id,
        OrganizationMembership.organization_id == DEFAULT_ORGANIZATION_ID,
    ))
    assert request.status == AccessRequestStatus.APPROVED
    assert request.reviewed_by == reviewer.id
    assert membership.role_code == RoleCode.FARMER
    assert membership.farmer_id == farmer.id
    assert membership.status == MembershipStatus.ACTIVE


def test_other_invite_admin_cannot_review_access_requests(client, session, monkeypatch) -> None:
    _organization(session)
    monkeypatch.setenv("ACCESS_REQUEST_REVIEWER_EMAIL", "reviewer@example.test")
    other_admin = UserAccount(id=uuid4(), email="other-admin@example.test", display_name="Other Admin")
    session.add(other_admin)
    session.commit()
    app.dependency_overrides[get_authorization_context] = lambda: AuthorizationContext(
        user_id=other_admin.id,
        organization_id=DEFAULT_ORGANIZATION_ID,
        membership_id=uuid4(),
        role=RoleCode.ORGANIZATION_ADMIN,
        permissions=ROLE_PERMISSIONS[RoleCode.ORGANIZATION_ADMIN],
    )
    response = client.get("/admin/access-requests")
    assert response.status_code == 403
