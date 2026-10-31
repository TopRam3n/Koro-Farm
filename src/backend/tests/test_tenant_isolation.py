"""Adversarial organization-isolation tests.

Two organizations, each with its own users, buyers, suppliers, lots, orders, nodes, programmes and
corridors. Authorization runs through the real membership lookup (`get_authorization_context`); only
the Supabase token check is replaced by a test identity header. The attacker in organization B holds
PLATFORM_ADMIN, every permission, so these tests show that isolation does not depend on permissions.

Runs on SQLite always, and on PostgreSQL when POSTGRES_TEST_DATABASE_URL is set.
"""
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.app.assurance.domain.models import DomainEvent, RecoveryRun
from src.backend.app.compliance.domain.models import ComplianceRule
from src.backend.app.core.auth import get_current_user
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.domain.models import FulfilmentNode, ReceivedSublot
from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, Role, UserAccount
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.main import app
from src.backend.app.supply.domain.crops import ensure_shared_crops
from src.backend.app.main_dependencies import get_session
from src.backend.app.programmes.domain.models import Programme
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, SupplyAllocation
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor
from two_orgs import factory, http, _org, _h  # noqa: F401  (pytest fixtures)
from consent_support import confirm_plan_via_api

@pytest.fixture()
def worlds(factory, http):
    with factory() as session:
        for code in RoleCode:
            if session.get(Role, code) is None:
                session.add(Role(code=code, name=code.value, description="test role", internal_only=False))
        session.commit()
        a = _org(session, "Alpha")
        b = _org(session, "Beta", crop_lot=Crop.YAM)
    # Organization A builds real downstream records through its own, authorized API calls.
    assert http.post(f"/requirements/{a['requirement']}/plan", headers=_h(a, "plan-a")).status_code == 201
    confirm_plan_via_api(http, a["requirement"], _h(a))
    with factory() as session:
        allocation = session.scalar(select(SupplyAllocation).where(SupplyAllocation.requirement_id == a["requirement"],
                                                                   SupplyAllocation.role == AllocationRole.COMMITTED))
        a["allocation"] = allocation.id
    receipt = http.post("/sublots/receive", headers=_h(a, "receive-a"), json={
        "allocation_id": str(a["allocation"]), "fulfilment_node_id": str(a["node"]), "received_quantity_kg": "10",
        "received_at": "2026-12-11T10:00:00Z"})
    assert receipt.status_code == 200, receipt.text
    a["sublot"] = UUID(receipt.json()["received_sublot_id"])
    assert http.post(f"/sublots/{a['sublot']}/grade", headers=_h(a, "grade-a"),
                     json={"accepted_quantity_kg": "10", "rejected_quantity_kg": "0", "assigned_grade": "A"}).status_code == 200
    shipment = http.post(f"/requirements/{a['requirement']}/shipments", headers=_h(a, "ship-a"),
                         json={"fulfilment_node_id": str(a["node"]), "reference": "ALPHA-1"})
    assert shipment.status_code == 200, shipment.text
    a["shipment"] = UUID(shipment.json()["shipment_id"])
    # Dropping the committed allocation creates a recovery case owned by organization A.
    dropped = http.post(f"/allocations/{a['allocation']}/dropout", headers=_h(a, "drop-a"), json={"reason": "test", "defer_recovery": True})
    assert dropped.status_code == 200, dropped.text
    with factory() as session:
        run = session.scalar(select(RecoveryRun).where(RecoveryRun.requirement_id == a["requirement"]))
        a["recovery"] = run.id if run else None
        # An exception owned by organization A, for the route sweep.
        from src.backend.app.assurance.domain.exceptions import ExceptionKind, SupplyException
        exception = SupplyException(organization_id=a["org"], requirement_id=a["requirement"], kind=ExceptionKind.CAPACITY_SHORTFALL,
                                    dedupe_key=f"capacity:{a['requirement']}", shortfall_kg=Decimal("10"), summary="test", details={})
        session.add(exception); session.commit()
        a["exception"] = exception.id
    return a, b


