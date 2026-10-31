"""R1 WP3: recovery agent, human approval and the execution gateway.

Runs on SQLite and, when POSTGRES_TEST_DATABASE_URL is set, on PostgreSQL. The model is not involved here: every
test uses the deterministic decider (model behaviour is tested in test_recovery_model.py with scripted clients).
"""
import ast
import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from test_capacity_exceptions import H, commit_all, make_order, open_exceptions, org, report, supply  # noqa: F401
from two_orgs import add_member, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app import worker
from src.backend.app.agents.application import gateway
from src.backend.app.agents.domain.models import (
    ProposalStatus, RecoveryExecution, RecoveryIncident, RecoveryProposal, RecoveryTask, TaskStatus,
)
from src.backend.app.assurance.application.operations import operational_status
from src.backend.app.assurance.domain.exceptions import ExceptionKind
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.demand.domain.models import SupplyHealth, Requirement
from src.backend.app.identity.domain.models import MembershipStatus, OrganizationMembership
from src.backend.app.identity.domain.permissions import PermissionCode, ROLE_PERMISSIONS, RoleCode
from src.backend.app.supply.domain.planning_models import AllocationStatus, SupplyAllocation

D = Decimal
APP = pathlib.Path(__file__).resolve().parents[1] / "app"
PORTAL = {"decision": "ACCEPTED", "attestation_method": "farmer portal"}


@pytest.fixture()
def team(org, factory):
    """The capacity-exceptions organization plus the other people recovery involves."""
    with factory() as session:
        for role, label in ((RoleCode.SUPPLY_COORDINATOR, "second_coordinator"), (RoleCode.PROCUREMENT_MANAGER, "manager"),
                            (RoleCode.ORGANIZATION_ADMIN, "admin"), (RoleCode.WAREHOUSE_OPERATOR, "warehouse")):
            org[label] = add_member(session, org["org"], role, label).id
        session.commit()
    return org


def committed_order(http, org, quantity="300"):
    order = make_order(http, org, quantity)
    commit_all(http, org, order, roles=("COMMITTED", "STANDBY"))
    return order


def committed_rows(http, org, order):
    return [a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED"]


def tasks(http, org, order):
    response = http.get(f"/recovery-tasks?state=all&requirement_id={order['id']}", headers=H(org))
    assert response.status_code == 200, response.text
    return response.json()


def current(http, org, order) -> dict:
    found = tasks(http, org, order)
    assert len(found) == 1, found
    return found[0]


def approve(http, org, order, who="coordinator", proposal=None, expect=200):
    proposal = proposal or current(http, org, order)["current_proposal"]
    response = http.post(f"/recovery-proposals/{proposal['id']}/approve", headers=H(org, who),
                         json={"proposal_hash": proposal["content_hash"], "note": "checked"})
    assert response.status_code == expect, response.text
    return response


def drop(http, org, allocation_id, key="drop"):
    response = http.post(f"/allocations/{allocation_id}/dropout", headers=H(org, key=key), json={"reason": "crop failure"})
    assert response.status_code == 200, response.text
    return response.json()


# --- Role policy (decision 2) --------------------------------------------------------------------------------

def test_recovery_role_policy_is_explicit() -> None:
    approve_, elevated, execute, propose = (PermissionCode.RECOVERY_APPROVE, PermissionCode.RECOVERY_APPROVE_ELEVATED,
                                            PermissionCode.RECOVERY_EXECUTE, PermissionCode.RECOVERY_PROPOSE)
    expected = {
        RoleCode.SUPPLY_COORDINATOR: {approve_, propose},
        RoleCode.PROCUREMENT_MANAGER: {approve_, elevated, propose},
        RoleCode.ORGANIZATION_ADMIN: {approve_, elevated},
        RoleCode.PLATFORM_ADMIN: {approve_, elevated, propose},
        RoleCode.WAREHOUSE_OPERATOR: set(), RoleCode.AUDITOR: set(), RoleCode.FARMER: set(), RoleCode.BUYER: set(),
    }
    for role, granted in expected.items():
        held = {p for p in (approve_, elevated, execute, propose) if p in ROLE_PERMISSIONS[role]}
        assert held == granted, role
    assert not any(execute in permissions for permissions in ROLE_PERMISSIONS.values())  # nobody may execute


# --- Legacy paths are closed, not hidden (decision 1) --------------------------------------------------------

def test_only_the_gateway_can_activate_standby() -> None:
    """Static guard: no module other than the gateway assigns ACTIVATED or builds a committed row from standby."""
    offenders = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.keyword)):
                value = node.value
                if isinstance(value, ast.Tuple):
                    values = value.elts
                else:
                    values = [value]
                for item in values:
                    if isinstance(item, ast.Attribute) and item.attr == "ACTIVATED" and getattr(item.value, "id", "") == "AllocationStatus":
                        offenders.append(str(path.relative_to(APP)))
    assert sorted(set(offenders)) == [str(pathlib.Path("agents/application/gateway.py"))]
    from src.backend.app.assurance.application import recovery
    assert not hasattr(recovery, "continue_recovery") and not hasattr(recovery, "recover_quality_shortfall")


