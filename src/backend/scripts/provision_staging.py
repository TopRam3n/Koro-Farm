"""Provision staging organizations, accounts and memberships from a plan file. Dry run unless --apply.

  python -m src.backend.scripts.provision_staging /path/outside/repo/staging-plan.json            # report only
  python -m src.backend.scripts.provision_staging /path/outside/repo/staging-plan.json --apply    # write

The people themselves are created in Supabase (Authentication > Users > Add user), never here: this script holds no
passwords and calls no Supabase API. It links each Supabase user id to a KoroFarm account and gives it one staff
membership per organization. Plan file (keep it outside the repository; it names real people):

  {
    "organizations": [{"slug": "staging-org-a", "name": "Staging Organization A"}],
    "users": [{"id": "<Supabase user UUID>", "email": "person@example.com", "display_name": "Person",
               "memberships": [{"organization": "staging-org-a", "role": "SUPPLY_COORDINATOR"}]}]
  }

Rules:
* Never runs with APP_ENV=production.
* Additive and idempotent: existing records that already match are left alone and reported as unchanged.
* Never corrects anything ambiguous. A conflict (an email already used by another id, an existing membership with a
  different role or status, a slug with a different name) is reported and nothing at all is written.
* Staff roles only. Farmers and buyers join through the in-app invitation or access-request flow, which links them to
  their farm or buyer record. PLATFORM_ADMIN (access across every organization) needs --allow-platform-admin.
* All changes are applied in one transaction, so a failure writes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

STAFF_ROLES = ("ORGANIZATION_ADMIN", "PROCUREMENT_MANAGER", "SUPPLY_COORDINATOR", "WAREHOUSE_OPERATOR", "AUDITOR")
LINKED_ROLES = ("FARMER", "BUYER")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PlanError(ValueError):
    """The plan file is malformed or asks for something this script never does."""


@dataclass
class Report:
    create: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"create:    {item}" for item in self.create]
        out += [f"unchanged: {item}" for item in self.unchanged]
        out += [f"CONFLICT:  {item}" for item in self.conflicts]
        return out or ["nothing to do"]


def load_plan(path: Path, allow_platform_admin: bool = False) -> dict:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot read plan: {exc}") from exc
    if not isinstance(plan, dict) or set(plan) - {"organizations", "users"}:
        raise PlanError("plan must be an object with 'organizations' and 'users' only")
    organizations = plan.get("organizations") or []
    users = plan.get("users") or []
    slugs = set()
    for organization in organizations:
        slug, name = organization.get("slug", ""), (organization.get("name") or "").strip()
        if not SLUG.match(slug) or not name or set(organization) - {"slug", "name"}:
            raise PlanError(f"organization needs a lowercase slug (letters, digits, hyphens) and a name: {organization}")
        if slug in slugs:
            raise PlanError(f"organization {slug} appears twice")
        slugs.add(slug)
    ids, emails = set(), set()
    for user in users:
        if set(user) - {"id", "email", "display_name", "memberships"}:
            raise PlanError(f"unexpected user fields {sorted(set(user) - {'id', 'email', 'display_name', 'memberships'})}"
                            " (passwords never belong in the plan)")
        try:
            user_id = UUID(str(user.get("id")))
        except ValueError as exc:
            raise PlanError(f"user id must be the Supabase user UUID: {user.get('email')}") from exc
        email = (user.get("email") or "").strip().lower()
        if not EMAIL.match(email) or not (user.get("display_name") or "").strip():
            raise PlanError(f"user {user_id} needs an email and a display name")
        if user_id in ids or email in emails:
            raise PlanError(f"user {email} appears twice")
        ids.add(user_id)
        emails.add(email)
        for membership in user.get("memberships") or []:
            role = membership.get("role", "")
            if membership.get("organization") not in slugs:
                raise PlanError(f"membership of {email} must name an organization listed in the plan")
            if role in LINKED_ROLES:
                raise PlanError(f"{role} memberships link to a farm or buyer record; use the in-app invitation instead ({email})")
            if role == "PLATFORM_ADMIN" and not allow_platform_admin:
                raise PlanError(f"PLATFORM_ADMIN reaches every organization; pass --allow-platform-admin deliberately ({email})")
            if role not in (*STAFF_ROLES, "PLATFORM_ADMIN"):
                raise PlanError(f"unknown role {role!r} for {email}")
    return {"organizations": organizations, "users": users}


def provision(session: Session, plan: dict, apply: bool = False) -> Report:
    """Compare the plan with the database; with apply=True and no conflicts, write the missing records."""
    from src.backend.app.identity.domain.models import (
        MembershipStatus, Organization, OrganizationMembership, Role, UserAccount,
    )
    from src.backend.app.identity.domain.permissions import RoleCode

    report = Report()
    pending: list = []
    organizations: dict[str, Organization | None] = {}
    for item in plan["organizations"]:
        existing = session.scalar(select(Organization).where(Organization.slug == item["slug"]))
        if existing is None:
            organization = Organization(name=item["name"].strip(), slug=item["slug"], active=True)
            pending.append(organization)
            organizations[item["slug"]] = organization
            report.create.append(f"organization {item['slug']} ({item['name'].strip()})")
        elif existing.name != item["name"].strip() or not existing.active:
            report.conflicts.append(f"organization {item['slug']} exists as {existing.name!r} (active={existing.active})")
            organizations[item["slug"]] = existing
        else:
            organizations[item["slug"]] = existing
            report.unchanged.append(f"organization {item['slug']}")
    for item in plan["users"]:
        user_id, email = UUID(str(item["id"])), item["email"].strip().lower()
        account = session.get(UserAccount, user_id)
        same_email = session.scalar(select(UserAccount).where(func.lower(UserAccount.email) == email))
        if same_email is not None and same_email.id != user_id:
            report.conflicts.append(f"email {email} already belongs to account {same_email.id}, not {user_id}")
            continue
        if account is None:
            account = UserAccount(id=user_id, email=email, display_name=item["display_name"].strip(), active=True)
            pending.append(account)
            report.create.append(f"account {email} ({user_id})")
        elif account.email.lower() != email or not account.active:
            report.conflicts.append(f"account {user_id} exists as {account.email} (active={account.active})")
            continue
        else:
            report.unchanged.append(f"account {email}")
        for membership in item.get("memberships") or []:
            slug, role = membership["organization"], RoleCode(membership["role"])
            if session.get(Role, role) is None:
                report.conflicts.append(f"role {role} is missing from the roles table; run the migrations first")
                continue
            organization = organizations[slug]
            existing = None
            if organization is not None and organization.id is not None and account in session:
                existing = session.scalar(select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user_id, OrganizationMembership.organization_id == organization.id))
            if existing is None:
                pending.append((account, organization, role))
                report.create.append(f"membership {email} -> {slug} as {role}")
            elif existing.role_code != role or existing.status != MembershipStatus.ACTIVE:
                report.conflicts.append(f"membership {email} -> {slug} exists as {existing.role_code} ({existing.status}); "
                                        "change it in Users & Access, not here")
            else:
                report.unchanged.append(f"membership {email} -> {slug} as {role}")
    if not apply or report.conflicts or not report.create:
        return report
    now = datetime.now(timezone.utc)
    for item in pending:
        if isinstance(item, tuple):
            account, organization, role = item
            session.flush()
            session.add(OrganizationMembership(user_id=account.id, organization_id=organization.id, role_code=role,
                                               status=MembershipStatus.ACTIVE, accepted_at=now))
        else:
            session.add(item)
    session.flush()
    return report


def main(argv=None, env=None, session_factory=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Provision staging organizations, accounts and memberships")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    parser.add_argument("--allow-platform-admin", action="store_true")
    args = parser.parse_args(argv)
    app_env = env.get("APP_ENV", "").strip().lower()
    if app_env == "production":
        print("refusing to run in production", file=sys.stderr)
        return 2
    if app_env not in ("staging", "development", "test"):
        print("APP_ENV must be staging, development or test", file=sys.stderr)
        return 2
    try:
        plan = load_plan(args.plan, args.allow_platform_admin)
    except PlanError as exc:
        print(f"plan refused: {exc}", file=sys.stderr)
        return 2
    if session_factory is None:
        import src.backend.app.main  # noqa: F401  (registers every model and validates configuration)
        from src.backend.app.infrastructure.database.session import create_session_factory
        session_factory = create_session_factory()
    with session_factory() as session:
        try:
            report = provision(session, plan, apply=args.apply)
            if args.apply and not report.conflicts:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise
    print("\n".join(report.lines()))
    if report.conflicts:
        print("conflicts found: nothing was written", file=sys.stderr)
        return 1
    if not args.apply:
        print("dry run: nothing was written")
    else:
        print("applied" if report.create else "nothing to do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