def _state(factory, a) -> dict:
    with factory() as session:
        requirement = session.get(Requirement, a["requirement"])
        lot = session.get(ProductionLot, a["lot"])
        return {"req_qty": requirement.required_quantity_kg, "req_version": requirement.version, "plan_version": requirement.plan_version,
                "health": requirement.supply_health, "lot_reserved": lot.reserved_quantity_kg,
                "allocations": sorted((str(x.id), x.status.value, x.quantity_kg) for x in session.scalars(
                    select(SupplyAllocation).where(SupplyAllocation.requirement_id == a["requirement"]))),
                "sublots": sorted((str(x.id), x.accepted_quantity_kg) for x in session.scalars(select(ReceivedSublot))),
                "spare_plan": session.get(Requirement, a["spare_requirement"]).plan_version,
                "spare_programme": session.get(Requirement, a["spare_requirement"]).programme_id}


def test_reads_of_another_organizations_records_are_not_found(http, worlds) -> None:
    a, b = worlds
    paths = [
        f"/requirements/{a['requirement']}", f"/requirements/{a['requirement']}/assurance", f"/requirements/{a['requirement']}/risk",
        f"/requirements/{a['requirement']}/events", f"/requirements/{a['requirement']}/fulfilment",
        f"/requirements/{a['requirement']}/compliance", f"/production-lots/{a['lot']}", f"/production-lots/{a['lot']}/shipments",
        f"/farmers/{a['farmer']}/trade-performance-passport", f"/sublots/{a['sublot']}/traceability",
        f"/shipments/{a['shipment']}/traceability", f"/programmes/{a['programme']}", f"/trade-corridors/{a['corridor']}",
        f"/recovery-cases/{a['recovery']}",
    ]
    for path in paths:
        assert http.get(path, headers=_h(a)).status_code == 200, f"owner should read {path}"
        response = http.get(path, headers=_h(b))
        assert response.status_code == 404, f"{path} leaked across organizations: {response.status_code}"


def test_mutations_of_another_organizations_records_are_refused_and_change_nothing(http, worlds, factory) -> None:
    a, b = worlds
    before = _state(factory, a)
    commands = [
        ("post", f"/requirements/{a['spare_requirement']}/plan", None),
        ("post", f"/requirements/{a['requirement']}/recovery", None),
        ("post", f"/requirements/{a['requirement']}/buyer-change", {"new_quantity_kg": "999", "reason": "attack"}),
        ("post", f"/allocations/{a['allocation']}/dropout", {"reason": "attack", "defer_recovery": True}),
        ("post", f"/allocations/{a['allocation']}/accept", None),
        ("post", f"/allocations/{a['allocation']}/decline", None),
        ("post", f"/sublots/{a['sublot']}/grade", {"accepted_quantity_kg": "0", "rejected_quantity_kg": "10"}),
        ("post", f"/requirements/{a['requirement']}/shipments", {"fulfilment_node_id": str(b["node"]), "reference": "EVIL-1"}),
        ("post", f"/shipments/{a['shipment']}/sublots", {"received_sublot_id": str(a["sublot"])}),
        ("post", f"/shipments/{a['shipment']}/dispatch", {}),
        ("post", f"/shipments/{a['shipment']}/delivery", {"delivered_quantity_kg": "1", "delivered_at": "2026-12-12T00:00:00Z"}),
        ("post", f"/requirements/{a['requirement']}/reconcile", {"verification_evidence_reference": "attack"}),
        ("post", f"/programmes/{a['programme']}/requirements/{a['spare_requirement']}", None),
    ]
    for index, (method, path, body) in enumerate(commands):
        response = getattr(http, method)(path, headers=_h(b, f"attack-{index}"), json=body)
        assert response.status_code == 404, f"{path} accepted a cross-organization command: {response.status_code} {response.text}"
    assert _state(factory, a) == before