def test_legacy_recovery_endpoints_record_and_queue_but_never_execute(http, team, factory) -> None:
    order = committed_order(http, team)
    before = supply(http, team, order)
    lost = committed_rows(http, team, order)[0]
    refused = http.post(f"/allocations/{lost['id']}/dropout", headers=H(team, key="now"),
                        json={"reason": "crop failure", "defer_recovery": False})
    assert refused.status_code == 422 and "approved recovery proposal" in refused.text
    assert http.post(f"/allocations/{lost['id']}/dropout", headers=H(team, "auditor", key="aud"), json={"reason": "x y z"}).status_code == 403
    result = drop(http, team, lost["id"])
    assert result["standby_activated_kg"] == "0" and result["exception_id"]
    planned = http.post(f"/requirements/{order['id']}/recovery", headers=H(team), json={"note": "please plan"})
    assert planned.status_code == 202, planned.text
    assert http.post(f"/requirements/{order['id']}/recovery", headers=H(team, "auditor"), json={}).status_code == 403
    worker.run_once(factory)
    after = supply(http, team, order)
    assert after["standby_quantity_kg"] == before["standby_quantity_kg"]  # nothing activated without approval
    assert not [a for a in after["allocations"] if a["status"] in ("ACTIVATED", "SOLICITED")]
    task = current(http, team, order)
    assert task["status"] == "AWAITING_APPROVAL" and task["current_proposal"]["status"] == "PENDING"
    kinds = [i["kind"] for i in task["incidents"]]
    assert kinds.count("SUPPLIER_DROPOUT") == 1 and "MANUAL_REQUEST" in kinds  # both joined one task


def test_grading_is_recorded_at_once_and_opens_an_actionable_incident(http, team, factory) -> None:
    order = committed_order(http, team, "200")
    allocation = committed_rows(http, team, order)[0]
    with factory() as session:
        from src.backend.app.fulfilment.domain.models import FulfilmentNode
        node = FulfilmentNode(organization_id=team["org"], name="Packhouse", node_type="PACKHOUSE", parish="St. Ann")
        session.add(node); session.commit()
    received = http.post("/sublots/receive", headers=H(team, "warehouse", key="rcv"), json={
        "allocation_id": allocation["id"], "fulfilment_node_id": str(node.id), "received_quantity_kg": "100",
        "received_at": datetime.now(timezone.utc).isoformat()})
    assert received.status_code == 200, received.text
    sublot = received.json()["received_sublot_id"]
    body = {"accepted_quantity_kg": "75", "rejected_quantity_kg": "25", "assigned_grade": "A", "rejection_reason": "bruising"}
    assert http.post(f"/sublots/{sublot}/grade", headers=H(team, key="g0"), json=body).status_code == 403  # coordinators do not grade
    graded = http.post(f"/sublots/{sublot}/grade", headers=H(team, "warehouse", key="g1"), json=body)
    assert graded.status_code == 200, graded.text
    assert graded.json()["inspection_status"] == "PARTIALLY_ACCEPTED"
    assert graded.json()["recovery"]["standby_activated_kg"] == "0"
    assert [e.kind for e in open_exceptions(factory, order["id"])] == [ExceptionKind.QUALITY_REJECTION]
    worker.run_once(factory)
    task = current(http, team, order)
    assert task["incidents"][0]["kind"] == "QUALITY_REJECTION" and task["status"] == "AWAITING_APPROVAL"


# --- The adversarial story through the API (capacity cut, partial cover, a new supplier) ----------------------

