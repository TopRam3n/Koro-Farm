"""The recovery gateway: the only path from an approved proposal to a change in supply. Run by the worker.

Before anything is applied, `execute` re-verifies independently of the approval step:
1. the proposal is APPROVED, its stored content still hashes to its hash, and every approval names that hash;
2. each approver is still an active member of the organization whose current role still grants the authority
   counted for them, and the remaining valid approvals still satisfy the tier;
3. the tier is re-evaluated under the organization's current cost policy (a tightened tolerance can require
   elevated approval that was not obtained);
4. the approval window has not passed and the order is not cancelled;
5. under row locks (lots, then allocations, in id order) every action's preconditions hold now: standby still
   authorized with the same consent and enough supported quantity, lots still eligible with enough free stock, no
   open request already on the lot, exposed quantities unchanged, and replacements no larger than the current need.
Any failure refuses the whole proposal as STALE (nothing applied) and the task re-plans.

Actions then apply one by one, each in its own savepoint with an execution record (unique per proposal action),
so a failure leaves earlier actions applied and recorded and the outcome is reported truthfully as PARTIAL.
`_activate_standby`, `_solicit_supply` and `_release_exposed` require a verified `Authority` and are not used
anywhere else; no API, worker or legacy caller can activate standby without an approved proposal.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.agents.application import evidence as ev
from src.backend.app.agents.application.policy import content_hash, current_policy, evaluate, policy_snapshot, satisfied
from src.backend.app.agents.application.timeline import GATEWAY, add_step, agent_event
from src.backend.app.agents.domain.models import (
    ApprovalTier, ProposalStatus, RecoveryApproval, RecoveryExecution, RecoveryProposal, RecoveryTask, StepKind, TaskStatus,
)
from src.backend.app.assurance.application.exceptions import sync_capacity_exception
from src.backend.app.assurance.application.recovery import _coverage, _create_recovery_snapshot, _event
from src.backend.app.assurance.domain.models import RecoveryRun, RecoveryStatus
from src.backend.app.demand.domain.models import Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.identity.domain.models import MembershipStatus, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import ROLE_PERMISSIONS, PermissionCode
from src.backend.app.supply.application.capacity import free_kg, lot_exposure, refresh_lot_status
from src.backend.app.supply.application.commitments import solicit
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, ConsentStatus, SupplyAllocation, SupplyPlan,
)

FRESH = {"populate_existing": True}


class StaleProposal(Exception):
    pass


@dataclass(frozen=True)
class Authority:
    """Proof, for this transaction, that the gateway verified an approved proposal."""
    proposal: RecoveryProposal
    approvers: tuple[str, ...]


@dataclass(frozen=True)
class GatewayActor:
    """Attribution for commands the gateway runs (record_event reads user_id and organization_id)."""
    user_id: str
    organization_id: UUID


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _valid_approvals(session: Session, proposal: RecoveryProposal) -> tuple[list[tuple[UUID, bool]], list[str]]:
    valid, problems = [], []
    for approval in session.scalars(select(RecoveryApproval).where(RecoveryApproval.proposal_id == proposal.id,
                                                                    RecoveryApproval.decision == "APPROVED")):
        if approval.proposal_hash != proposal.content_hash:
            problems.append("an approval names a different proposal hash")
            continue
        membership = session.get(OrganizationMembership, approval.reviewer_membership_id)
        user = session.get(UserAccount, approval.reviewer_user_id)
        if (membership is None or user is None or not user.active or membership.status != MembershipStatus.ACTIVE
                or membership.user_id != approval.reviewer_user_id or membership.organization_id != proposal.organization_id):
            problems.append("an approver is no longer an active member of the organization")
            continue
        permissions = ROLE_PERMISSIONS[membership.role_code]
        if PermissionCode.RECOVERY_APPROVE not in permissions:
            problems.append("an approver's current role no longer grants recovery approval")
            continue
        valid.append((approval.reviewer_user_id, approval.elevated and PermissionCode.RECOVERY_APPROVE_ELEVATED in permissions))
    return valid, problems


def verify(session: Session, proposal: RecoveryProposal, requirement: Requirement, now: datetime) -> Authority:
    if proposal.status != ProposalStatus.APPROVED:
        raise StaleProposal(f"proposal is {proposal.status.value}, not approved")
    if content_hash(proposal.content) != proposal.content_hash:
        raise StaleProposal("stored proposal content does not match its hash")
    if _aware(proposal.expires_at) <= now:
        raise StaleProposal("the approval window expired before execution")
    if requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
        raise StaleProposal("the order was cancelled")
    valid, problems = _valid_approvals(session, proposal)
    content = proposal.content
    policy = policy_snapshot(current_policy(session, proposal.organization_id))
    tier = proposal.tier
    if policy["version"] != content["approval"]["policy"]["version"]:
        current_tier, _ = evaluate(content["cost"], policy, bool(content["actions"]))
        if current_tier == ApprovalTier.ELEVATED:
            tier = ApprovalTier.ELEVATED
    if not satisfied(tier, valid):
        raise StaleProposal("; ".join(problems) or f"the approvals no longer satisfy {tier.value.lower()} approval")
    return Authority(proposal=proposal, approvers=tuple(str(user) for user, _ in valid))


def _lock_rows(session: Session, actions: list[dict]):
    lot_ids = sorted({UUID(a["production_lot_id"]) for a in actions if a.get("production_lot_id")}, key=str)
    allocation_ids = sorted({UUID(a["allocation_id"]) for a in actions if a.get("allocation_id")}, key=str)
    lots = {lot.id: lot for lot in session.scalars(select(ProductionLot).where(ProductionLot.id.in_(lot_ids))
                                                   .order_by(ProductionLot.id).with_for_update().execution_options(**FRESH))}
    allocations = {a.id: a for a in session.scalars(select(SupplyAllocation).where(SupplyAllocation.id.in_(allocation_ids))
                                                    .order_by(SupplyAllocation.id).with_for_update().execution_options(**FRESH))}
    return lots, allocations


def check_preconditions(session: Session, proposal: RecoveryProposal, requirement: Requirement, lots: dict,
                        allocations: dict, today: date) -> list[str]:
    content, problems = proposal.content, []
    basis, by_allocation = ev.basis_of(session, requirement)
    replacement = sum((Decimal(a["quantity_kg"]) for a in content["actions"]
                       if a["type"] in (ev.ACTIVATE_STANDBY, ev.SOLICIT_SUPPLY)), Decimal("0"))
    if replacement > basis.net_need_kg:
        problems.append(f"the order now needs {ev.kg(basis.net_need_kg)} kg, less than the {ev.kg(replacement)} kg proposed")
    exposures: dict[UUID, object] = {}
    from src.backend.app.agents.application import releases as rel
    from src.backend.app.supply.application.release import releasable_kg
    policy = policy_snapshot(current_policy(session, proposal.organization_id))
    for action in content["actions"]:
        quantity = Decimal(action["quantity_kg"])
        who = action["farmer_name"]
        if action["type"] == rel.CANCEL_ORDER:
            from src.backend.app.fulfilment.domain.models import ReceivedSublot
            ids = select(SupplyAllocation.id).where(SupplyAllocation.requirement_id == requirement.id)
            received_any = session.scalar(select(func.count(ReceivedSublot.id)).where(ReceivedSublot.allocation_id.in_(ids))) or 0
            if requirement.lifecycle_status in (RequirementLifecycleStatus.CANCELLED, RequirementLifecycleStatus.COMPLETED,
                                                RequirementLifecycleStatus.CLOSED_WITH_VARIANCE):
                problems.append("the order has already ended")
            elif (action["mode"] == "FULL") != (received_any == 0):
                problems.append("goods were received since the proposal was made; it must be re-planned")
            continue
        if action["type"] in (rel.RELEASE_COMMITMENT, rel.RELEASE_STANDBY, rel.WITHDRAW_REQUEST):
            allocation = allocations.get(UUID(action["allocation_id"]))
            expected = {rel.RELEASE_COMMITMENT: (AllocationStatus.COMMITTED,), rel.RELEASE_STANDBY: (AllocationStatus.STANDBY,),
                        rel.WITHDRAW_REQUEST: (AllocationStatus.PROPOSED, AllocationStatus.SOLICITED)}[action["type"]]
            if allocation is None or allocation.requirement_id != requirement.id or allocation.status not in expected:
                problems.append(f"{who}'s allocation changed state")
                continue
            if action["type"] != rel.WITHDRAW_REQUEST and releasable_kg(session, allocation) < quantity:
                problems.append(f"{who}'s undelivered reservation is now {ev.kg(releasable_kg(session, allocation))} kg, not {action['quantity_kg']} kg")
            if action["type"] == rel.RELEASE_COMMITMENT:
                # Re-checked under the current policy and agreements: a withdrawn right or agreement makes it stale.
                allowed, why = rel.release_permitted(session, allocation, quantity, policy)
                if not allowed:
                    problems.append(f"releasing {who}'s commitment is no longer permitted: {why}")
            continue
        lot = lots.get(UUID(action["production_lot_id"]))
        if lot is None:
            problems.append(f"{who}'s lot no longer exists")
            continue
        if action["type"] == ev.ACTIVATE_STANDBY:
            allocation = allocations.get(UUID(action["allocation_id"]))
            if (allocation is None or allocation.requirement_id != requirement.id or allocation.status != AllocationStatus.STANDBY
                    or allocation.consent_status != ConsentStatus.RECORDED):
                problems.append(f"{who}'s standby is no longer authorized")
                continue
            if str(allocation.consent_evidence_id) != str(action["consent_id"]):
                problems.append(f"{who}'s standby consent record changed")
            bound = action["authorization_valid_until"]
            current = allocation.authorization_valid_until.isoformat() if allocation.authorization_valid_until else None
            if current != bound or (allocation.authorization_valid_until is not None and allocation.authorization_valid_until < today):
                problems.append(f"{who}'s standby authorization period changed or ended")
            if lot.reverification_required or lot.status == ProductionLotStatus.EXHAUSTED:
                problems.append(f"{who}'s lot is excluded from new commitments until its capacity is re-verified")
            if lot.id not in exposures:
                exposures[lot.id] = lot_exposure(session, lot)
            supported = allocation.obligation_kg - exposures[lot.id].standby_uncovered.get(allocation.id, Decimal("0"))
            if supported < quantity:
                problems.append(f"{who}'s standby now supports {ev.kg(max(supported, Decimal('0')))} kg, not {action['quantity_kg']} kg")
        elif action["type"] == ev.SOLICIT_SUPPLY:
            farmer = session.get(Farmer, lot.farmer_id)
            open_request = session.scalar(select(SupplyAllocation.id).where(
                SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.production_lot_id == lot.id,
                SupplyAllocation.status.in_([AllocationStatus.PROPOSED, AllocationStatus.SOLICITED])).limit(1))
            if farmer is None or farmer.organization_id != proposal.organization_id:
                problems.append(f"{who} is not a supplier of this organization")
            elif (lot.status != ProductionLotStatus.AVAILABLE or lot.crop != requirement.crop or lot.quality_grade_estimate != requirement.grade
                  or lot.harvest_start > requirement.delivery_window_end or lot.harvest_end < requirement.delivery_window_start):
                problems.append(f"{who}'s lot is no longer eligible for this order")
            elif free_kg(lot) < quantity:
                problems.append(f"{who}'s lot now has {ev.kg(free_kg(lot))} kg free, not {action['quantity_kg']} kg")
            elif lot.reverification_required:
                problems.append(f"{who}'s lot needs its capacity re-verified before it is offered again")
            elif open_request is not None:
                problems.append(f"{who} already has an open request for this order")
        elif action["type"] == ev.RELEASE_EXPOSED:
            item = by_allocation.get(UUID(action["allocation_id"]))
            if item is None or item.allocation.status != AllocationStatus.COMMITTED or item.exposed_kg < quantity:
                problems.append(f"{who}'s exposed commitment changed")
    return problems


# --- Actions (verified authority required) --------------------------------------------------------------------

def _require(authority: Authority, action: dict) -> None:
    if not isinstance(authority, Authority) or authority.proposal.status != ProposalStatus.APPROVED \
            or action not in authority.proposal.content["actions"]:
        raise PermissionError("recovery actions run only from a verified, approved proposal")


def _provenance(authority: Authority, index: int) -> dict:
    return {"proposal_id": str(authority.proposal.id), "proposal_hash": authority.proposal.content_hash,
            "action_index": index, "approved_by": list(authority.approvers)}


def _activate_standby(session: Session, authority: Authority, index: int, action: dict, requirement: Requirement,
                      allocations: dict, now: datetime) -> dict:
    _require(authority, action)
    standby = allocations[UUID(action["allocation_id"])]
    quantity = Decimal(action["quantity_kg"])
    # The lot holds one reservation: it moves from the standby row to the new commitment row, never both.
    if quantity == standby.obligation_kg:
        standby.status, standby.activated_at, standby.holds_reservation = AllocationStatus.ACTIVATED, now, False
    else:
        standby.quantity_kg -= quantity
    committed = SupplyAllocation(requirement_id=requirement.id, supply_plan_id=standby.supply_plan_id,
                                 production_lot_id=standby.production_lot_id, role=AllocationRole.COMMITTED,
                                 status=AllocationStatus.COMMITTED, quantity_kg=quantity,
                                 consent_evidence_id=standby.consent_evidence_id, consent_status=standby.consent_status,
                                 holds_reservation=True, plan_version=standby.plan_version, activated_at=now)
    session.add(committed)
    session.flush()
    _event(session, "allocation.standby_activated", requirement.id, authority.proposal.id,
           {"source_allocation_id": str(standby.id), "allocation_id": str(committed.id), "quantity_kg": action["quantity_kg"],
            "consent_id": action["consent_id"], **_provenance(authority, index)})
    return {"allocation_id": str(committed.id), "quantity_kg": action["quantity_kg"]}


def _solicit_supply(session: Session, authority: Authority, index: int, action: dict, requirement: Requirement,
                    now: datetime) -> dict:
    _require(authority, action)
    plan_id = session.scalar(select(SupplyPlan.id).where(SupplyPlan.requirement_id == requirement.id)
                             .order_by(SupplyPlan.plan_version.desc()).limit(1))
    allocation = SupplyAllocation(requirement_id=requirement.id, supply_plan_id=plan_id,
                                  production_lot_id=UUID(action["production_lot_id"]), role=AllocationRole.COMMITTED,
                                  status=AllocationStatus.PROPOSED, quantity_kg=Decimal(action["quantity_kg"]),
                                  consent_status=ConsentStatus.NONE, holds_reservation=False, plan_version=requirement.plan_version)
    session.add(allocation)
    session.flush()
    actor = GatewayActor(user_id=GATEWAY, organization_id=authority.proposal.organization_id)
    result = solicit(session, actor, allocation.id, action["message"], f"recovery:{authority.proposal.id}:{index}",
                     respond_within_hours=action["respond_within_hours"], now=now, actor_type="agent")
    return {"allocation_id": str(allocation.id), "response_due_at": result["response_due_at"],
            "note": "a request only; it counts as supply once the supplier accepts"}


def _release_exposed(session: Session, authority: Authority, index: int, action: dict, requirement: Requirement,
                     lots: dict, allocations: dict, now: datetime) -> dict:
    """Release the part of a commitment the supplier can no longer supply (capacity cut or changed eligibility).
    The agreed quantity stays on record; only the reservation is released."""
    from src.backend.app.supply.application.release import release, received_kg
    _require(authority, action)
    allocation = allocations[UUID(action["allocation_id"])]
    quantity = Decimal(action["quantity_kg"])
    kind = "ineligible" if action.get("cause") == "eligibility" else "capacity_exposure"
    release(session, allocation, quantity, kind=kind, reason=action["reason"], actor_id=GATEWAY, actor_type="agent",
            organization_id=authority.proposal.organization_id, correlation_id=authority.proposal.id,
            detail=_provenance(authority, index))
    if allocation.obligation_kg <= 0 and received_kg(session, allocation.id) == 0:
        allocation.status, allocation.lost_at = AllocationStatus.LOST, now
    _event(session, "allocation.capacity_released", requirement.id, authority.proposal.id,
           {"allocation_id": str(allocation.id), "quantity_kg": action["quantity_kg"], "reason": action["reason"],
            **_provenance(authority, index)})
    return {"allocation_id": str(allocation.id), "released_kg": action["quantity_kg"]}


def _release_commitment(session: Session, authority: Authority, index: int, action: dict, allocations: dict, now: datetime) -> dict:
    from src.backend.app.supply.application.release import release
    _require(authority, action)
    allocation = allocations[UUID(action["allocation_id"])]
    release(session, allocation, Decimal(action["quantity_kg"]), kind=action["release_kind"], reason=action["reason"],
            actor_id=GATEWAY, actor_type="agent", organization_id=authority.proposal.organization_id,
            correlation_id=authority.proposal.id, detail={**_provenance(authority, index), "permitted_by": action["release_permitted_by"]})
    if allocation.obligation_kg <= 0:
        allocation.status = AllocationStatus.RELEASED
    return {"allocation_id": str(allocation.id), "released_kg": action["quantity_kg"]}


def _release_standby(session: Session, authority: Authority, index: int, action: dict, allocations: dict) -> dict:
    from src.backend.app.supply.application.release import release
    _require(authority, action)
    allocation = allocations[UUID(action["allocation_id"])]
    kind = "standby_unused" if action["release_kind"] == "cancellation" else "approved_partial"
    release(session, allocation, Decimal(action["quantity_kg"]), kind=kind, reason=action["reason"], actor_id=GATEWAY,
            actor_type="agent", organization_id=authority.proposal.organization_id, correlation_id=authority.proposal.id,
            detail=_provenance(authority, index))
    if allocation.obligation_kg <= 0:
        allocation.status = AllocationStatus.RELEASED
    return {"allocation_id": str(allocation.id), "released_kg": action["quantity_kg"]}


def _withdraw_request(session: Session, authority: Authority, index: int, action: dict, allocations: dict) -> dict:
    from src.backend.app.supply.application.release import release_remaining
    _require(authority, action)
    allocation = allocations[UUID(action["allocation_id"])]
    release_remaining(session, allocation, kind="request_withdrawn", reason=action["reason"], actor_id=GATEWAY,
                      actor_type="agent", organization_id=authority.proposal.organization_id, correlation_id=authority.proposal.id)
    allocation.status = AllocationStatus.WITHDRAWN
    return {"allocation_id": str(allocation.id), "status": "WITHDRAWN"}


def _cancel_order(session: Session, authority: Authority, index: int, action: dict, requirement: Requirement, now: datetime) -> dict:
    from src.backend.app.agents.application.orchestrator import close_tasks_for_order
    _require(authority, action)
    payload = {"mode": action["mode"], "reason": action["reason"], "buyer_instruction": action.get("buyer_instruction"),
               "requested_by": action.get("requested_by"), "attribution": "BUYER_CANCELLATION", **_provenance(authority, index)}
    if action["mode"] == "FULL":
        requirement.lifecycle_status = RequirementLifecycleStatus.CANCELLED
        requirement.cancelled_at, requirement.cancellation_reason = now, action["reason"][:500]
        requirement.version += 1
        _event(session, "requirement.cancelled", requirement.id, authority.proposal.id, payload)
        from src.backend.app.assurance.application.exceptions import resolve_for_ended_order
        resolve_for_ended_order(session, requirement, GATEWAY, "cancelled at the buyer's instruction")
    else:
        # Goods were received: only undelivered obligations end here. The order stays open for reconciliation,
        # dispute or return handling, and closes with an accepted variance (reconciliation/application/services.py).
        _event(session, "order.remainder_cancelled", requirement.id, authority.proposal.id, payload)
    close_tasks_for_order(session, requirement.id, "the approved cancellation was applied", GATEWAY)
    return {"requirement_id": str(requirement.id), "mode": action["mode"]}


# --- Execution ------------------------------------------------------------------------------------------------

def _refuse(session: Session, task: RecoveryTask, proposal: RecoveryProposal, reasons: list[str], now: datetime) -> None:
    reason = "; ".join(reasons)[:500]
    proposal.status, proposal.status_reason, proposal.decided_at = ProposalStatus.STALE, reason, now
    task.status, task.next_run_at = TaskStatus.QUEUED, now
    add_step(session, task, StepKind.EXECUTE, GATEWAY, f"Approved proposal v{proposal.version} refused, nothing applied: {reason}",
             {"reasons": reasons}, proposal.id)
    agent_event(session, task, "recovery.approval_stale", {"proposal_id": str(proposal.id), "reasons": reasons}, actor=GATEWAY)


def _ensure_run(session: Session, requirement: Requirement, task: RecoveryTask, basis: ev.Basis) -> RecoveryRun:
    run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id,
                                                   RecoveryRun.status == RecoveryStatus.RUNNING).with_for_update())
    if run is None:
        run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == requirement.id,
                                                       RecoveryRun.status == RecoveryStatus.ESCALATED)
                             .order_by(RecoveryRun.created_at.desc()).limit(1).with_for_update())
        if run is not None:
            run.status, run.active_key, run.completed_at = RecoveryStatus.RUNNING, "RUNNING", None
    if run is None:
        run = RecoveryRun(requirement_id=requirement.id, status=RecoveryStatus.RUNNING, active_key="RUNNING",
                          lost_quantity_kg=basis.gap_kg, cause=f"recovery task {str(task.id)[:8]}", remaining_shortfall_kg=basis.gap_kg)
        session.add(run)
        session.flush()
    return run


def execute(session: Session, task: RecoveryTask, proposal: RecoveryProposal, requirement: Requirement, now: datetime) -> None:
    try:
        authority = verify(session, proposal, requirement, now)
    except StaleProposal as exc:
        _refuse(session, task, proposal, [str(exc)], now)
        return
    actions = proposal.content["actions"]
    lots, allocations = _lock_rows(session, actions)
    problems = check_preconditions(session, proposal, requirement, lots, allocations, now.date())
    if problems:
        _refuse(session, task, proposal, problems, now)
        return

    basis, _ = ev.basis_of(session, requirement)
    run = _ensure_run(session, requirement, task, basis)
    applied = failed = 0
    activated = Decimal("0")
    for index, action in enumerate(actions):
        if session.scalar(select(RecoveryExecution.id).where(RecoveryExecution.proposal_id == proposal.id,
                                                             RecoveryExecution.action_index == index)) is not None:
            continue  # already applied in an earlier, committed attempt
        try:
            with session.begin_nested():
                if action["type"] == ev.ACTIVATE_STANDBY:
                    detail = _activate_standby(session, authority, index, action, requirement, allocations, now)
                    activated += Decimal(action["quantity_kg"])
                elif action["type"] == ev.SOLICIT_SUPPLY:
                    detail = _solicit_supply(session, authority, index, action, requirement, now)
                elif action["type"] == ev.RELEASE_EXPOSED:
                    detail = _release_exposed(session, authority, index, action, requirement, lots, allocations, now)
                elif action["type"] == "RELEASE_COMMITMENT":
                    detail = _release_commitment(session, authority, index, action, allocations, now)
                elif action["type"] == "RELEASE_STANDBY":
                    detail = _release_standby(session, authority, index, action, allocations)
                elif action["type"] == "WITHDRAW_REQUEST":
                    detail = _withdraw_request(session, authority, index, action, allocations)
                elif action["type"] == "CANCEL_ORDER":
                    detail = _cancel_order(session, authority, index, action, requirement, now)
                else:
                    raise ValueError(f"unknown action type {action['type']}")
                session.add(RecoveryExecution(proposal_id=proposal.id, organization_id=proposal.organization_id,
                                              action_index=index, action_type=action["type"], outcome="APPLIED", detail=detail,
                                              executed_at=now))
                session.flush()
            applied += 1
        except Exception as exc:  # recorded truthfully; earlier actions stay applied
            failed += 1
            session.add(RecoveryExecution(proposal_id=proposal.id, organization_id=proposal.organization_id, action_index=index,
                                          action_type=action["type"], outcome="FAILED",
                                          detail={"error": f"{type(exc).__name__}: {exc}"[:500]}, executed_at=now))
            session.flush()

    session.flush()
    covered = _coverage(session, requirement.id)
    after, _ = ev.basis_of(session, requirement)
    run.standby_activated_kg += activated
    run.remaining_shortfall_kg = after.gap_kg
    if activated > 0 and covered > 0:
        _create_recovery_snapshot(session, requirement)  # new immutable cost and risk record for the changed mix
    # Sessions run without autoflush, and the next call re-reads the order under lock (populate_existing):
    # write pending changes first so the re-read cannot discard them.
    session.flush()
    sync_capacity_exception(session, requirement.id)  # released exposure closes the capacity exception
    if after.gap_kg <= 0:
        requirement.supply_health = SupplyHealth.COVERED
    elif after.in_flight_kg > 0 and after.net_need_kg <= 0:
        requirement.supply_health = SupplyHealth.RECOVERING
    proposal.status = ProposalStatus.EXECUTED if failed == 0 else ProposalStatus.PARTIAL
    proposal.decided_at = now
    add_step(session, task, StepKind.EXECUTE, GATEWAY,
             f"Proposal v{proposal.version} executed: {applied} action(s) applied" + (f", {failed} failed" if failed else ""),
             {"applied": applied, "failed": failed, "approved_by": list(authority.approvers), "basis_after": after.as_dict()},
             proposal.id)
    agent_event(session, task, "recovery.applied", {"proposal_id": str(proposal.id), "applied": applied, "failed": failed,
                                                    "standby_activated_kg": ev.kg(activated),
                                                    "remaining_shortfall_kg": ev.kg(after.gap_kg)}, actor=GATEWAY)
    task.status, task.next_run_at = TaskStatus.QUEUED, now  # re-plan from the new position (complete, wait or escalate)
