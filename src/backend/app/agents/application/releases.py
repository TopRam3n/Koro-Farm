"""Approved releases, cancellations and buyer reductions (R1 WP4: P1, P2, P4). Deterministic; no language model.

Three kinds of proposal use the WP3 approval gateway, so a person approves the exact actions and the gateway
re-checks them under row locks before anything changes:

* RELEASE (P2, "earlier partial release"): a coordinator asks to release part of one allocation before close-out.
* CANCELLATION (P1): a coordinator asks to cancel an order. Before any receipt the whole order is cancelled. Once
  goods have been received only undelivered obligations are cancelled and the physical records stay for
  reconciliation; elevated approval is then required.
* Surplus (P4, inside a RECOVERY task): after a buyer reduces the quantity, reductions are proposed latest accepted
  first, allocations already in physical fulfilment last.

Releasing a supplier commitment is never assumed to be the coordinator's right. It needs the supplier's recorded
release agreement for that quantity, unless the organization's approval policy records that its supplier terms
grant the right (`commitment_release_without_supplier_consent`). If neither holds, no proposal is made: the task
escalates and names the suppliers whose agreement is needed. Original commitments stay in history; only the
reservation is released (supply/application/release.py).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.agents.application import evidence as ev
from src.backend.app.agents.application.policy import ApprovalTier, content_hash, current_policy, policy_snapshot
from src.backend.app.agents.application.timeline import AGENT, add_step, agent_event
from src.backend.app.agents.domain.models import ProposalStatus, RecoveryProposal, RecoveryTask, StepKind, TaskStatus
from src.backend.app.demand.domain.models import Requirement
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.supply.application.release import received_kg, releasable_kg
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, ConsentDecision, ConsentType, SupplierConsent, SupplyAllocation,
)

ZERO = Decimal("0")
RELEASE_COMMITMENT = "RELEASE_COMMITMENT"
RELEASE_STANDBY = "RELEASE_STANDBY"
WITHDRAW_REQUEST = "WITHDRAW_REQUEST"
CANCEL_ORDER = "CANCEL_ORDER"
RELEASE_ACTIONS = (RELEASE_COMMITMENT, RELEASE_STANDBY, WITHDRAW_REQUEST, CANCEL_ORDER)


def agreed_release_kg(session: Session, allocation_id: UUID) -> Decimal:
    return session.scalar(select(func.coalesce(func.sum(SupplierConsent.quantity_kg), 0)).where(
        SupplierConsent.allocation_id == allocation_id, SupplierConsent.consent_type == ConsentType.RELEASE_AGREEMENT,
        SupplierConsent.decision == ConsentDecision.ACCEPTED)) or ZERO


def release_permitted(session: Session, allocation: SupplyAllocation, quantity: Decimal, policy: dict) -> tuple[bool, str]:
    """Whether releasing `quantity` of a commitment is allowed without assuming the supplier's consent."""
    if policy.get("commitment_release_without_supplier_consent"):
        return True, f"the organization's supplier terms grant the right to release (policy v{policy['version']})"
    agreed = agreed_release_kg(session, allocation.id)
    if agreed >= (allocation.released_quantity_kg or ZERO) + quantity:
        return True, f"the supplier agreed to release {ev.kg(agreed)} kg"
    return False, f"the supplier has agreed to release {ev.kg(agreed)} kg; {ev.kg(quantity)} kg needs their agreement"


def _describe(session: Session, allocation: SupplyAllocation) -> dict:
    lot = session.get(ProductionLot, allocation.production_lot_id)
    farmer = session.get(Farmer, lot.farmer_id)
    return {"allocation_id": str(allocation.id), "production_lot_id": str(lot.id), "farmer_id": str(farmer.id),
            "farmer_name": farmer.name, "supplier_label": "", "parish": lot.parish}


def _in_fulfilment(session: Session, allocation: SupplyAllocation) -> bool:
    return received_kg(session, allocation.id) > 0


