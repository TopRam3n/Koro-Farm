"""Recovery tasks, proposals and approvals (R1 WP3). Staff only, organization-scoped (enforce_path_scope).

Viewing needs recovery.view; approving or rejecting needs recovery.approve (elevated proposals also need a second
reviewer with recovery.approve_elevated); cancelling a task needs recovery.propose; the cost tolerance needs
approval_policy.manage. There is deliberately no endpoint that executes a proposal: the gateway in the worker does.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.agents.application.approvals import ApprovalError, ApprovalForbidden, approvals_of, decide
from src.backend.app.agents.application.orchestrator import RecoveryError, cancel_task
from src.backend.app.agents.application.policy import current_policy, policy_snapshot
from src.backend.app.agents.domain.models import (
    ACTIVE_TASK_STATUSES, ProposalStatus, RecoveryApprovalPolicy, RecoveryExecution, RecoveryIncident, RecoveryProposal,
    RecoveryStep, RecoveryTask,
)
from src.backend.app.assurance.application.events import record_event
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.models import UserAccount
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session

router = APIRouter(tags=["recovery agent"])
SYSTEM_ACTORS = {"recovery-agent": "Recovery agent", "recovery-gateway": "Recovery gateway"}


class DecisionCommand(BaseModel):
    proposal_hash: str = Field(min_length=64, max_length=64, description="The hash of the proposal you reviewed")
    note: str | None = Field(default=None, max_length=1000)


class RejectCommand(BaseModel):
    proposal_hash: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=3, max_length=1000)


class CancelCommand(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PolicyCommand(BaseModel):
    # Unknown fields are refused, so `commitment_release_without_supplier_consent` cannot be set here: an operational
    # role is not contractual authority. Product-owner decision, R1 WP4 (docs/product/R1_WP4_DECISIONS.md).
    model_config = ConfigDict(extra="forbid")
    max_cost_increase_jmd: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    max_cost_increase_pct: Decimal | None = Field(default=None, ge=0, le=10, max_digits=6, decimal_places=4,
                                                  description="As a fraction: 0.05 is 5%")
    reason: str = Field(min_length=3, max_length=500)


def _names(session: Session, ids: set[str]) -> dict[str, str]:
    uuids = []
    for value in ids:
        try:
            uuids.append(UUID(value))
        except (TypeError, ValueError):
            continue
    if not uuids:
        return {}
    return {str(u.id): u.display_name or u.email for u in session.scalars(select(UserAccount).where(UserAccount.id.in_(uuids)))}


def _label(session: Session, requirement_id: UUID) -> str | None:
    row = session.execute(select(Requirement, Buyer).join(Buyer, Buyer.id == Requirement.buyer_id)
                          .where(Requirement.id == requirement_id)).first()
    return f"{str(row[0].crop).replace('_', ' ')} for {row[1].name}" if row else None


def _proposal(session: Session, proposal: RecoveryProposal, viewer: AuthorizationContext, names: dict) -> dict:
    approvals = approvals_of(session, proposal.id)
    executions = session.scalars(select(RecoveryExecution).where(RecoveryExecution.proposal_id == proposal.id)
                                 .order_by(RecoveryExecution.action_index)).all()
    decided = any(a.reviewer_user_id == viewer.user_id for a in approvals)
    return {
        "id": str(proposal.id), "version": proposal.version, "status": proposal.status.value, "tier": proposal.tier.value,
        "content_hash": proposal.content_hash, "content": proposal.content, "expires_at": proposal.expires_at,
        "created_at": proposal.created_at, "decided_at": proposal.decided_at, "status_reason": proposal.status_reason,
        "approvals": [{"reviewer_user_id": str(a.reviewer_user_id), "reviewer_name": names.get(str(a.reviewer_user_id)),
                       "reviewer_role": a.reviewer_role, "decision": a.decision, "elevated": a.elevated, "note": a.note,
                       "decided_at": a.decided_at} for a in approvals],
        "executions": [{"action_index": e.action_index, "action_type": e.action_type, "outcome": e.outcome,
                        "detail": e.detail, "executed_at": e.executed_at} for e in executions],
        "viewer": {"can_approve": PermissionCode.RECOVERY_APPROVE in viewer.permissions and not decided
                   and proposal.status == ProposalStatus.PENDING,
                   "elevated": PermissionCode.RECOVERY_APPROVE_ELEVATED in viewer.permissions, "already_decided": decided},
    }


def _task(session: Session, task: RecoveryTask, viewer: AuthorizationContext, detail: bool) -> dict:
    proposals = session.scalars(select(RecoveryProposal).where(RecoveryProposal.task_id == task.id)
                                .order_by(RecoveryProposal.version.desc())).all()
    steps = session.scalars(select(RecoveryStep).where(RecoveryStep.task_id == task.id).order_by(RecoveryStep.sequence)).all() if detail else []
    approver_ids = {str(a.reviewer_user_id) for p in proposals for a in approvals_of(session, p.id)}
    names = _names(session, approver_ids | {s.actor for s in steps})
    result = {
        "id": str(task.id), "requirement_id": str(task.requirement_id), "requirement_label": _label(session, task.requirement_id),
        "status": task.status.value, "escalated_kg": str(task.escalated_kg), "terminal_reason": task.terminal_reason,
        "last_error": task.last_error, "attempts": task.attempts, "created_at": task.created_at, "updated_at": task.updated_at,
        "closed_at": task.closed_at,
        "current_proposal": _proposal(session, proposals[0], viewer, names) if proposals else None,
    }
    if detail:
        incidents = session.scalars(select(RecoveryIncident).where(RecoveryIncident.task_id == task.id)
                                    .order_by(RecoveryIncident.recorded_at)).all()
        result["incidents"] = [{"kind": i.kind, "quantity_kg": str(i.quantity_kg), "summary": i.summary,
                                "exception_id": str(i.exception_id) if i.exception_id else None, "recorded_at": i.recorded_at}
                               for i in incidents]
        result["steps"] = [{"sequence": s.sequence, "kind": s.kind.value, "actor": s.actor, "actor_name": names.get(s.actor) or SYSTEM_ACTORS.get(s.actor, s.actor),
                            "summary": s.summary, "detail": s.detail, "proposal_id": str(s.proposal_id) if s.proposal_id else None,
                            "created_at": s.created_at} for s in steps]
        result["proposals"] = [_proposal(session, p, viewer, names) for p in proposals]
    return result


@router.get("/recovery-tasks", dependencies=[Depends(require_permission(PermissionCode.RECOVERY_VIEW))])
def list_tasks(state: str = Query("active", pattern="^(active|all)$"), requirement_id: UUID | None = None,
               session: Session = Depends(get_session),
               context: AuthorizationContext = Depends(get_authorization_context)) -> list[dict]:
    statement = select(RecoveryTask).where(RecoveryTask.organization_id == context.organization_id)
    if state == "active":
        statement = statement.where(RecoveryTask.status.in_(ACTIVE_TASK_STATUSES))
    if requirement_id is not None:
        statement = statement.where(RecoveryTask.requirement_id == requirement_id)
    tasks = session.scalars(statement.order_by(RecoveryTask.updated_at.desc()).limit(100)).all()
    return [_task(session, task, context, detail=requirement_id is not None) for task in tasks]


@router.get("/recovery-tasks/{recovery_task_id}", dependencies=[Depends(require_permission(PermissionCode.RECOVERY_VIEW))])
def get_task(recovery_task_id: UUID, session: Session = Depends(get_session),
             context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _task(session, session.get(RecoveryTask, recovery_task_id), context, detail=True)


@router.post("/recovery-tasks/{recovery_task_id}/cancel", dependencies=[Depends(require_permission(PermissionCode.RECOVERY_PROPOSE))])
def post_cancel(recovery_task_id: UUID, payload: CancelCommand, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    try:
        task = cancel_task(session, context, recovery_task_id, payload.reason)
    except RecoveryError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return {"id": str(task.id), "status": task.status.value}


def _decide(session: Session, context: AuthorizationContext, proposal_id: UUID, proposal_hash: str, approve: bool,
            note: str | None) -> dict:
    try:
        result = decide(session, context, proposal_id, proposal_hash, approve, note)
    except ApprovalForbidden as exc:
        session.rollback()
        raise HTTPException(403, str(exc)) from exc
    except ApprovalError as exc:
        session.commit()  # keeps a re-plan request recorded by an expired-window refusal
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return result


@router.post("/recovery-proposals/{recovery_proposal_id}/approve",
             dependencies=[Depends(require_permission(PermissionCode.RECOVERY_APPROVE))])
def post_approve(recovery_proposal_id: UUID, payload: DecisionCommand, session: Session = Depends(get_session),
                 context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Approve the exact proposal you reviewed. Execution happens afterwards in the gateway, which re-verifies."""
    return _decide(session, context, recovery_proposal_id, payload.proposal_hash, True, payload.note)


