"""Human approval of an exact recovery proposal. Approving records a decision; it never executes anything.

A reviewer submits the hash of the proposal they were shown. The decision is refused when that hash is not the
proposal's, when the stored content no longer matches its own hash, when the proposal is no longer the task's
pending proposal, or when its approval window has passed. Once the proposal's tier is satisfied (see
policy.satisfied) the task moves to EXECUTING and the gateway, in the worker, executes it after re-verifying.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.agents.application.policy import content_hash, satisfied
from src.backend.app.agents.application.timeline import add_step, agent_event, current_proposal
from src.backend.app.agents.domain.models import (
    ApprovalTier, ProposalStatus, RecoveryApproval, RecoveryProposal, RecoveryTask, StepKind, TaskStatus,
)
from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.permissions import PermissionCode

FRESH = {"populate_existing": True}


class ApprovalError(ValueError):
    """Conflicts with the proposal's state (HTTP 409)."""


class ApprovalForbidden(PermissionError):
    """The reviewer may not make this decision (HTTP 403)."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def approvals_of(session: Session, proposal_id: UUID) -> list[RecoveryApproval]:
    return session.scalars(select(RecoveryApproval).where(RecoveryApproval.proposal_id == proposal_id)
                           .order_by(RecoveryApproval.decided_at)).all()


def decide(session: Session, actor: AuthorizationContext, proposal_id: UUID, proposal_hash: str, approve: bool,
           note: str | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if PermissionCode.RECOVERY_APPROVE not in actor.permissions:
        raise ApprovalForbidden("approving recovery requires the recovery.approve permission")
    if not approve and not (note and len(note.strip()) >= 3):
        raise ApprovalError("a rejection needs a reason")
    proposal = session.scalar(select(RecoveryProposal).where(RecoveryProposal.id == proposal_id).with_for_update().execution_options(**FRESH))
    if proposal is None or proposal.organization_id != actor.organization_id:
        raise ApprovalError("proposal not found")
    task = session.scalar(select(RecoveryTask).where(RecoveryTask.id == proposal.task_id).with_for_update().execution_options(**FRESH))
    if proposal.status != ProposalStatus.PENDING:
        raise ApprovalError(f"this proposal is {proposal.status.value.lower()}; review the current proposal")
    if current_proposal(session, task).id != proposal.id or task.status != TaskStatus.AWAITING_APPROVAL:
        raise ApprovalError("this proposal is no longer the task's pending proposal")
    if proposal_hash != proposal.content_hash:
        raise ApprovalError("the proposal you reviewed is not the current version; reload and review it again")
    if content_hash(proposal.content) != proposal.content_hash:
        raise ApprovalError("the stored proposal does not match its hash; it cannot be approved")
    if _aware(proposal.expires_at) <= now:
        task.next_run_at = now  # let the orchestrator re-plan
        raise ApprovalError("the approval window for this proposal has passed; a new proposal will be prepared")
    earlier = approvals_of(session, proposal.id)
    if any(a.reviewer_user_id == actor.user_id for a in earlier):
        raise ApprovalError("you have already decided this proposal")
    elevated = PermissionCode.RECOVERY_APPROVE_ELEVATED in actor.permissions
    if approve and proposal.tier == ApprovalTier.ELEVATED and earlier and not elevated \
            and not any(a.elevated for a in earlier if a.decision == "APPROVED"):
        raise ApprovalForbidden("this proposal needs a procurement manager or organization administrator to approve it")

    record = RecoveryApproval(proposal_id=proposal.id, organization_id=proposal.organization_id, proposal_hash=proposal_hash,
                              decision="APPROVED" if approve else "REJECTED", reviewer_user_id=actor.user_id,
                              reviewer_membership_id=actor.membership_id, reviewer_role=actor.role.value, elevated=elevated,
                              note=(note or "").strip()[:1000] or None, decided_at=now)
    session.add(record)
    session.flush()
    who = str(actor.user_id)
    if not approve:
        proposal.status, proposal.status_reason, proposal.decided_at = ProposalStatus.REJECTED, record.note, now
        task.status, task.next_run_at = TaskStatus.QUEUED, now
        add_step(session, task, StepKind.REJECTION, who, f"Proposal v{proposal.version} rejected: {record.note}",
                 {"role": actor.role.value}, proposal.id)
        agent_event(session, task, "recovery.rejected", {"proposal_id": str(proposal.id), "reason": record.note,
                                                         "reviewer_user_id": who}, actor=who)
        return {"proposal_id": str(proposal.id), "status": proposal.status.value, "task_status": task.status.value}

    valid = [(a.reviewer_user_id, a.elevated) for a in approvals_of(session, proposal.id) if a.decision == "APPROVED"]
    complete = satisfied(proposal.tier, valid)
    add_step(session, task, StepKind.APPROVAL, who,
             f"Proposal v{proposal.version} approved by {actor.role.value.replace('_', ' ').lower()}"
             + ("" if complete else "; a second approval with elevated authority is still required"),
             {"role": actor.role.value, "elevated": elevated, "hash": proposal_hash}, proposal.id)
    agent_event(session, task, "recovery.approval_recorded", {"proposal_id": str(proposal.id), "reviewer_user_id": who,
                                                              "role": actor.role.value, "complete": complete}, actor=who)
    if complete:
        proposal.status, proposal.decided_at = ProposalStatus.APPROVED, now
        task.status, task.next_run_at = TaskStatus.EXECUTING, now
        agent_event(session, task, "recovery.approved", {"proposal_id": str(proposal.id), "hash": proposal_hash,
                                                         "approvers": [str(user) for user, _ in valid]}, actor=who)
    return {"proposal_id": str(proposal.id), "status": proposal.status.value, "task_status": task.status.value,
            "approvals": len(valid), "complete": complete}
