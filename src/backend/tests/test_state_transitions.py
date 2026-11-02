"""Invalid state transitions are refused and leave state unchanged; legacy consent is never revived."""
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from two_orgs import add_member, as_user, ensure_roles, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app import worker
from src.backend.app.agents.domain.models import RecoveryProposal
from src.backend.app.assurance.application.recovery import dropout
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.risk.domain.models import RiskSnapshot
from src.backend.app.supply.domain.models import ProductionLot
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, ConsentStatus, SupplierConsent, SupplyAllocation,
)

ATTEST = {"attestation_method": "phone call with farmer"}


@pytest.fixture()
def org(factory, http):
    with factory() as session:
        ensure_roles(session)
        organization = Organization(id=uuid4(), name="Transition Exports", slug=f"tx-{uuid4().hex[:6]}")
        session.add(organization); session.flush()
        user = add_member(session, organization.id, RoleCode.SUPPLY_COORDINATOR, "coordinator")
        session.commit()
    h = as_user(user.id, organization.id)
    buyer = http.post("/buyers", headers=h, json={"name": "Port Royal Foods", "buyer_type": "PROCESSOR", "destination": "Kingston"}).json()
    for name, qty in (("Ena Gordon", "500"), ("Paul Reid", "400")):
        farmer = http.post("/farmers", headers=h, json={"name": name, "parish": "St. Ann"}).json()
        http.post("/production-lots", headers=h, json={
            "farmer_id": farmer["id"], "crop": "SCOTCH_BONNET", "harvest_start": "2026-11-20", "harvest_end": "2026-12-10",
            "expected_quantity_kg": qty, "available_quantity_kg": qty, "quality_grade_estimate": "A",
            "provenance_source": "field visit", "attestation_method": "coordinator observation", "farmgate_price_per_kg_jmd": "600"})
    order = http.post("/requirements", headers=h, json={"buyer_id": buyer["id"], "crop": "SCOTCH_BONNET", "grade": "A",
                                                       "required_quantity_kg": "730", "delivery_window_start": "2026-12-01",
                                                       "delivery_window_end": "2026-12-12"}).json()
    return {"org": organization.id, "user": user.id, "order": order}


def H(org, key=None):
    return as_user(org["user"], org["org"], key)


def _supply(http, org):
    return http.get(f"/requirements/{org['order']['id']}/assurance", headers=H(org)).json()


def _plan(http, org):
    assert http.post(f"/requirements/{org['order']['id']}/plan", headers=H(org, "plan")).status_code == 201
    return _supply(http, org)["allocations"]


def _snapshot(factory, org):
    with factory() as session:
        rows = session.scalars(select(SupplyAllocation).where(SupplyAllocation.requirement_id == UUID(org["order"]["id"]))).all()
        lots = session.scalars(select(ProductionLot)).all()
        return (sorted((str(a.id), a.status.value, str(a.quantity_kg), a.consent_status.value) for a in rows),
                sorted((str(l.id), str(l.reserved_quantity_kg)) for l in lots),
                session.query(SupplierConsent).count())


def test_supplier_decision_transitions(http, org, factory) -> None:
    allocations = [a for a in _plan(http, org) if a["role"] == "COMMITTED"]
    first, second = allocations[0]["id"], allocations[1]["id"]
    before = _snapshot(factory, org)
    refused = [
        (f"/allocations/{first}/responses", {"decision": "ACCEPTED", **ATTEST}),   # not yet solicited
        (f"/allocations/{first}/responses", {"decision": "DECLINED", **ATTEST}),
    ]
    for index, (path, body) in enumerate(refused):
        assert http.post(path, headers=H(org, f"r{index}"), json=body).status_code == 409
    assert _snapshot(factory, org) == before

    assert http.post(f"/allocations/{first}/solicit", headers=H(org, "s1"), json={}).status_code == 200
    assert http.post(f"/allocations/{first}/solicit", headers=H(org, "s1-again"), json={}).status_code == 409  # already asked
    assert http.post(f"/allocations/{first}/responses", headers=H(org, "a1"), json={"decision": "ACCEPTED", **ATTEST}).status_code == 200
    after_accept = _snapshot(factory, org)
    for index, (path, body) in enumerate([
        (f"/allocations/{first}/responses", {"decision": "DECLINED", **ATTEST}),   # cannot reverse a recorded acceptance
        (f"/allocations/{first}/responses", {"decision": "ACCEPTED", **ATTEST}),   # nor record it twice
        (f"/allocations/{first}/withdraw", {"reason": "changed mind"}),           # nor withdraw a commitment
        (f"/allocations/{first}/solicit", {}),
    ]):
        assert http.post(path, headers=H(org, f"x{index}"), json=body).status_code == 409, path
    assert _snapshot(factory, org) == after_accept

    assert http.post(f"/allocations/{second}/withdraw", headers=H(org, "w2"), json={"reason": "not needed"}).status_code == 200
    for index, (path, body) in enumerate([
        (f"/allocations/{second}/solicit", {}),
        (f"/allocations/{second}/responses", {"decision": "ACCEPTED", **ATTEST}),
        (f"/allocations/{second}/withdraw", {"reason": "again"}),
    ]):
        assert http.post(path, headers=H(org, f"y{index}"), json=body).status_code == 409, path