def test_capacity_cut_is_recovered_only_after_approval_and_closes_truthfully(http, team, factory) -> None:
    order = committed_order(http, team)
    committed = committed_rows(http, team, order)[0]
    farmer = "farmer_user" if committed["production_lot_id"] == team["lots"][0]["id"] else "other_farmer"
    other = "other_farmer" if farmer == "farmer_user" else "farmer_user"
    # The farmer reports that 110 kg of the 300 kg commitment can no longer be supplied.
    assert report(http, team, committed["production_lot_id"], 190, who=farmer).status_code == 201
    worker.run_once(factory)
    task = current(http, team, order)
    proposal = task["current_proposal"]
    content = proposal["content"]
    assert content["basis"]["exposed_kg"] == "110" and content["basis"]["net_need_kg"] == "110"
    types = [a["type"] for a in content["actions"]]
    assert types[0] == "RELEASE_EXPOSED" and "ACTIVATE_STANDBY" in types and "SOLICIT_SUPPLY" in types
    replacement = sum(D(a["quantity_kg"]) for a in content["actions"] if a["type"] != "RELEASE_EXPOSED")
    assert replacement == D("110") and content["escalation_kg"] == "0"
    assert proposal["tier"] == "ORDINARY" and content["decision"]["mode"] == "deterministic"
    assert "Draft only" in content["drafts"]["status"]
    # Nothing happens until a person approves the exact proposal.
    worker.run_once(factory)
    assert D(supply(http, team, order)["exposed_kg"]) == D("110")
    approve(http, team, order)
    worker.run_once(factory)
    after = supply(http, team, order)
    assert D(after["exposed_kg"]) == D("0")
    assert open_exceptions(factory, order["id"], ExceptionKind.CAPACITY_SHORTFALL) == []
    assert current(http, team, order)["status"] == "AWAITING_SUPPLIER"
    request = next(a for a in after["allocations"] if a["status"] == "SOLICITED")
    # The new supplier answers in their own portal: only now is it supply.
    assert D(after["committed_quantity_kg"]) == D("300") - D(request["quantity_kg"])
    answered = http.post(f"/allocations/{request['id']}/responses", headers=H(team, other, key="yes"), json=PORTAL)
    assert answered.status_code == 200, answered.text
    worker.run_once(factory)
    final = supply(http, team, order)
    assert D(final["committed_quantity_kg"]) == D("300") and final["supply_health"] == "COVERED"
    task = current(http, team, order)
    assert task["status"] == "COMPLETED"
    kinds = [step["kind"] for step in task["steps"]]
    assert kinds.index("PROPOSE") < kinds.index("APPROVAL") < kinds.index("EXECUTE") < kinds.index("COMPLETE")
    approval = next(step for step in task["steps"] if step["kind"] == "APPROVAL")
    assert approval["actor"] == str(team["coordinator"]) and approval["actor_name"] == "Coordinator"
    history = [e["event_type"] for e in http.get(f"/requirements/{order['id']}/events", headers=H(team)).json()]
    for name in ("exception.opened", "recovery.task_opened", "recovery.proposed", "recovery.approved",
                 "allocation.capacity_released", "allocation.standby_activated", "solicitation.sent", "recovery.applied",
                 "supplier.accepted", "recovery.task_completed"):
        assert name in history, name


# --- Approval binding (immutable content, distinct reviewers, tiers) -----------------------------------------

