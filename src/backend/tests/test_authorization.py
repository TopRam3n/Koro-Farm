from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from src.backend.app.core.auth import get_current_user
from src.backend.app.identity.application.authorization import get_authorization_context
from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.main import app
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus


ORG_A = UUID("00000000-0000-0000-0000-000000001001")
ORG_B = UUID("00000000-0000-0000-0000-000000001002")


def _identity(session, role: RoleCode, status: MembershipStatus = MembershipStatus.ACTIVE,
              organization_id: UUID = ORG_A) -> tuple[UserAccount, OrganizationMembership]:
    for org_id, name in ((ORG_A, "Alpha"), (ORG_B, "Beta")):
        if session.get(Organization, org_id) is None:
            session.add(Organization(id=org_id, name=f"{name} Organization", slug=f"{name.lower()}-{uuid4().hex[:6]}"))
    user = UserAccount(id=uuid4(), email=f"{uuid4().hex}@example.test", display_name="Test Operator")
    session.add(user)
    session.flush()
    membership = OrganizationMembership(
        user_id=user.id, organization_id=organization_id, role_code=role, status=status,
        accepted_at=datetime.now(timezone.utc) if status == MembershipStatus.ACTIVE else None,
    )
    session.add(membership)
    session.commit()
    return user, membership


def _as(client, user: UserAccount) -> None:
    app.dependency_overrides.pop(get_authorization_context, None)
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user.id), "email": user.email}


def test_same_organization_allowed_role_is_permitted(client, session) -> None:
    user, _ = _identity(session, RoleCode.ORGANIZATION_ADMIN)
    _as(client, user)
    response = client.get("/admin/users", headers={"X-Organization-ID": str(ORG_A)})
    assert response.status_code == 200
    assert response.json()["items"][0]["user_id"] == str(user.id)


def test_same_organization_wrong_role_is_denied(client, session) -> None:
    user, _ = _identity(session, RoleCode.WAREHOUSE_OPERATOR)
    _as(client, user)
    assert client.get("/admin/users", headers={"X-Organization-ID": str(ORG_A)}).status_code == 403


def test_different_organization_is_denied_without_resource_leak(client, session) -> None:
    user, _ = _identity(session, RoleCode.ORGANIZATION_ADMIN, organization_id=ORG_A)
    _as(client, user)
    response = client.get("/admin/users", headers={"X-Organization-ID": str(ORG_B)})
    assert response.status_code == 403
    assert response.json()["detail"] == "active organization membership required"


def test_inactive_membership_is_denied(client, session) -> None:
    user, _ = _identity(session, RoleCode.ORGANIZATION_ADMIN, MembershipStatus.INACTIVE)
    _as(client, user)
    assert client.get("/admin/users", headers={"X-Organization-ID": str(ORG_A)}).status_code == 403


def test_unauthenticated_request_is_denied(client) -> None:
    app.dependency_overrides.pop(get_authorization_context, None)
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get("/admin/users", headers={"X-Organization-ID": str(ORG_A)}).status_code == 401


def test_auditor_mutation_and_platform_admin_assignment_are_denied(client, session) -> None:
    auditor, auditor_membership = _identity(session, RoleCode.AUDITOR)
    _as(client, auditor)
    assert client.post(f"/admin/users/{auditor_membership.id}/deactivate",
                       headers={"X-Organization-ID": str(ORG_A)}).status_code == 403

    admin, target = _identity(session, RoleCode.ORGANIZATION_ADMIN)
    _as(client, admin)
    response = client.patch(
        f"/admin/users/{target.id}/role", headers={"X-Organization-ID": str(ORG_A)},
        json={"role": "PLATFORM_ADMIN"},
    )
    assert response.status_code == 403


def test_invitation_acceptance_and_role_change_lifecycle(client, session) -> None:
    admin, _ = _identity(session, RoleCode.ORGANIZATION_ADMIN)
    _as(client, admin)
    invited_id = uuid4()
    invitation = client.post(
        "/admin/users/invitations", headers={"X-Organization-ID": str(ORG_A)},
        json={"user_id": str(invited_id), "email": "invitee@example.test", "display_name": "Invitee User",
              "role": "SUPPLY_COORDINATOR"},
    )
    assert invitation.status_code == 201
    token = invitation.json()["invitation_token"]
    app.dependency_overrides[get_current_user] = lambda: {"id": str(invited_id), "email": "invitee@example.test"}
    accepted = client.post("/invitations/accept", json={"token": token})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACTIVE"


def test_warehouse_operator_cannot_create_procurement_requirement(client, session) -> None:
    user, _ = _identity(session, RoleCode.WAREHOUSE_OPERATOR)
    _as(client, user)
    response = client.post("/requirements", headers={"X-Organization-ID": str(ORG_A)}, json={})
    assert response.status_code == 403


def test_cross_tenant_requirement_identifier_returns_not_found(client, session) -> None:
    user, _ = _identity(session, RoleCode.PROCUREMENT_MANAGER, organization_id=ORG_A)
    buyer = Buyer(organization_id=ORG_B, name="Other buyer", buyer_type="HOTEL", destination="Jamaica")
    session.add(buyer); session.flush()
    requirement = Requirement(
        buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A, required_quantity_kg=Decimal("100"),
        delivery_window_start=date(2026, 10, 1), delivery_window_end=date(2026, 10, 10),
    )
    session.add(requirement); session.commit()
    _as(client, user)
    assert client.get(f"/requirements/{requirement.id}",
                      headers={"X-Organization-ID": str(ORG_A)}).status_code == 404


def test_farmer_cannot_access_another_farmers_private_lot(client, session) -> None:
    own_farmer = Farmer(organization_id=ORG_A, name="Own Farmer", parish="Manchester")
    other_farmer = Farmer(organization_id=ORG_A, name="Other Farmer", parish="Clarendon")
    session.add_all([own_farmer, other_farmer]); session.flush()
    other_lot = ProductionLot(
        farmer_id=other_farmer.id, crop=Crop.GINGER, harvest_start=date(2026, 10, 1),
        harvest_end=date(2026, 10, 10), expected_quantity_kg=Decimal("100"),
        available_quantity_kg=Decimal("100"), reserved_quantity_kg=Decimal("0"),
        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
        parish=other_farmer.parish, status=ProductionLotStatus.AVAILABLE,
        last_verified_at=datetime.now(timezone.utc),
    )
    session.add(other_lot); session.commit()
    user, membership = _identity(session, RoleCode.FARMER)
    membership.farmer_id = own_farmer.id
    session.commit()
    _as(client, user)
    assert client.get(f"/production-lots/{other_lot.id}",
                      headers={"X-Organization-ID": str(ORG_A)}).status_code == 404