def test_order_lifecycle_transitions(http, org, factory) -> None:
    path = f"/requirements/{org['order']['id']}"
    allocations = _plan(http, org)
    assert http.patch(path, headers=H(org), json={"expected_version": 2, "notes": "late edit"}).status_code == 409  # locked after planning
    assert http.post(f"{path}/plan", headers=H(org, "plan-again")).status_code == 409                              # no replanning
    commitment = next(a for a in allocations if a["role"] == "COMMITTED")
    http.post(f"/allocations/{commitment['id']}/solicit", headers=H(org, "s"), json={})
    http.post(f"/allocations/{commitment['id']}/responses", headers=H(org, "a"), json={"decision": "ACCEPTED", **ATTEST})
    blocked = http.post(f"{path}/cancel", headers=H(org), json={"reason": "buyer withdrew"})
    assert blocked.status_code == 409 and "cancellation request" in blocked.json()["detail"]
    assert http.get(path, headers=H(org)).json()["lifecycle_status"] != "CANCELLED"


def test_cancelling_withdraws_open_requests_and_blocks_further_work(http, org, factory) -> None:
    path = f"/requirements/{org['order']['id']}"
    allocations = _plan(http, org)
    asked = allocations[0]["id"]
    http.post(f"/allocations/{asked}/solicit", headers=H(org, "s"), json={})
    cancelled = http.post(f"{path}/cancel", headers=H(org), json={"reason": "tender withdrawn"})
    assert cancelled.status_code == 200
    statuses = {a["status"] for a in _supply(http, org)["allocations"]}
    assert statuses == {"WITHDRAWN"}
    assert http.post(f"/allocations/{allocations[1]['id']}/solicit", headers=H(org, "late"), json={}).status_code == 409
    assert http.post(f"/allocations/{asked}/responses", headers=H(org, "late-r"), json={"decision": "ACCEPTED", **ATTEST}).status_code == 409
    with factory() as session:
        assert all(lot.reserved_quantity_kg == 0 for lot in session.scalars(select(ProductionLot)))


def test_a_cancelled_order_cannot_be_planned(http, org) -> None:
    path = f"/requirements/{org['order']['id']}"
    assert http.post(f"{path}/cancel", headers=H(org), json={"reason": "duplicate order"}).status_code == 200
    response = http.post(f"{path}/plan", headers=H(org, "plan-cancelled"))
    assert response.status_code == 409 and "cancelled" in response.json()["detail"]


def _make_legacy(factory, org, allocations):
    """Reproduce exactly what the pre-R1 planner wrote: COMMITTED/STANDBY with a random consent id."""
    with factory() as session:
        for row in allocations:
            allocation = session.get(SupplyAllocation, UUID(row["id"]))
            allocation.status = AllocationStatus.COMMITTED if allocation.role == AllocationRole.COMMITTED else AllocationStatus.STANDBY
            allocation.consent_evidence_id, allocation.consent_status, allocation.holds_reservation = uuid4(), ConsentStatus.UNSUPPORTED_LEGACY, True
            session.get(ProductionLot, allocation.production_lot_id).reserved_quantity_kg += allocation.quantity_kg
        session.commit()


def test_legacy_consent_cannot_be_revived_or_counted(http, org, factory) -> None:
    allocations = _plan(http, org)
    _make_legacy(factory, org, allocations)
    legacy_standby = next(a for a in allocations if a["role"] == "STANDBY")
    # A legacy row cannot be turned into a recorded one by responding to it.
    assert http.post(f"/allocations/{legacy_standby['id']}/responses", headers=H(org, "revive"),
                     json={"decision": "ACCEPTED", "activation_conditions": "x", **ATTEST}).status_code == 409
    supply = _supply(http, org)
    assert supply["committed_quantity_kg"] == "0" and supply["standby_quantity_kg"] == "0"
    assert Decimal(supply["unsupported_legacy_kg"]) == sum(Decimal(a["quantity_kg"]) for a in allocations)
    assert {a["consent_status"] for a in supply["allocations"]} == {"UNSUPPORTED_LEGACY"}
    with factory() as session:
        assert session.query(SupplierConsent).count() == 0
        # The recovery agent must not offer legacy standby either.
        committed = next(a for a in allocations if a["role"] == "COMMITTED")
        dropout(session, UUID(committed["id"]), "legacy loss", "legacy-drop")
        session.commit()
    worker.run_once(factory)
    with factory() as session:
        offered = [a.get("allocation_id") for content in session.scalars(select(RecoveryProposal.content)) for a in content["actions"]]
        assert legacy_standby["id"] not in offered
        activated = session.scalars(select(SupplyAllocation).where(
            SupplyAllocation.requirement_id == UUID(org["order"]["id"]), SupplyAllocation.status == AllocationStatus.ACTIVATED)).all()
        assert activated == []
        standby_row = session.get(SupplyAllocation, UUID(legacy_standby["id"]))
        assert standby_row.status == AllocationStatus.STANDBY and standby_row.consent_status == ConsentStatus.UNSUPPORTED_LEGACY


def test_risk_snapshot_ignores_legacy_standby(http, org, factory) -> None:
    from src.backend.app.risk.application.calculator import create_risk_snapshot
    from src.backend.app.demand.domain.models import Requirement
    from src.backend.app.supply.domain.planning_models import SupplyPlan
    allocations = _plan(http, org)
    _make_legacy(factory, org, allocations)
    with factory() as session:
        requirement = session.get(Requirement, UUID(org["order"]["id"]))
        plan = session.scalar(select(SupplyPlan).where(SupplyPlan.requirement_id == requirement.id))
        snapshot = create_risk_snapshot(session, requirement, plan)
        assert snapshot.committed_farmer_count == 0 and snapshot.standby_farmer_count == 0
        assert snapshot.standby_coverage_pct == 0