def test_approval_is_bound_to_the_reviewed_hash_and_each_reviewer_decides_once(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    wrong = http.post(f"/recovery-proposals/{proposal['id']}/approve", headers=H(team), json={"proposal_hash": "0" * 64})
    assert wrong.status_code == 409 and "not the current version" in wrong.text
    assert http.post(f"/recovery-proposals/{proposal['id']}/approve", headers=H(team, "auditor"),
                     json={"proposal_hash": proposal["content_hash"]}).status_code == 403
    assert http.post(f"/recovery-proposals/{proposal['id']}/approve", headers=H(team, "warehouse"),
                     json={"proposal_hash": proposal["content_hash"]}).status_code == 403
    assert http.post(f"/recovery-proposals/{proposal['id']}/reject", headers=H(team),
                     json={"proposal_hash": proposal["content_hash"], "reason": ""}).status_code == 422
    with factory() as session:  # tampering with stored content is detected
        row = session.get(RecoveryProposal, UUID(proposal["id"]))
        original = row.content
        row.content = {**original, "escalation_kg": "0.5"}
        session.commit()
    tampered = http.post(f"/recovery-proposals/{proposal['id']}/approve", headers=H(team), json={"proposal_hash": proposal["content_hash"]})
    assert tampered.status_code == 409 and "does not match its hash" in tampered.text
    with factory() as session:
        session.get(RecoveryProposal, UUID(proposal["id"])).content = original
        session.commit()
    approve(http, team, order)
    approve(http, team, order, proposal=proposal, expect=409)  # already approved; nobody approves twice


def test_elevated_proposals_need_a_second_distinct_approver_with_authority(http, team, factory) -> None:
    order = committed_order(http, team)
    # Make the only replacement dearer: the standby lot's farmgate price rises, with no tolerance set.
    standby = next(a for a in supply(http, team, order)["allocations"] if a["status"] == "STANDBY")
    with factory() as session:
        from src.backend.app.economics.domain.models import LotCostInput
        session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == UUID(standby["production_lot_id"]))).farmgate_price_per_kg_jmd = D("900")
        session.commit()
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    assert proposal["tier"] == "ELEVATED" and "no cost tolerance" in proposal["content"]["approval"]["reasons"][0]
    approve(http, team, order, "coordinator")
    assert current(http, team, order)["status"] == "AWAITING_APPROVAL"
    second = approve(http, team, order, "second_coordinator", proposal=proposal, expect=403)
    assert "procurement manager or organization administrator" in second.text
    approve(http, team, order, "manager", proposal=proposal)
    assert current(http, team, order)["status"] == "EXECUTING"
    worker.run_once(factory)
    assert current(http, team, order)["current_proposal"]["status"] == "EXECUTED"


def test_a_cost_tolerance_lets_coordinators_approve_within_it(http, team, factory) -> None:
    assert http.post("/recovery-approval-policy", headers=H(team), json={"max_cost_increase_jmd": "1000000", "reason": "x y"}).status_code == 403
    set_ = http.post("/recovery-approval-policy", headers=H(team, "admin"),
                     json={"max_cost_increase_jmd": "1000000", "max_cost_increase_pct": "0.80", "reason": "pilot tolerance"})
    assert set_.status_code == 201 and set_.json()["version"] == 1
    order = committed_order(http, team)
    standby = next(a for a in supply(http, team, order)["allocations"] if a["status"] == "STANDBY")
    with factory() as session:
        from src.backend.app.economics.domain.models import LotCostInput
        session.scalar(select(LotCostInput).where(LotCostInput.production_lot_id == UUID(standby["production_lot_id"]))).farmgate_price_per_kg_jmd = D("700")
        session.commit()
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    assert proposal["tier"] == "ORDINARY" and "within tolerance" in proposal["content"]["approval"]["reasons"][0]
    # The tolerance is tightened after approval: the gateway re-checks and refuses the stale approval.
    approve(http, team, order)
    assert http.post("/recovery-approval-policy", headers=H(team, "admin"),
                     json={"max_cost_increase_jmd": "1", "reason": "tightened"}).status_code == 201
    worker.run_once(factory)
    task = current(http, team, order)
    first = next(p for p in task["proposals"] if p["version"] == 1)
    assert first["status"] == "STALE" and "elevated" in first["status_reason"]
    assert task["current_proposal"]["version"] == 2 and task["current_proposal"]["tier"] == "ELEVATED"


# --- Gateway re-verification ---------------------------------------------------------------------------------

def test_gateway_refuses_when_the_approver_lost_their_membership(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    approve(http, team, order, "second_coordinator")
    with factory() as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == team["second_coordinator"]))
        membership.status = MembershipStatus.INACTIVE
        session.commit()
    worker.run_once(factory)
    task = current(http, team, order)
    first = next(p for p in task["proposals"] if p["version"] == 1)
    assert first["status"] == "STALE" and "no longer an active member" in first["status_reason"]
    assert first["executions"] == []
    assert supply(http, team, order)["standby_quantity_kg"] != "0"  # nothing applied