def test_identifiers_in_request_bodies_are_checked_against_the_caller(http, worlds, factory) -> None:
    a, b = worlds
    before = _state(factory, a)
    attempts = [
        ("/sublots/receive", {"allocation_id": str(a["allocation"]), "fulfilment_node_id": str(b["node"]),
                              "received_quantity_kg": "1", "received_at": "2026-12-11T10:00:00Z"}),
        (f"/requirements/{b['requirement']}/shipments", {"fulfilment_node_id": str(a["node"]), "reference": "MIXED-1"}),
        ("/programmes", {"buyer_id": str(a["buyer"]), "name": "Hijack", "start_date": "2026-01-01", "end_date": "2026-12-31"}),
    ]
    for index, (path, body) in enumerate(attempts):
        response = http.post(path, headers=_h(b, f"body-{index}"), json=body)
        assert response.status_code == 404, f"{path} accepted a foreign identifier: {response.status_code} {response.text}"
    assert http.post("/requirements", headers=_h(b), json={
        "buyer_id": str(a["buyer"]), "crop": "GINGER", "grade": "A", "required_quantity_kg": "5",
        "delivery_window_start": "2026-12-01", "delivery_window_end": "2026-12-02"}).status_code == 404
    assert _state(factory, a) == before


def test_lists_and_summaries_contain_only_the_callers_organization(http, worlds) -> None:
    a, b = worlds
    foreign = {str(v) for k, v in a.items() if k not in {"org", "user"} and v is not None}
    for path in ["/requirements", "/production-lots", "/farmers", "/allocations", "/recovery-cases", "/received-sublots",
                 "/shipments", "/activity", "/programmes", "/trade-corridors", "/compliance-rules", "/command-center/summary"]:
        response = http.get(path, headers=_h(b))
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"
        leaked = [value for value in foreign if value in response.text]
        assert not leaked, f"{path} exposes organization A identifiers: {leaked}"
    summary = http.get("/command-center/summary", headers=_h(b)).json()
    assert summary["requirements"]["total"] == 2
    assert summary["physical_flow_kg"]["received"] in {"0", "0.000"}


def test_planning_never_uses_another_organizations_supply(http, worlds, factory) -> None:
    a, b = worlds
    # Only organization B holds yam. An organization-A yam order must stay unfilled.
    with factory() as session:
        requirement = Requirement(buyer_id=a["buyer"], crop=Crop.YAM, grade=Grade.A, required_quantity_kg=Decimal("100"),
                                  delivery_window_start=date(2026, 12, 10), delivery_window_end=date(2026, 12, 15))
        session.add(requirement); session.commit()
        yam_order = requirement.id
    response = http.post(f"/requirements/{yam_order}/plan", headers=_h(a, "plan-yam"))
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["committed_quantity_kg"]) == 0
    assert Decimal(response.json()["unfilled_quantity_kg"]) == Decimal("100")
    with factory() as session:
        assert session.get(ProductionLot, b["lot"]).reserved_quantity_kg == 0


def test_idempotency_keys_are_namespaced_per_organization(http, worlds) -> None:
    a, b = worlds
    first = http.post(f"/requirements/{a['spare_requirement']}/plan", headers=_h(a, "shared-key"))
    second = http.post(f"/requirements/{b['requirement']}/plan", headers=_h(b, "shared-key"))
    assert first.status_code == second.status_code == 201
    assert first.json()["requirement_id"] == str(a["spare_requirement"])
    assert second.json()["requirement_id"] == str(b["requirement"])


def test_events_carry_their_organization_and_history_is_isolated(http, worlds, factory) -> None:
    a, b = worlds
    with factory() as session:
        events = session.scalars(select(DomainEvent).where(DomainEvent.aggregate_id == a["requirement"])).all()
        assert events and all(event.organization_id == a["org"] for event in events)
    a_ids = {str(event.id) for event in events}
    seen_by_b = {item["id"] for item in http.get("/activity", headers=_h(b)).json()["items"]}
    assert not (a_ids & seen_by_b)
    assert a_ids <= {item["id"] for item in http.get("/activity", headers=_h(a)).json()["items"]}