def persist_proposal(session: Session, task: RecoveryTask, requirement: Requirement, *, actions: list[dict], tier: ApprovalTier,
                     reasons: list[str], policy: dict, rationale: str, now: datetime, extra: dict | None = None) -> RecoveryProposal:
    """Write an immutable release-type proposal in the same shape approvers already review."""
    basis, _ = ev.basis_of(session, requirement)
    expires = max(now + timedelta(hours=24), now + timedelta(hours=1))
    version = task.proposals_made + 1
    content = {
        "schema": "release-proposal-v1", "purpose": task.purpose, "task_id": str(task.id), "requirement_id": str(requirement.id),
        "organization_id": str(task.organization_id), "version": version, "created_at": now.isoformat(), "expires_at": expires.isoformat(),
        "request": task.request, "basis": basis.as_dict(), "incidents": [], "options": [], "chosen_option_id": "R",
        "actions": actions, "escalation_kg": "0",
        "cost": {"known": True, "replacement_kg": "0", "total_landed_cost_jmd": None, "baseline_cost_per_kg_jmd": None,
                 "increase_jmd": "0.00", "increase_pct": "0", "unknown_cost_lots": []},
        "commercial_terms": (task.request or {}).get("commercial_consequences") or
                            "Commercial consequences of releasing these obligations are not recorded in KoroFarm; confirm them before approving.",
        "approval": {"tier": tier.value, "reasons": reasons, "policy": policy,
                     "required": "one approver with recovery.approve" if tier == ApprovalTier.ORDINARY
                     else "two different approvers, at least one with recovery.approve_elevated"},
        "decision": {"mode": "deterministic", "model": None, "rationale": rationale, "recommend_escalation": False,
                     "information_requests": [], "violations": [], "fallback_reason": None},
        "drafts": {"buyer": "", "status": "No message is sent. Suppliers see the release in their records."},
        **(extra or {}),
    }
    proposal = RecoveryProposal(task_id=task.id, organization_id=task.organization_id, requirement_id=requirement.id,
                                version=version, status=ProposalStatus.PENDING, tier=tier, content=content,
                                content_hash=content_hash(content), expires_at=expires, created_at=now)
    session.add(proposal)
    session.flush()
    task.proposals_made = version
    task.status, task.next_run_at = TaskStatus.AWAITING_APPROVAL, expires
    add_step(session, task, StepKind.PROPOSE, AGENT, f"{task.purpose.title()} proposal v{version} awaits {tier.value.lower()} approval: "
             f"{len(actions)} action(s)", {"hash": proposal.content_hash, "tier": tier.value, "reasons": reasons}, proposal.id)
    agent_event(session, task, "recovery.proposed", {"proposal_id": str(proposal.id), "version": version, "tier": tier.value,
                                                     "purpose": task.purpose, "hash": proposal.content_hash})
    return proposal


def _commitment_action(session: Session, allocation: SupplyAllocation, quantity: Decimal, kind: str, reason: str,
                       permission: str) -> dict:
    return {"type": RELEASE_COMMITMENT, **_describe(session, allocation), "quantity_kg": ev.kg(quantity),
            "release_kind": kind, "reason": reason, "release_permitted_by": permission,
            "received_kg": ev.kg(received_kg(session, allocation.id)), "commitment_kg": ev.kg(allocation.quantity_kg)}


def _escalate_missing_agreement(session: Session, task: RecoveryTask, missing: list[str], what: str) -> None:
    from src.backend.app.agents.application.orchestrator import escalate_task
    escalate_task(session, task, f"{what} needs supplier agreement first: " + "; ".join(missing))


def plan_release(session: Session, task: RecoveryTask, requirement: Requirement, now: datetime) -> None:
    """An approved partial release of one allocation (P2)."""
    request = task.request or {}
    allocation = session.get(SupplyAllocation, UUID(request["allocation_id"]))
    quantity = Decimal(request["quantity_kg"])
    policy = policy_snapshot(current_policy(session, task.organization_id))
    if allocation is None or allocation.requirement_id != requirement.id:
        _close_failed(session, task, "the allocation is no longer part of this order")
        return
    available = releasable_kg(session, allocation)
    if quantity > available:
        _close_failed(session, task, f"only {ev.kg(available)} kg of this allocation is reserved and undelivered")
        return
    if allocation.status == AllocationStatus.COMMITTED:
        allowed, why = release_permitted(session, allocation, quantity, policy)
        if not allowed:
            _escalate_missing_agreement(session, task, [f"{_describe(session, allocation)['farmer_name']}: {why}"], "this release")
            return
        action = _commitment_action(session, allocation, quantity, "approved_partial", request["reason"], why)
    elif allocation.status == AllocationStatus.STANDBY:
        action = {"type": RELEASE_STANDBY, **_describe(session, allocation), "quantity_kg": ev.kg(quantity),
                  "release_kind": "approved_partial", "reason": request["reason"]}
    else:
        _close_failed(session, task, f"a {allocation.status.value.lower()} allocation holds no releasable reservation")
        return
    tier = ApprovalTier.ELEVATED if _in_fulfilment(session, allocation) else ApprovalTier.ORDINARY
    reasons = ["goods have already been received against this allocation"] if tier == ApprovalTier.ELEVATED else ["release before any receipt"]
    persist_proposal(session, task, requirement, actions=[action], tier=tier, reasons=reasons, policy=policy, now=now,
                     rationale=f"Release {action['quantity_kg']} kg of undelivered reservation as requested: {request['reason']}")