def test_stock_taken_after_approval_is_refused_and_replanned(http, team, factory) -> None:
    order = committed_order(http, team)
    committed = committed_rows(http, team, order)[0]
    assert report(http, team, committed["production_lot_id"], 190,
                  who="farmer_user" if committed["production_lot_id"] == team["lots"][0]["id"] else "other_farmer").status_code == 201
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    solicit = next(a for a in proposal["content"]["actions"] if a["type"] == "SOLICIT_SUPPLY")
    approve(http, team, order)
    rival = make_order(http, team, "240")  # another order commits the requested lot's free stock first
    commit_all(http, team, rival)
    worker.run_once(factory)
    task = current(http, team, order)
    first = next(p for p in task["proposals"] if p["version"] == 1)
    assert first["status"] == "STALE" and first["executions"] == []
    assert any(word in first["status_reason"] for word in ("free", "need", "no longer eligible"))
    assert D(supply(http, team, order)["exposed_kg"]) == D("110")  # still truthfully exposed
    assert solicit["production_lot_id"]


def test_an_expired_approval_window_supersedes_the_proposal(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    with factory() as session:
        session.get(RecoveryProposal, UUID(proposal["id"])).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
    late = http.post(f"/recovery-proposals/{proposal['id']}/approve", headers=H(team), json={"proposal_hash": proposal["content_hash"]})
    assert late.status_code == 409 and "approval window" in late.text
    worker.run_once(factory)
    task = current(http, team, order)
    assert next(p for p in task["proposals"] if p["version"] == 1)["status"] == "SUPERSEDED"
    assert task["current_proposal"]["version"] == 2 and task["current_proposal"]["status"] == "PENDING"


def test_rejection_is_respected_when_replanning(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    rejected = http.post(f"/recovery-proposals/{proposal['id']}/reject", headers=H(team),
                         json={"proposal_hash": proposal["content_hash"], "reason": "this supplier is unreliable"})
    assert rejected.status_code == 200, rejected.text
    worker.run_once(factory)
    task = current(http, team, order)
    targets = {a.get("allocation_id") or a["production_lot_id"] for a in proposal["content"]["actions"]}
    if task["current_proposal"]["version"] == 2:
        retry = {a.get("allocation_id") or a["production_lot_id"] for a in task["current_proposal"]["content"]["actions"]}
        assert not targets & retry
    else:
        assert task["status"] == "ESCALATED"
    assert any(s["kind"] == "REJECTION" and "unreliable" in s["summary"] for s in task["steps"])


# --- Coordination, restart safety, replay --------------------------------------------------------------------

def test_simultaneous_exceptions_on_one_order_share_one_task_and_one_quantity(http, team, factory) -> None:
    order = committed_order(http, team, "400")
    rows = committed_rows(http, team, order)
    assert len(rows) >= 2, rows
    first, second = rows[0], rows[1]
    drop(http, team, first["id"], key="drop-1")
    who = "farmer_user" if second["production_lot_id"] == team["lots"][0]["id"] else "other_farmer"
    keep = D(second["quantity_kg"]) - D("30")
    assert report(http, team, second["production_lot_id"], keep, who=who).status_code == 201
    worker.run_once(factory)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RecoveryTask)) == 1
        kinds = sorted(i.kind for i in session.scalars(select(RecoveryIncident)))
    assert kinds == ["CAPACITY_SHORTFALL", "SUPPLIER_DROPOUT"]
    content = current(http, team, order)["current_proposal"]["content"]
    need = D(first["quantity_kg"]) + D("30")
    assert D(content["basis"]["net_need_kg"]) == need
    claimed = sum(D(a["quantity_kg"]) for a in content["actions"] if a["type"] != "RELEASE_EXPOSED")
    assert claimed + D(content["escalation_kg"]) == need  # one plan for the whole shortfall, nothing claimed twice