def test_membership_in_a_different_organization_cannot_be_claimed_by_header(http, worlds) -> None:
    a, b = worlds
    spoof = {"X-Test-User-ID": str(b["user"]), "X-Organization-ID": str(a["org"])}
    assert http.get(f"/requirements/{a['requirement']}", headers=spoof).status_code == 403
    assert http.get("/requirements", headers=spoof).status_code == 403


SELF_SCOPED_PREFIXES = ("/v1/ingestion", "/v1/secure-actions", "/marketplace", "/admin", "/me", "/access-requests",
                        "/invitations")


def test_every_identifier_route_refuses_another_organizations_records(http, worlds) -> None:
    """Behavioural sweep over the whole API surface.

    Every route with an ``*_id`` path parameter (outside routers that do their own membership-based scoping)
    is called by organization B with organization A's real identifiers and must answer 404 or 403.
    A parameter name not mapped here fails the test, so a new route cannot silently skip the guard.
    """
    a, b = worlds
    ids = {"requirement_id": a["requirement"], "allocation_id": a["allocation"], "sublot_id": a["sublot"],
           "shipment_id": a["shipment"], "lot_id": a["lot"], "farmer_id": a["farmer"], "programme_id": a["programme"],
           "recovery_id": a["recovery"], "corridor_id": a["corridor"], "buyer_id": a["buyer"], "exception_id": a["exception"]}
    checked, problems = 0, []
    for path, operations in app.openapi()["paths"].items():
        params = [part[1:-1] for part in path.split("/") if part.startswith("{") and part.endswith("}")]
        if not any(name.endswith("_id") for name in params) or path.startswith(SELF_SCOPED_PREFIXES):
            continue
        unknown = [name for name in params if name not in ids]
        if unknown:
            problems.append(f"{path}: no test identifier for {unknown}")
            continue
        concrete = path
        for name in params:
            concrete = concrete.replace("{" + name + "}", str(ids[name]))
        for method in operations:
            response = http.request(method.upper(), concrete, headers=_h(b, f"sweep-{checked}"), json={})
            checked += 1
            if response.status_code not in (403, 404):
                problems.append(f"{method.upper()} {path} -> {response.status_code}")
    assert checked >= 27, f"sweep only exercised {checked} operations"
    assert not problems, problems


def test_users_in_several_organizations_must_choose_one(http, factory) -> None:
    with factory() as session:
        from two_orgs import add_member, ensure_roles
        ensure_roles(session)
        first = Organization(id=uuid4(), name="Alpha Exports", slug=f"alpha-{uuid4().hex[:6]}")
        second = Organization(id=uuid4(), name="Beta Exports", slug=f"beta-{uuid4().hex[:6]}")
        session.add_all([first, second]); session.flush()
        user = add_member(session, first.id, RoleCode.SUPPLY_COORDINATOR, "dual")
        session.add(OrganizationMembership(user_id=user.id, organization_id=second.id, role_code=RoleCode.AUDITOR,
                                           status=MembershipStatus.ACTIVE, accepted_at=datetime.now(timezone.utc)))
        session.commit()
    listed = http.get("/me/organizations", headers={"X-Test-User-ID": str(user.id)})
    assert listed.status_code == 200
    assert {(row["name"], row["role"]) for row in listed.json()} == {("Alpha Exports", "SUPPLY_COORDINATOR"), ("Beta Exports", "AUDITOR")}
    # Without a chosen organization the request is ambiguous and refused, not guessed.
    assert http.get("/requirements", headers={"X-Test-User-ID": str(user.id)}).status_code == 403
    assert http.get("/requirements", headers={"X-Test-User-ID": str(user.id), "X-Organization-ID": str(first.id)}).status_code == 200