@router.post("/recovery-proposals/{recovery_proposal_id}/reject",
             dependencies=[Depends(require_permission(PermissionCode.RECOVERY_APPROVE))])
def post_reject(recovery_proposal_id: UUID, payload: RejectCommand, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return _decide(session, context, recovery_proposal_id, payload.proposal_hash, False, payload.reason)


@router.get("/recovery-approval-policy", dependencies=[Depends(require_permission(PermissionCode.RECOVERY_VIEW))])
def get_policy(session: Session = Depends(get_session), context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    return policy_snapshot(current_policy(session, context.organization_id))


@router.post("/recovery-approval-policy", status_code=201,
             dependencies=[Depends(require_permission(PermissionCode.APPROVAL_POLICY_MANAGE))])
def post_policy(payload: PolicyCommand, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Add a new version of the cost tolerance. Proposals made under an older version are re-checked at execution.
    Leaving both limits empty removes the tolerance: every cost increase then needs elevated approval."""
    previous = current_policy(session, context.organization_id)
    row = RecoveryApprovalPolicy(organization_id=context.organization_id, version=(previous.version if previous else 0) + 1,
                                 max_cost_increase_jmd=payload.max_cost_increase_jmd,
                                 max_cost_increase_pct=payload.max_cost_increase_pct, reason=payload.reason,
                                 set_by_user_id=context.user_id, created_at=datetime.now().astimezone())
    session.add(row)
    session.flush()
    snapshot = policy_snapshot(row)
    record_event(session, context, "recovery.policy_changed", "organization", context.organization_id,
                 {**snapshot, "reason": payload.reason})
    session.commit()
    return snapshot
