"""Test helpers that obtain supplier agreement the only legitimate way: solicit, then record a response.

Older tests were written when planning committed supply directly. They now call these helpers, so every
commitment and standby they rely on is backed by a recorded SupplierConsent (channel COORDINATOR_RELAYED,
attestation "test: phone call with farmer").
"""
from uuid import UUID

from sqlalchemy import select

from src.backend.app.identity.application.authorization import AuthorizationContext
from src.backend.app.identity.domain.models import DEFAULT_ORGANIZATION_ID
from src.backend.app.identity.domain.permissions import ROLE_PERMISSIONS, RoleCode
from src.backend.app.supply.application.commitments import SupplierResponse, respond, solicit
from src.backend.app.supply.application.planner import PlannerConfig, finalize_plan
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, ConsentDecision, SupplyAllocation

TEST_ACTOR = AuthorizationContext(
    user_id=UUID("00000000-0000-0000-0000-00000000c001"), organization_id=DEFAULT_ORGANIZATION_ID,
    membership_id=UUID("00000000-0000-0000-0000-00000000c002"), role=RoleCode.SUPPLY_COORDINATOR,
    permissions=ROLE_PERMISSIONS[RoleCode.SUPPLY_COORDINATOR],
)
ATTESTATION = "test: phone call with farmer"
STANDBY_CONDITIONS = "Test: may be activated only to replace lost committed supply"


def _response(decision: ConsentDecision, standby: bool) -> SupplierResponse:
    return SupplierResponse(decision=decision, attestation_method=ATTESTATION,
                            activation_conditions=STANDBY_CONDITIONS if standby and decision == ConsentDecision.ACCEPTED else None)


def confirm_plan(session, requirement_id, actor: AuthorizationContext = TEST_ACTOR) -> None:
    proposals = session.scalars(select(SupplyAllocation).where(
        SupplyAllocation.requirement_id == requirement_id, SupplyAllocation.status == AllocationStatus.PROPOSED,
    ).order_by(SupplyAllocation.created_at, SupplyAllocation.id)).all()
    for proposal in proposals:
        solicit(session, actor, proposal.id, None, f"test-solicit-{proposal.id}")
        respond(session, actor, proposal.id, _response(ConsentDecision.ACCEPTED, proposal.role == AllocationRole.STANDBY),
                f"test-accept-{proposal.id}")
    # Planning commits its own transaction; commit the recorded responses too so other sessions see them.
    session.commit()


def plan_and_confirm(session, requirement_id, config: PlannerConfig = PlannerConfig(), actor: AuthorizationContext = TEST_ACTOR):
    result = finalize_plan(session, requirement_id, config)
    confirm_plan(session, requirement_id, actor)
    return result


def accept(session, allocation_id, key: str, actor: AuthorizationContext = TEST_ACTOR) -> dict:
    allocation = session.get(SupplyAllocation, allocation_id)
    standby = allocation is not None and allocation.role == AllocationRole.STANDBY
    return respond(session, actor, allocation_id, _response(ConsentDecision.ACCEPTED, standby), key)


def decline(session, allocation_id, key: str, actor: AuthorizationContext = TEST_ACTOR) -> dict:
    return respond(session, actor, allocation_id, _response(ConsentDecision.DECLINED, False), key)


def confirm_plan_via_api(client, requirement_id, headers: dict | None = None) -> None:
    """Solicit and accept every proposal of a planned order through the HTTP API."""
    headers = dict(headers or {})
    assurance = client.get(f"/requirements/{requirement_id}/assurance", headers=headers).json()
    for allocation in assurance["allocations"]:
        if allocation["status"] != "PROPOSED":
            continue
        solicited = client.post(f"/allocations/{allocation['id']}/solicit", json={},
                                headers={**headers, "Idempotency-Key": f"api-solicit-{allocation['id']}"})
        assert solicited.status_code == 200, solicited.text
        body = {"decision": "ACCEPTED", "attestation_method": ATTESTATION}
        if allocation["role"] == "STANDBY":
            body["activation_conditions"] = STANDBY_CONDITIONS
        answered = client.post(f"/allocations/{allocation['id']}/responses", json=body,
                               headers={**headers, "Idempotency-Key": f"api-accept-{allocation['id']}"})
        assert answered.status_code == 200, answered.text
