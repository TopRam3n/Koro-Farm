"""Seed a fresh, migrated database with two isolated test organizations for browser E2E.

Creates only organizations, user accounts and memberships, plus the supplier record a farmer account signs in
as and the buyer record a buyer account signs in as (a farmer or buyer membership must name the record it acts
for). Other buyers, lots and orders are created by the E2E test itself through the real UI. Writes the test users (with generated passwords) to a JSON
file read by src/frontend/e2e/r1/support/auth-stub.mjs and the Playwright specs.

Usage: DATABASE_URL=... python -m src.backend.scripts.seed_e2e <users.json>
"""
import json
import secrets
import sys
from datetime import datetime, timezone
from uuid import uuid4

import src.backend.app.main  # noqa: F401  (registers every mapped model)
from src.backend.app.demand.domain.models import Buyer
from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.infrastructure.database.session import create_session_factory
from src.backend.app.supply.domain.models import Farmer

ACCOUNTS = [
    # key, organization, role, display name
    ("coordinator_a", "A", RoleCode.SUPPLY_COORDINATOR, "Alpha Coordinator"),
    ("colleague_a", "A", RoleCode.PROCUREMENT_MANAGER, "Alpha Colleague"),
    ("coordinator_b", "B", RoleCode.SUPPLY_COORDINATOR, "Beta Coordinator"),
    ("farmer_a", "A", RoleCode.FARMER, "Fiona Grant"),
    ("warehouse_a", "A", RoleCode.WAREHOUSE_OPERATOR, "Wesley Brown"),
    ("buyer_a", "A", RoleCode.BUYER, "Bianca Lewis"),
    ("auditor_a", "A", RoleCode.AUDITOR, "Audrey Clarke"),  # WP5 M1: read and flag only
]
FARMER_PARISH = "St. Ann"


def main(path: str) -> None:
    session = create_session_factory()()
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:6]
    orgs = {
        "A": Organization(id=uuid4(), name="Blue Mountain Exports (E2E test)", slug=f"e2e-a-{suffix}"),
        "B": Organization(id=uuid4(), name="Cockpit Country Growers (E2E test)", slug=f"e2e-b-{suffix}"),
    }
    session.add_all(orgs.values())
    session.flush()
    users = []
    for key, org_key, role, name in ACCOUNTS:
        user = UserAccount(id=uuid4(), email=f"{key}.{suffix}@e2e.korofarm.test", display_name=name)
        session.add(user)
        farmer = buyer = None
        if role == RoleCode.BUYER:
            buyer = Buyer(id=uuid4(), organization_id=orgs[org_key].id, name=f"Ocho Rios Resort {suffix}", buyer_type="Hotel",
                          destination="Ocho Rios")
            session.add(buyer)
        if role == RoleCode.FARMER:
            farmer = Farmer(id=uuid4(), organization_id=orgs[org_key].id, name=f"{name} {suffix}", parish=FARMER_PARISH)
            session.add(farmer)
        session.flush()
        session.add(OrganizationMembership(user_id=user.id, organization_id=orgs[org_key].id, role_code=role,
                                           status=MembershipStatus.ACTIVE, accepted_at=now,
                                           farmer_id=farmer.id if farmer else None, buyer_id=buyer.id if buyer else None))
        users.append({"farmer_id": str(farmer.id) if farmer else None, "farmer_name": farmer.name if farmer else None,
                      "farmer_parish": farmer.parish if farmer else None, "buyer_name": buyer.name if buyer else None,
                      "key": key, "id": str(user.id), "email": user.email, "password": secrets.token_urlsafe(18),
                      "display_name": name, "role": role.value, "organization_id": str(orgs[org_key].id),
                      "organization_name": orgs[org_key].name, "created_at": now.isoformat()})
    session.commit()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"users": users}, handle, indent=2)
    print(f"seeded {len(orgs)} organizations and {len(users)} users -> {path}")


if __name__ == "__main__":
    main(sys.argv[1])
