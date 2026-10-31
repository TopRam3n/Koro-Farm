"""Helpers for driving the recovery agent in tests the way production does: the worker plans, real members approve.

`agent_round` commits the test session and runs one worker tick on the same database (outbox, timers, recovery
tasks). `member` creates a real user and active membership, because the gateway re-verifies every approver.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.backend.app import worker
from src.backend.app.agents.application.approvals import decide
from src.backend.app.agents.domain.models import ProposalStatus, RecoveryProposal, RecoveryTask
from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.models import DEFAULT_ORGANIZATION_ID, MembershipStatus, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import ROLE_PERMISSIONS, RoleCode


def member(session, role: RoleCode = RoleCode.SUPPLY_COORDINATOR, organization_id: UUID = DEFAULT_ORGANIZATION_ID) -> AuthorizationContext:
    from two_orgs import ensure_roles
    ensure_roles(session)
    user = UserAccount(id=uuid4(), email=f"{role.value.lower()}-{uuid4().hex[:6]}@example.test", display_name=role.value.title())
    session.add(user); session.flush()
    membership = OrganizationMembership(user_id=user.id, organization_id=organization_id, role_code=role,
                                        status=MembershipStatus.ACTIVE, accepted_at=datetime.now(timezone.utc))
    session.add(membership); session.commit()
    return AuthorizationContext(user_id=user.id, organization_id=organization_id, membership_id=membership.id, role=role,
                                permissions=ROLE_PERMISSIONS[role])


def agent_round(session, decider=None, now=None) -> dict:
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    result = worker.run_once(factory, now=now, decider=decider)
    session.expire_all()
    return result


def task_for(session, requirement_id) -> RecoveryTask | None:
    return session.scalar(select(RecoveryTask).where(RecoveryTask.requirement_id == requirement_id)
                          .order_by(RecoveryTask.created_at.desc()).limit(1))


def pending(session, requirement_id) -> RecoveryProposal:
    proposal = session.scalar(select(RecoveryProposal).where(RecoveryProposal.requirement_id == requirement_id,
                                                             RecoveryProposal.status == ProposalStatus.PENDING))
    assert proposal is not None, "no pending recovery proposal"
    return proposal


def approve(session, requirement_id, *actors, run: bool = True) -> RecoveryProposal:
    proposal = pending(session, requirement_id)
    for actor in actors:
        decide(session, actor, proposal.id, proposal.content_hash, True, "approved in test")
        session.commit()
    if run:
        agent_round(session)
    session.refresh(proposal)
    return proposal