def test_a_worker_crash_mid_execution_repeats_nothing(http, team, factory, monkeypatch) -> None:
    order = committed_order(http, team)
    committed = committed_rows(http, team, order)[0]
    assert report(http, team, committed["production_lot_id"], 190,
                  who="farmer_user" if committed["production_lot_id"] == team["lots"][0]["id"] else "other_farmer").status_code == 201
    worker.run_once(factory)
    approve(http, team, order)
    real = gateway.agent_event

    def die(session, task, event_type, payload, actor="recovery-agent"):
        if event_type == "recovery.applied":
            raise KeyboardInterrupt("worker process killed mid-transaction")
        return real(session, task, event_type, payload, actor)

    monkeypatch.setattr(gateway, "agent_event", die)
    with pytest.raises(KeyboardInterrupt):
        worker.run_once(factory)
    monkeypatch.setattr(gateway, "agent_event", real)
    with factory() as session:  # the killed transaction left nothing behind
        assert session.scalar(select(func.count()).select_from(RecoveryExecution)) == 0
        assert session.scalar(select(func.count()).select_from(SupplyAllocation).where(SupplyAllocation.status == AllocationStatus.SOLICITED)) == 0
    worker.run_once(factory)  # the restarted worker resumes from the last committed step
    worker.run_once(factory)
    with factory() as session:
        proposal = session.scalar(select(RecoveryProposal).where(RecoveryProposal.version == 1))
        assert proposal.status == ProposalStatus.EXECUTED
        actions = len(proposal.content["actions"])
        assert session.scalar(select(func.count()).select_from(RecoveryExecution)) == actions
        sent_by_gateway = select(func.count()).select_from(DomainEvent).where(
            DomainEvent.event_type == "solicitation.sent", DomainEvent.actor_id == "recovery-gateway")
        assert session.scalar(sent_by_gateway) == sum(1 for a in proposal.content["actions"] if a["type"] == "SOLICIT_SUPPLY")
        assert session.scalar(select(func.count()).select_from(DomainEvent).where(DomainEvent.event_type == "allocation.standby_activated")) == \
            sum(1 for a in proposal.content["actions"] if a["type"] == "ACTIVATE_STANDBY")


def test_replayed_events_open_no_second_task_or_incident(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    with factory() as session:
        for message in session.scalars(select(OutboxMessage)):
            message.status = "PENDING"  # replay every event the worker has ever seen
        session.commit()
    worker.run_once(factory)
    worker.run_once(factory)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RecoveryTask)) == 1
        assert session.scalar(select(func.count()).select_from(RecoveryIncident)) == 1
        assert session.scalar(select(func.count()).select_from(RecoveryProposal)) == 1


def test_cancelling_the_order_cancels_its_recovery(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    proposal = current(http, team, order)["current_proposal"]
    # Orders with binding supply cannot be cancelled through the API yet; record the cancellation directly and
    # wake the task, as the requirement.cancelled event does.
    with factory() as session:
        from src.backend.app.demand.domain.models import RequirementLifecycleStatus
        session.get(Requirement, UUID(order["id"])).lifecycle_status = RequirementLifecycleStatus.CANCELLED
        session.scalar(select(RecoveryTask)).next_run_at = datetime.now(timezone.utc)
        session.commit()
    worker.run_once(factory)
    task = current(http, team, order)
    assert task["status"] == "CANCELLED"
    assert approve(http, team, order, proposal=proposal, expect=409)


# --- Monitoring ----------------------------------------------------------------------------------------------

def test_a_failed_recovery_task_degrades_monitoring(http, team, factory, monkeypatch) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    from src.backend.app.agents.application import orchestrator

    def broken(*args, **kwargs):
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(orchestrator, "_plan", broken)
    now = datetime.now(timezone.utc)
    for attempt in range(orchestrator.MAX_ATTEMPTS + 1):  # the first tick only creates the task
        worker.run_once(factory, now=now + timedelta(seconds=40 * attempt))
    with factory() as session:
        task = session.scalar(select(RecoveryTask))
        assert task.status == TaskStatus.FAILED and "planner unavailable" in task.terminal_reason
        assert "recovery_failed" in operational_status(session)["reasons"]
        assert session.get(Requirement, UUID(order["id"])).supply_health != SupplyHealth.COVERED


def test_people_and_the_agent_are_attributed_separately_in_order_history(http, team, factory) -> None:
    order = committed_order(http, team)
    drop(http, team, committed_rows(http, team, order)[0]["id"])
    worker.run_once(factory)
    approve(http, team, order)
    worker.run_once(factory)
    with factory() as session:
        events = {e.event_type: e for e in session.scalars(select(DomainEvent).where(DomainEvent.aggregate_id == UUID(order["id"])))}
    assert (events["recovery.proposed"].actor_type, events["recovery.proposed"].actor_id) == ("agent", "recovery-agent")
    assert (events["recovery.approved"].actor_type, events["recovery.approved"].actor_id) == ("user", str(team["coordinator"]))
    assert (events["recovery.applied"].actor_type, events["recovery.applied"].actor_id) == ("agent", "recovery-gateway")