def plan_cancellation(session: Session, task: RecoveryTask, requirement: Requirement, now: datetime) -> None:
    """Cancel an order (P1): everything if nothing was received, otherwise only undelivered obligations."""
    request = task.request or {}
    policy = policy_snapshot(current_policy(session, task.organization_id))
    allocations = session.scalars(select(SupplyAllocation).where(SupplyAllocation.requirement_id == requirement.id)
                                  .order_by(SupplyAllocation.created_at, SupplyAllocation.id)).all()
    received_any = session.scalar(select(func.count(ReceivedSublot.id)).where(
        ReceivedSublot.allocation_id.in_([a.id for a in allocations]))) if allocations else 0
    actions, missing = [], []
    for allocation in allocations:
        quantity = releasable_kg(session, allocation)
        if allocation.status == AllocationStatus.COMMITTED and allocation.role == AllocationRole.COMMITTED and quantity > 0:
            allowed, why = release_permitted(session, allocation, quantity, policy)
            if not allowed:
                missing.append(f"{_describe(session, allocation)['farmer_name']}: {why}")
                continue
            actions.append(_commitment_action(session, allocation, quantity, "cancellation", request["reason"], why))
        elif allocation.status == AllocationStatus.STANDBY and quantity > 0:
            actions.append({"type": RELEASE_STANDBY, **_describe(session, allocation), "quantity_kg": ev.kg(quantity),
                            "release_kind": "cancellation", "reason": request["reason"]})
        elif allocation.status in (AllocationStatus.PROPOSED, AllocationStatus.SOLICITED):
            actions.append({"type": WITHDRAW_REQUEST, **_describe(session, allocation), "quantity_kg": ev.kg(allocation.quantity_kg),
                            "reason": "order cancelled"})
    if missing:
        _escalate_missing_agreement(session, task, missing, "cancelling this order")
        return
    mode = "REMAINDER" if received_any else "FULL"
    actions.append({"type": CANCEL_ORDER, "mode": mode, "production_lot_id": None, "quantity_kg": "0",
                    "farmer_name": "", "supplier_label": "", "parish": "", "reason": request["reason"],
                    "buyer_instruction": request.get("buyer_instruction"), "requested_by": request.get("requested_by")})
    tier = ApprovalTier.ELEVATED if received_any else ApprovalTier.ORDINARY
    reasons = (["goods have already been received: only undelivered obligations are cancelled; physical records stay for reconciliation"]
               if received_any else ["no goods received yet"])
    persist_proposal(session, task, requirement, actions=actions, tier=tier, reasons=reasons, policy=policy, now=now,
                     rationale=("Cancel the order's undelivered obligations at the buyer's instruction" if received_any
                                else "Cancel the order at the buyer's instruction") + f": {request['reason']}")


def plan_surplus(session: Session, task: RecoveryTask, requirement: Requirement, surplus: Decimal, now: datetime) -> bool:
    """Propose reductions after a buyer reduced the quantity (P4). Returns True when a proposal or escalation was made."""
    policy = policy_snapshot(current_policy(session, task.organization_id))
    candidates = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == requirement.id, SupplyAllocation.role == AllocationRole.COMMITTED,
        SupplyAllocation.status == AllocationStatus.COMMITTED)).all()
    # Latest accepted first; anything already in physical fulfilment last.
    ordered = sorted(candidates, key=lambda a: (_in_fulfilment(session, a), -(a.responded_at or a.created_at).timestamp(), str(a.id)))
    actions, missing, remaining = [], [], surplus
    for allocation in ordered:
        if remaining <= 0:
            break
        quantity = min(remaining, releasable_kg(session, allocation))
        if quantity <= 0:
            continue
        allowed, why = release_permitted(session, allocation, quantity, policy)
        if not allowed:
            missing.append(f"{_describe(session, allocation)['farmer_name']}: {why}")
            continue
        actions.append(_commitment_action(session, allocation, quantity, "surplus",
                                          "the buyer reduced the order quantity", why))
        remaining -= quantity
    if missing and not actions:
        _escalate_missing_agreement(session, task, missing, "reducing commitments to the new quantity")
        return True
    if not actions:
        return False
    tier = ApprovalTier.ELEVATED if any(Decimal(a["received_kg"]) > 0 for a in actions) else ApprovalTier.ORDINARY
    reasons = ["the reduction touches an allocation already in physical fulfilment"] if tier == ApprovalTier.ELEVATED else ["no affected allocation has been received yet"]
    rationale = (f"The buyer's change leaves {ev.kg(surplus)} kg committed above the order. Reductions are proposed "
                 "latest accepted first, allocations already in fulfilment last, and only where the supplier agreed or the "
                 "organization's terms grant the right.")
    if missing:
        rationale += " Not proposed (supplier agreement needed): " + "; ".join(missing)
    persist_proposal(session, task, requirement, actions=actions, tier=tier, reasons=reasons, policy=policy, now=now,
                     rationale=rationale, extra={"surplus_kg": ev.kg(surplus), "unresolved_surplus_kg": ev.kg(max(remaining, ZERO))})
    return True


def _close_failed(session: Session, task: RecoveryTask, reason: str) -> None:
    from src.backend.app.agents.application.orchestrator import _close
    _close(session, task, TaskStatus.CANCELLED, f"request cannot proceed: {reason}")
