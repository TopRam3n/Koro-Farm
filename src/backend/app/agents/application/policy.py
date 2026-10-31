"""Approval policy and proposal hashing (deterministic).

Tier rules (R1 WP3, product-owner decision 2):
* ORDINARY - one approver with RECOVERY_APPROVE (supply coordinator and above), when the proposal's cost is known
  and its landed-cost increase over the order's current cost per kg is zero, or within the organization's tolerance;
* ELEVATED - additionally a second, different approver with RECOVERY_APPROVE_ELEVATED (procurement manager or
  organization administrator), when the cost is unknown (a lot has no cost inputs, or the order has no cost
  baseline), when it exceeds a tolerance, or when no tolerance is set and the cost increases at all.
Escalation is never an action and never needs approval.
"""
import hashlib
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.agents.domain.models import ApprovalTier, RecoveryApprovalPolicy


def canonical(content: dict) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(content: dict) -> str:
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def current_policy(session: Session, organization_id: UUID) -> RecoveryApprovalPolicy | None:
    return session.scalar(select(RecoveryApprovalPolicy).where(RecoveryApprovalPolicy.organization_id == organization_id)
                          .order_by(RecoveryApprovalPolicy.version.desc()).limit(1))


def policy_snapshot(policy: RecoveryApprovalPolicy | None) -> dict:
    if policy is None:
        return {"policy_id": None, "version": 0, "max_cost_increase_jmd": None, "max_cost_increase_pct": None}
    return {"policy_id": str(policy.id), "version": policy.version,
            "max_cost_increase_jmd": str(policy.max_cost_increase_jmd) if policy.max_cost_increase_jmd is not None else None,
            "max_cost_increase_pct": str(policy.max_cost_increase_pct) if policy.max_cost_increase_pct is not None else None}


def evaluate(cost: dict, policy: dict, has_actions: bool) -> tuple[ApprovalTier, list[str]]:
    """Return the tier and the reasons, from a proposal's bound cost and policy snapshot."""
    if not has_actions:
        return ApprovalTier.ORDINARY, []
    if not cost["known"]:
        reasons = []
        if cost.get("unknown_cost_lots"):
            reasons.append(f"cost unknown: {len(cost['unknown_cost_lots'])} lot(s) have no cost inputs")
        if cost.get("missing_baseline"):
            reasons.append("cost unknown: the order has no landed-cost baseline to compare against")
        return ApprovalTier.ELEVATED, reasons or ["cost unknown"]
    increase, pct = Decimal(cost["increase_jmd"]), Decimal(cost["increase_pct"])
    if increase <= 0:
        return ApprovalTier.ORDINARY, ["no landed-cost increase"]
    max_jmd, max_pct = policy["max_cost_increase_jmd"], policy["max_cost_increase_pct"]
    if max_jmd is None and max_pct is None:
        return ApprovalTier.ELEVATED, [f"no cost tolerance is set and landed cost rises by J${increase}"]
    reasons = []
    if max_jmd is not None and increase > Decimal(max_jmd):
        reasons.append(f"landed cost rises by J${increase}, above the J${max_jmd} tolerance")
    if max_pct is not None and pct > Decimal(max_pct):
        reasons.append(f"landed cost rises by {pct * 100:.2f}%, above the {Decimal(max_pct) * 100:.2f}% tolerance")
    if reasons:
        return ApprovalTier.ELEVATED, reasons
    return ApprovalTier.ORDINARY, [f"landed cost rises by J${increase}, within tolerance (policy v{policy['version']})"]


def satisfied(tier: ApprovalTier, approvals: list[tuple[UUID, bool]]) -> bool:
    """approvals: (reviewer user id, held RECOVERY_APPROVE_ELEVATED) for each valid APPROVED decision."""
    reviewers = {user for user, _ in approvals}
    if tier == ApprovalTier.ORDINARY:
        return len(reviewers) >= 1
    return len(reviewers) >= 2 and any(elevated for _, elevated in approvals)
