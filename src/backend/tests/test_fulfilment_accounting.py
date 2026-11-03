"""R1 WP4: fulfilment accounting, reservation release, buyer confirmation, versioned reconciliation and close-out.

Runs on SQLite and, when POSTGRES_TEST_DATABASE_URL is set, on PostgreSQL. Every test ends with the stock ledger
invariant checked by the two_orgs factory (each lot's reserved total equals what holds reservations on it).
"""
import importlib.util
import json
import pathlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from test_capacity_exceptions import ATTEST, H, RELAY, commit_all, make_order, open_exceptions, org, supply  # noqa: F401
from two_orgs import add_member, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app import worker
from src.backend.app.assurance.application.operations import operational_status
from src.backend.app.assurance.domain.exceptions import ExceptionKind
from src.backend.app.assurance.domain.models import DomainEvent
from src.backend.app.demand.domain.models import Requirement, RequirementLifecycleStatus
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.identity.domain.permissions import ROLE_PERMISSIONS, PermissionCode as P, RoleCode
from src.backend.app.reconciliation.domain.models import StockLedgerFinding
from src.backend.app.supply.application.release import ReleaseError, release, release_remaining, releasable_kg
from src.backend.app.supply.domain.models import ProductionLot, ProductionLotStatus
from src.backend.app.supply.domain.planning_models import AllocationStatus, SupplyAllocation

D = Decimal
NOW = "2026-10-30T10:00:00Z"
CONFIRM_RELAY = {"buyer_representative": "Receiving clerk", "communication_channel": "phone call",
                 "attestation": "clerk confirmed the count on the phone", "stated_at": NOW}


@pytest.fixture()
def team(org, factory, http):
    """Everyone fulfilment involves, plus a fulfilment site created through the API."""
    with factory() as session:
        for role, label in ((RoleCode.SUPPLY_COORDINATOR, "second_coordinator"), (RoleCode.PROCUREMENT_MANAGER, "manager"),
                            (RoleCode.ORGANIZATION_ADMIN, "admin"), (RoleCode.WAREHOUSE_OPERATOR, "warehouse")):
            org[label] = add_member(session, org["org"], role, label).id
        org["buyer_user"] = add_member(session, org["org"], RoleCode.BUYER, "buyer", buyer_id=UUID(org["buyer"]["id"])).id
        session.commit()
    node = http.post("/fulfilment-nodes", headers=H(org), json={"name": "Moneague Packhouse", "node_type": "packhouse", "parish": "St. Ann"})
    assert node.status_code == 201, node.text
    org["node"] = node.json()["id"]
    return org


def committed(http, team, order) -> list[dict]:
    return [a for a in supply(http, team, order)["allocations"] if a["status"] == "COMMITTED"]


def receive(http, team, allocation_id, kg, key, accepted=None, rejected="0"):
    received = http.post("/sublots/receive", headers=H(team, "warehouse", key), json={
        "allocation_id": allocation_id, "fulfilment_node_id": team["node"], "received_quantity_kg": str(kg),
        "received_at": NOW, "receipt_evidence_reference": f"receipt-{key}"})
    assert received.status_code == 200, received.text
    sublot = received.json()["received_sublot_id"]
    if accepted is not None:
        graded = http.post(f"/sublots/{sublot}/grade", headers=H(team, "warehouse", f"g-{key}"), json={
            "accepted_quantity_kg": str(accepted), "rejected_quantity_kg": str(rejected), "assigned_grade": "A",
            "rejection_reason": "soft fruit" if D(str(rejected)) > 0 else None, "inspection_evidence_reference": f"qc-{key}"})
        assert graded.status_code == 200, graded.text
    return sublot


def ship(http, team, order, sublots, delivered, key):
    shipment = http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", f"sh-{key}"),
                         json={"fulfilment_node_id": team["node"], "reference": f"SHIP-{key}"})
    assert shipment.status_code == 200, shipment.text
    shipment_id = shipment.json()["shipment_id"]
    for sublot in sublots:
        added = http.post(f"/shipments/{shipment_id}/sublots", headers=H(team, "warehouse", f"add-{sublot}"), json={"received_sublot_id": sublot})
        assert added.status_code == 200, added.text
    assert http.post(f"/shipments/{shipment_id}/dispatch", headers=H(team, "warehouse", f"dis-{key}"), json={"evidence_reference": "manifest"}).status_code == 200
    delivery = http.post(f"/shipments/{shipment_id}/delivery", headers=H(team, "warehouse", f"del-{key}"), json={
        "delivered_quantity_kg": str(delivered), "delivered_at": NOW, "delivery_evidence_reference": "proof of delivery"})
    assert delivery.status_code == 200, delivery.text
    return shipment_id, delivery.json()["delivery_id"]


def record(http, team, order, who="coordinator") -> dict:
    response = http.get(f"/requirements/{order['id']}/fulfilment-record", headers=H(team, who))
    assert response.status_code == 200, response.text
    return response.json()


def one_lot(http, team, factory, expected="800", available="760") -> str:
    """A single lot holding all the stock, so the plan commits exactly one allocation on it."""
    with factory() as session:
        for lot in team["lots"]:
            session.get(ProductionLot, UUID(lot["id"])).available_quantity_kg = D("0")
        session.commit()
    lot = http.post("/production-lots", headers=H(team), json={
        "farmer_id": team["farmers"][0]["id"], "crop": "SCOTCH_BONNET", "harvest_start": date.today().isoformat(),
        "harvest_end": (date.today() + timedelta(days=40)).isoformat(), "expected_quantity_kg": expected,
        "available_quantity_kg": available, "quality_grade_estimate": "A", "provenance_source": "field visit",
        "attestation_method": "coordinator observation", "farmgate_price_per_kg_jmd": "600"})
    assert lot.status_code == 201, lot.text
    return lot.json()["id"]


def lot_row(factory, lot_id) -> ProductionLot:
    with factory() as session:
        return session.get(ProductionLot, UUID(lot_id))


# --- Role policy (P11) -------------------------------------------------------------------------------------------

def test_fulfilment_role_policy_is_explicit() -> None:
    R = ROLE_PERMISSIONS
    assert P.TRADE_RECONCILE in R[RoleCode.SUPPLY_COORDINATOR] and P.TRADE_RECONCILE in R[RoleCode.PROCUREMENT_MANAGER]
    assert P.TRADE_RECONCILE not in R[RoleCode.WAREHOUSE_OPERATOR]  # records physical facts, never certifies
    assert {P.RECEIVING_RECORD, P.GRADING_RECORD, P.SHIPMENT_DISPATCH, P.DELIVERY_CONFIRM} <= R[RoleCode.WAREHOUSE_OPERATOR]
    assert P.TRADE_ACCEPT_VARIANCE in R[RoleCode.PROCUREMENT_MANAGER] and P.TRADE_ACCEPT_VARIANCE in R[RoleCode.ORGANIZATION_ADMIN]
    assert P.TRADE_ACCEPT_VARIANCE not in R[RoleCode.SUPPLY_COORDINATOR]
    assert R[RoleCode.BUYER] & {P.TRADE_RECONCILE, P.BUYER_CONFIRMATION_RELAY, P.DISPUTE_RAISE} == set()
    assert P.DELIVERY_CONFIRM_OWN in R[RoleCode.BUYER]
    auditor = R[RoleCode.AUDITOR]
    assert P.AUDIT_FLAG in auditor and not auditor & {P.TRADE_RECONCILE, P.DISPUTE_RAISE, P.BUYER_CONFIRMATION_RELAY, P.RECEIVING_RECORD}


# --- Release primitive (P2, P3) --------------------------------------------------------------------------------------

def test_release_is_partial_idempotent_and_never_releases_received_stock(http, team, factory) -> None:
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    allocation_id = committed(http, team, order)[0]["id"]
    receive(http, team, allocation_id, 30, "r1")
    with factory() as session:
        allocation = session.get(SupplyAllocation, UUID(allocation_id))
        lot_id, quantity = allocation.production_lot_id, allocation.quantity_kg
        reserved_before = session.get(ProductionLot, lot_id).reserved_quantity_kg
        assert releasable_kg(session, allocation) == quantity - 30
        assert release(session, allocation, D("50"), kind="approved_partial", reason="test", actor_id="test") == D("50")
        with pytest.raises(ReleaseError):
            release(session, allocation, quantity, kind="approved_partial", reason="too much", actor_id="test")
        with pytest.raises(ReleaseError):
            release(session, allocation, D("1"), kind="not_a_kind", reason="x", actor_id="test")
        rest = release_remaining(session, allocation, kind="approved_partial", reason="rest", actor_id="test")
        assert rest == quantity - 30 - 50
        assert release_remaining(session, allocation, kind="approved_partial", reason="again", actor_id="test") == 0
        session.commit()
        lot = session.get(ProductionLot, lot_id)
        assert allocation.quantity_kg == quantity  # the agreement is never rewritten
        assert allocation.released_quantity_kg == quantity - 30 and allocation.holds_reservation is True
        assert lot.reserved_quantity_kg == reserved_before - (quantity - 30)  # the 30 kg received stays reserved
        assert lot.reverification_required and lot.status == ProductionLotStatus.UNAVAILABLE
        events = session.scalars(select(DomainEvent).where(DomainEvent.event_type == "allocation.reservation_released")).all()
        assert len(events) == 2 and all(e.payload["attribution"] == "COORDINATOR_RELEASE" for e in events)


# --- Dropout (P3) ----------------------------------------------------------------------------------------------------

def test_dropout_releases_only_the_undelivered_part_at_once_and_keeps_the_history(http, team, factory) -> None:
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    commitment = committed(http, team, order)[0]
    receive(http, team, commitment["id"], 60, "r1", accepted=60)
    response = http.post(f"/allocations/{commitment['id']}/dropout", headers=H(team, key="drop"), json={"reason": "crop failure"})
    assert response.status_code == 200, response.text
    with factory() as session:
        allocation = session.get(SupplyAllocation, UUID(commitment["id"]))
        lot = session.get(ProductionLot, allocation.production_lot_id)
        assert allocation.status == AllocationStatus.LOST and allocation.quantity_kg == D(commitment["quantity_kg"])
        assert allocation.released_quantity_kg == allocation.quantity_kg - 60
        assert lot.reverification_required  # freed stock is not offered again until confirmed
        event = session.scalar(select(DomainEvent).where(DomainEvent.event_type == "allocation.reservation_released"))
        assert event.payload["kind"] == "dropout" and event.payload["attribution"] == "SUPPLIER_DROPOUT"
    state = supply(http, team, order)
    lost = next(a for a in state["allocations"] if a["id"] == commitment["id"])
    assert lost["status"] == "LOST"
    assert record(http, team, order)["figures"]["accepted_kg"] in ("60", "60.000")  # delivered stock still counted


# --- The spec story: 730 ordered, 725 received, 705 accepted, 20 rejected (additional requirement 7) ----------------

def test_730_ordered_725_received_705_accepted_is_never_shown_as_730_delivered(http, team, factory) -> None:
    lot_id = one_lot(http, team, factory)
    order = make_order(http, team, "730")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    assert len(rows) == 1 and D(rows[0]["quantity_kg"]) == 730
    sublot = receive(http, team, rows[0]["id"], 725, "story", accepted=705, rejected=20)
    _, delivery_id = ship(http, team, order, [sublot], 705, "story")

    # The buyer can never confirm more than was delivered; they confirm what arrived in their own account.
    buyer = H(team, "buyer_user", "bc-1")
    too_much = http.post(f"/buyer/deliveries/{delivery_id}/confirmation", headers=buyer, json={"confirmed_quantity_kg": "730"})
    assert too_much.status_code == 409
    confirmed = http.post(f"/buyer/deliveries/{delivery_id}/confirmation", headers=H(team, "buyer_user", "bc-2"),
                          json={"confirmed_quantity_kg": "705"})
    assert confirmed.status_code == 200 and confirmed.json()["channel"] == "BUYER_ACCOUNT"

    # Warehouse operators record facts but cannot certify the reconciliation.
    assert http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, "warehouse", "rw"), json={}).status_code == 403
    reconciled = http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="rc"), json={"verification_evidence_reference": "count"})
    assert reconciled.status_code == 200, reconciled.text
    figures, variances = reconciled.json()["figures"], reconciled.json()["variances"]
    as_kg = {k: D(str(v)) for k, v in figures.items() if k.endswith("_kg")}
    assert (as_kg["required_kg"], as_kg["committed_kg"], as_kg["received_kg"], as_kg["accepted_kg"], as_kg["rejected_kg"]) == (730, 730, 725, 705, 20)
    assert (as_kg["dispatched_kg"], as_kg["delivered_kg"], as_kg["buyer_confirmed_kg"]) == (705, 705, 705)
    assert D(str(variances["required_minus_accepted_kg"])) == 25 and D(str(variances["required_minus_received_kg"])) == 5
    assert reconciled.json()["completion"]["can_complete"] is False

    # Completed is refused; only an authorized person may accept the documented 25 kg difference.
    assert http.post(f"/requirements/{order['id']}/close", headers=H(team, key="c1"), json={}).status_code == 409
    assert http.post(f"/requirements/{order['id']}/close", headers=H(team, key="c2"),
                     json={"accept_variance": True, "reason": "short harvest"}).status_code == 403
    assert http.post(f"/requirements/{order['id']}/close", headers=H(team, "manager", "c3"),
                     json={"accept_variance": True}).status_code == 422
    closed = http.post(f"/requirements/{order['id']}/close", headers=H(team, "manager", "c4"),
                       json={"accept_variance": True, "reason": "20 kg rejected at grading, 5 kg never harvested; buyer informed"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["outcome"] == "CLOSED_WITH_VARIANCE" and D(closed.json()["released_kg"]) == 5
    assert http.post(f"/requirements/{order['id']}/close", headers=H(team, "manager", "c4"),
                     json={"accept_variance": True, "reason": "repeat"}).json() == closed.json()  # idempotent

    # Only the 5 kg never received is released; received, rejected and delivered stock is never offered again.
    lot = lot_row(factory, lot_id)
    assert lot.reserved_quantity_kg == 725 and lot.reverification_required
    # An ended order asks for nothing more: its open exceptions (here the 20 kg quality rejection) are resolved with
    # the outcome, and their records stay.
    assert open_exceptions(factory, order["id"]) == []
    with factory() as session:
        from src.backend.app.assurance.domain.exceptions import SupplyException
        resolved = session.scalars(select(SupplyException).where(SupplyException.requirement_id == UUID(order["id"]))).all()
        assert resolved and all("order ended (closed with variance)" in e.resolution for e in resolved)

    # The same figures survive a refresh, another person's independent session and the order's history.
    for who in ("auditor", "second_coordinator"):
        view = record(http, team, order, who)
        assert view["lifecycle_status"] == "CLOSED_WITH_VARIANCE"
        assert D(str(view["figures"]["delivered_kg"])) == 705 and D(str(view["figures"]["buyer_confirmed_kg"])) == 705
        assert D(str(view["variances"]["required_minus_accepted_kg"])) == 25
        assert view["effective_reconciliation_version"] == 1
    with factory() as session:
        event = session.scalar(select(DomainEvent).where(DomainEvent.event_type == "order.closed"))
        assert event.payload["variance_reason"].startswith("20 kg rejected")
    assert http.post(f"/requirements/{order['id']}/close", headers=H(team, "manager", "c5"),
                     json={"accept_variance": True, "reason": "again"}).status_code == 409


# --- Versioned reconciliation, review and completion (P6, P11) -----------------------------------------------------

def test_corrections_are_new_versions_and_material_ones_need_a_second_reviewer(http, team, factory) -> None:
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    sublots = [receive(http, team, a["id"], a["quantity_kg"], f"r{i}", accepted=a["quantity_kg"]) for i, a in enumerate(rows)]
    total = sum(D(a["quantity_kg"]) for a in rows)
    assert total == 200
    _, delivery_id = ship(http, team, order, sublots, total, "v")
    first = http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="v1"), json={})
    assert first.status_code == 200 and first.json()["version"] == 1 and first.json()["status"] == "EFFECTIVE"
    # An unconfirmed delivery is reconciled but not completed.
    assert http.post(f"/requirements/{order['id']}/close", headers=H(team, key="cx"), json={}).status_code == 409

    relayed = http.post(f"/deliveries/{delivery_id}/confirmations", headers=H(team, key="rel"),
                        json={"confirmed_quantity_kg": str(total), **CONFIRM_RELAY})
    assert relayed.status_code == 200 and relayed.json()["channel"] == "STAFF_RELAYED"
    no_reason = http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="v2a"), json={})
    assert no_reason.status_code == 422
    second = http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="v2"),
                       json={"reason": "buyer confirmed by phone"})
    assert second.status_code == 200 and second.json()["status"] == "PENDING_REVIEW" and second.json()["material_change"] is True
    assert record(http, team, order)["effective_reconciliation_version"] == 1  # the earlier version stays effective
    assert http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="v3"), json={"reason": "again"}).status_code == 409
    review = f"/reconciliations/{second.json()['reconciliation_id']}/review"
    assert http.post(review, headers=H(team), json={"approve": True, "note": "mine"}).status_code == 403
    assert http.post(review, headers=H(team, "warehouse"), json={"approve": True, "note": "looks right"}).status_code == 403
    approved = http.post(review, headers=H(team, "second_coordinator"), json={"approve": True, "note": "checked the call log"})
    assert approved.status_code == 200, approved.text
    view = record(http, team, order)
    assert view["effective_reconciliation_version"] == 2
    assert [r["version"] for r in view["reconciliations"]] == [1, 2]  # nothing overwritten

    # Auditors flag without changing anything.
    flag = http.post("/audit-flags", headers=H(team, "auditor"), json={"subject": "check relay", "note": "verify call log", "requirement_id": order["id"]})
    assert flag.status_code == 201
    assert http.post(f"/requirements/{order['id']}/disputes", headers=H(team, "auditor"), json={"description": "x y z"}).status_code == 403

    closed = http.post(f"/requirements/{order['id']}/close", headers=H(team, key="done"), json={})
    assert closed.status_code == 200 and closed.json()["outcome"] == "COMPLETED", closed.text
    with factory() as session:
        assert session.get(Requirement, UUID(order["id"])).lifecycle_status == RequirementLifecycleStatus.COMPLETED


# --- Buyer confirmation, discrepancies and disputes (P5, P11) ------------------------------------------------------

def test_buyer_partial_confirmation_opens_a_dispute_that_blocks_close_until_resolved(http, team, factory) -> None:
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    sublots = [receive(http, team, a["id"], a["quantity_kg"], f"r{i}", accepted=a["quantity_kg"]) for i, a in enumerate(rows)]
    _, delivery_id = ship(http, team, order, sublots, 100, "b")
    mine = http.get("/buyer/deliveries", headers=H(team, "buyer_user"))
    assert mine.status_code == 200 and [d["id"] for d in mine.json()] == [delivery_id]
    assert mine.json()[0]["confirmation"] is None

    # A different buyer in the same organization cannot see or confirm it.
    with factory() as session:
        from src.backend.app.demand.domain.models import Buyer
        other = Buyer(organization_id=team["org"], name="Other Hotel", buyer_type="HOTEL", destination="Ocho Rios")
        session.add(other); session.flush()
        stranger = add_member(session, team["org"], RoleCode.BUYER, "stranger", buyer_id=other.id).id
        session.commit()
    team["stranger"] = stranger
    assert http.get("/buyer/deliveries", headers=H(team, "stranger")).json() == []
    assert http.post(f"/buyer/deliveries/{delivery_id}/confirmation", headers=H(team, "stranger", "s1"),
                     json={"confirmed_quantity_kg": "100"}).status_code == 404
    # A buyer cannot use the staff relay route, and staff cannot pose as the buyer.
    assert http.post(f"/deliveries/{delivery_id}/confirmations", headers=H(team, "buyer_user", "x"),
                     json={"confirmed_quantity_kg": "100", **CONFIRM_RELAY}).status_code == 403
    assert http.post(f"/buyer/deliveries/{delivery_id}/confirmation", headers=H(team, key="x2"),
                     json={"confirmed_quantity_kg": "100"}).status_code == 403
    assert http.post(f"/deliveries/{delivery_id}/confirmations", headers=H(team, key="x3"),
                     json={"confirmed_quantity_kg": "100", **{**CONFIRM_RELAY, "attestation": ""}}).status_code == 422

    vague = http.post(f"/buyer/deliveries/{delivery_id}/confirmation", headers=H(team, "buyer_user", "d0"),
                      json={"confirmed_quantity_kg": "92", "discrepancy": True})
    assert vague.status_code == 422  # a discrepancy must be described
    partial = http.post(f"/buyer/deliveries/{delivery_id}/confirmation", headers=H(team, "buyer_user", "d1"),
                        json={"confirmed_quantity_kg": "92", "discrepancy": True, "note": "two crates short"})
    assert partial.status_code == 200 and partial.json()["outcome"] == "DISCREPANCY" and partial.json()["dispute_id"]
    view = record(http, team, order)
    f = view["figures"]
    assert D(str(f["delivered_kg"])) == 100 and D(str(f["buyer_confirmed_kg"])) == 92 and D(str(f["disputed_kg"])) == 8
    assert f["open_disputes"] == 1 and view["disputes"][0]["party"] == "BUYER"

    assert http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="rc"), json={}).status_code == 200
    blocked = http.post(f"/requirements/{order['id']}/close", headers=H(team, "manager", "c1"), json={"accept_variance": True, "reason": "x y z"})
    assert blocked.status_code == 409 and "dispute" in blocked.json()["detail"]
    resolution = f"/disputes/{partial.json()['dispute_id']}/resolution"
    assert http.post(resolution, headers=H(team, "warehouse"), json={"outcome": "RESOLVED", "resolution": "credit"}).status_code == 403
    assert http.post(resolution, headers=H(team), json={"outcome": "RESOLVED", "resolution": "credit note for 8 kg"}).status_code == 200
    assert http.post(resolution, headers=H(team), json={"outcome": "WITHDRAWN", "resolution": "overwrite"}).status_code == 409
    assert http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="rc2"), json={"reason": "dispute resolved"}).status_code == 200
    view = record(http, team, order)
    assert view["disputes"][0]["status"] == "RESOLVED" and view["disputes"][0]["resolution"] == "credit note for 8 kg"


# --- Receipts and physical corrections (requirement 3) -------------------------------------------------------------

def test_receipts_need_an_agreed_commitment_and_corrections_never_edit_the_original(http, team, factory) -> None:
    order = make_order(http, team, "100")
    assert http.post(f"/requirements/{order['id']}/plan", headers=H(team, key="plan")).status_code == 201
    proposed = supply(http, team, order)["allocations"][0]
    unagreed = http.post("/sublots/receive", headers=H(team, "warehouse", "u"), json={
        "allocation_id": proposed["id"], "fulfilment_node_id": team["node"], "received_quantity_kg": "10", "received_at": NOW})
    assert unagreed.status_code == 409
    for allocation in supply(http, team, order)["allocations"]:
        if allocation["role"] == "COMMITTED":
            assert http.post(f"/allocations/{allocation['id']}/solicit", headers=H(team, key=f"s-{allocation['id']}"), json={}).status_code == 200
            assert http.post(f"/allocations/{allocation['id']}/responses", headers=H(team, key=f"a-{allocation['id']}"),
                             json={"decision": "ACCEPTED", **ATTEST}).status_code == 200
    allocation = committed(http, team, order)[0]
    over = http.post("/sublots/receive", headers=H(team, "warehouse", "o"), json={
        "allocation_id": allocation["id"], "fulfilment_node_id": team["node"],
        "received_quantity_kg": str(D(allocation["quantity_kg"]) + 1), "received_at": NOW})
    assert over.status_code == 409
    sublot = receive(http, team, allocation["id"], 50, "r", accepted=45, rejected=5)
    correction = http.post(f"/sublots/{sublot}/adjustments", headers=H(team, "warehouse"), json={
        "received_delta_kg": "0", "accepted_delta_kg": "-3", "rejected_delta_kg": "3", "reason": "re-inspection found bruising"})
    assert correction.status_code in (200, 201), correction.text
    with factory() as session:
        original = session.get(ReceivedSublot, UUID(sublot))
        assert (original.received_quantity_kg, original.accepted_quantity_kg, original.rejected_quantity_kg) == (50, 45, 5)
        adjustment = session.scalar(select(ReceivedSublot).where(ReceivedSublot.adjusts_sublot_id == original.id))
        assert adjustment.entry_type == "ADJUSTMENT" and adjustment.adjustment_reason == "re-inspection found bruising"
    receipt = record(http, team, order)["receipts"][0]
    assert (D(receipt["accepted_kg"]), D(receipt["rejected_kg"]), receipt["corrections"]) == (42, 8, 1)


def test_shipment_references_are_unique_per_site_and_open_shipments_cancel_with_a_reason(http, team, factory) -> None:
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    allocation = committed(http, team, order)[0]
    sublot = receive(http, team, allocation["id"], 40, "r", accepted=40)
    body = {"fulfilment_node_id": team["node"], "reference": "MAY-01"}
    first = http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", "s1"), json=body)
    assert first.status_code == 200
    assert http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", "s2"), json=body).status_code == 409
    other_site = http.post("/fulfilment-nodes", headers=H(team), json={"name": "Second Hub", "node_type": "hub", "parish": "Clarendon"}).json()["id"]
    assert http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", "s3"),
                     json={**body, "fulfilment_node_id": other_site}).status_code == 200
    shipment_id = first.json()["shipment_id"]
    assert http.post(f"/shipments/{shipment_id}/sublots", headers=H(team, "warehouse", "a"), json={"received_sublot_id": sublot}).status_code == 200
    assert http.post(f"/shipments/{shipment_id}/cancel", headers=H(team, "warehouse"), json={"reason": "x"}).status_code == 422
    cancelled = http.post(f"/shipments/{shipment_id}/cancel", headers=H(team, "warehouse"), json={"reason": "truck broke down"})
    assert cancelled.status_code == 200, cancelled.text
    # The produce is free to go on another shipment.
    again = http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", "s4"), json={**body, "reference": "MAY-02"}).json()["shipment_id"]
    assert http.post(f"/shipments/{again}/sublots", headers=H(team, "warehouse", "b"), json={"received_sublot_id": sublot}).status_code == 200
    # Sites are managed by coordinators, not warehouse operators, and are deactivated rather than deleted.
    assert http.post("/fulfilment-nodes", headers=H(team, "warehouse"), json={"name": "X Site", "node_type": "hub", "parish": "Clarendon"}).status_code == 403
    assert http.post(f"/fulfilment-nodes/{other_site}/deactivate", headers=H(team)).json()["active"] is False
    assert http.post("/sublots/receive", headers=H(team, "warehouse", "inactive"), json={
        "allocation_id": allocation["id"], "fulfilment_node_id": other_site, "received_quantity_kg": "1", "received_at": NOW}).status_code == 409


# --- Cancellation (P1) ---------------------------------------------------------------------------------------------

def test_cancellation_is_a_request_that_needs_supplier_agreement_and_approval(http, team, factory) -> None:
    from recovery_support import agent_round, approve, member, pending, task_for
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    direct = http.post(f"/requirements/{order['id']}/cancel", headers=H(team), json={"reason": "buyer cancelled"})
    assert direct.status_code == 409 and "cancellation request" in direct.json()["detail"]
    body = {"reason": "buyer cancelled the event", "buyer_instruction": "email from buyer 12 Oct"}
    requested = http.post(f"/requirements/{order['id']}/cancellation-requests", headers=H(team), json=body)
    assert requested.status_code == 202, requested.text
    with factory() as session:
        agent_round(session)
        task = task_for(session, UUID(order["id"]))
        assert task.purpose == "CANCELLATION" and task.status.value == "ESCALATED"  # no supplier has agreed yet
        assert "supplier agreement" in task.terminal_reason or "agreement" in (task.last_error or task.terminal_reason or "")
    # Each supplier agrees to be released (relayed by staff with an attestation), then a fresh request is planned.
    for row in rows:
        agreed = http.post(f"/allocations/{row['id']}/release-agreements", headers=H(team),
                           json={"quantity_kg": row["quantity_kg"], "attestation_method": "phone call with farmer"})
        assert agreed.status_code == 201, agreed.text
    # The agreements wake the escalated task, which plans again.
    with factory() as session:
        agent_round(session)
        proposal = pending(session, UUID(order["id"]))
        types = [a["type"] for a in proposal.content["actions"]]
        assert types[-1] == "CANCEL_ORDER" and proposal.content["actions"][-1]["mode"] == "FULL"
        assert proposal.tier.value == "ORDINARY"
        coordinator = member(session, RoleCode.SUPPLY_COORDINATOR, team["org"])
        approve(session, UUID(order["id"]), coordinator)
        requirement = session.get(Requirement, UUID(order["id"]))
        assert requirement.lifecycle_status == RequirementLifecycleStatus.CANCELLED
        for row in rows:
            allocation = session.get(SupplyAllocation, UUID(row["id"]))
            assert allocation.quantity_kg == D(row["quantity_kg"]) and allocation.status == AllocationStatus.RELEASED
            assert allocation.holds_reservation is False
        events = session.scalars(select(DomainEvent).where(DomainEvent.event_type == "allocation.reservation_released")).all()
        assert events and all(e.payload["attribution"] == "BUYER_CANCELLATION" for e in events)  # never a farmer default


def test_cancellation_after_receipt_keeps_physical_records_and_needs_elevated_approval(http, team, factory) -> None:
    from recovery_support import agent_round, member, pending
    from src.backend.app.agents.application.approvals import decide
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    receive(http, team, rows[0]["id"], 50, "r", accepted=50)
    for row in rows:
        assert http.post(f"/allocations/{row['id']}/release-agreements", headers=H(team),
                         json={"quantity_kg": row["quantity_kg"], "attestation_method": "phone call with farmer"}).status_code == 201
    assert http.post(f"/requirements/{order['id']}/cancellation-requests", headers=H(team),
                     json={"reason": "buyer stopped the order", "buyer_instruction": "call 14 Oct"}).status_code == 202
    with factory() as session:
        agent_round(session)
        proposal = pending(session, UUID(order["id"]))
        assert proposal.tier.value == "ELEVATED" and proposal.content["actions"][-1]["mode"] == "REMAINDER"
        coordinator = member(session, RoleCode.SUPPLY_COORDINATOR, team["org"])
        manager = member(session, RoleCode.PROCUREMENT_MANAGER, team["org"])
        decide(session, coordinator, proposal.id, proposal.content_hash, True, "ok"); session.commit()
        agent_round(session)
        session.refresh(proposal)
        assert proposal.status.value == "PENDING"  # one ordinary approval is not enough
        decide(session, manager, proposal.id, proposal.content_hash, True, "elevated ok"); session.commit()
        agent_round(session)
        requirement = session.get(Requirement, UUID(order["id"]))
        assert requirement.lifecycle_status != RequirementLifecycleStatus.CANCELLED  # stays open for reconciliation
        received = session.get(SupplyAllocation, UUID(rows[0]["id"]))
        assert received.released_quantity_kg == received.quantity_kg - 50 and received.holds_reservation is True
        assert session.scalar(select(ReceivedSublot).where(ReceivedSublot.allocation_id == received.id)) is not None


# --- Buyer reduction (P4) and demand increase ------------------------------------------------------------------------

def test_buyer_changes_never_revoke_commitments_automatically(http, team, factory) -> None:
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    before = {a["id"]: a["quantity_kg"] for a in committed(http, team, order)}
    changed = http.post(f"/requirements/{order['id']}/buyer-change", headers=H(team),
                        json={"new_quantity_kg": "120", "reason": "buyer reduced the order"})
    assert changed.status_code in (200, 201), changed.text
    worker.run_once(factory)
    assert {a["id"]: a["quantity_kg"] for a in committed(http, team, order)} == before
    assert [e.kind for e in open_exceptions(factory, order["id"])] == [ExceptionKind.OVER_COMMITTED]
    increased = http.post(f"/requirements/{order['id']}/buyer-change", headers=H(team),
                          json={"new_quantity_kg": "260", "reason": "buyer increased the order"})
    assert increased.status_code in (200, 201), increased.text
    worker.run_once(factory)
    kinds = {e.kind for e in open_exceptions(factory, order["id"])}
    assert ExceptionKind.DEMAND_INCREASE in kinds and ExceptionKind.OVER_COMMITTED not in kinds


# --- Changed lot information and harvest expiry (P7, P9) -------------------------------------------------------------

def test_grade_downgrade_and_withdrawal_raise_exceptions_without_changing_commitments(http, team, factory) -> None:
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    commitment = committed(http, team, order)[0]
    lot_id = commitment["production_lot_id"]
    version = http.get(f"/production-lots/{lot_id}", headers=H(team)).json()["version"]
    downgraded = http.patch(f"/production-lots/{lot_id}", headers=H(team), json={
        "expected_version": version, "quality_grade_estimate": "B", "provenance_source": "field visit", "attestation_method": "coordinator observation"})
    assert downgraded.status_code == 200, downgraded.text
    kinds = [e.kind for e in open_exceptions(factory, order["id"])]
    assert ExceptionKind.ELIGIBILITY_CHANGED in kinds
    with factory() as session:
        allocation = session.get(SupplyAllocation, UUID(commitment["id"]))
        assert allocation.status == AllocationStatus.COMMITTED and allocation.quantity_kg == D(commitment["quantity_kg"])
    withdrawn = http.post(f"/production-lots/{lot_id}/withdraw", headers=H(team), json={"reason": "flood damage confirmed on visit", "provenance_source": "field visit", "attestation_method": "coordinator observation"})
    assert withdrawn.status_code == 200, withdrawn.text
    assert lot_row(factory, lot_id).status == ProductionLotStatus.EXHAUSTED
    assert ExceptionKind.LOT_UNAVAILABLE in [e.kind for e in open_exceptions(factory, order["id"])]
    version = http.get(f"/production-lots/{lot_id}", headers=H(team)).json()["version"]
    assert http.patch(f"/production-lots/{lot_id}", headers=H(team), json={
        "expected_version": version, "expected_quantity_kg": "500", "provenance_source": "x y", "attestation_method": "x y"}).status_code == 409


def test_an_ended_harvest_needs_reverification_but_time_alone_never_exhausts_a_lot(http, team, factory, monkeypatch) -> None:
    lot_id = team["lots"][0]["id"]
    with factory() as session:
        lot = session.get(ProductionLot, UUID(lot_id))
        lot.harvest_start, lot.harvest_end = date.today() - timedelta(days=30), date.today() - timedelta(days=8)
        lot.last_verified_at = datetime.now(timezone.utc) - timedelta(days=9)
        session.commit()
    worker.run_once(factory)
    lot = lot_row(factory, lot_id)
    assert lot.reverification_required and lot.status == ProductionLotStatus.UNAVAILABLE  # excluded from new planning only
    assert lot.status != ProductionLotStatus.EXHAUSTED
    relayed = http.post(f"/production-lots/{lot_id}/capacity-reports", headers=H(team), json={"reported_capacity_kg": "200", **RELAY})
    assert relayed.status_code == 201
    lot = lot_row(factory, lot_id)
    assert not lot.reverification_required and lot.status == ProductionLotStatus.AVAILABLE
    worker.run_once(factory)
    assert not lot_row(factory, lot_id).reverification_required  # a current confirmation holds

    # A verified viability date that passes makes the lot exhausted and flags the orders depending on it.
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    commitment = committed(http, team, order)[0]
    with factory() as session:
        session.get(ProductionLot, UUID(commitment["production_lot_id"])).viable_until = date.today() - timedelta(days=1)
        session.commit()
    worker.run_once(factory)
    assert lot_row(factory, commitment["production_lot_id"]).status == ProductionLotStatus.EXHAUSTED
    assert ExceptionKind.LOT_UNAVAILABLE in [e.kind for e in open_exceptions(factory, order["id"])]


# --- Stock ledger (M8, requirement 5) ------------------------------------------------------------------------------

@pytest.mark.ledger_drift_expected
def test_ledger_drift_is_recorded_and_degrades_monitoring_and_is_never_repaired(http, team, factory) -> None:
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    lot_id = UUID(committed(http, team, order)[0]["production_lot_id"])
    with factory() as session:
        session.get(ProductionLot, lot_id).reserved_quantity_kg += D("7")
        session.commit()
    now = datetime.now(timezone.utc)
    assert worker.run_ledger_check(factory, now, force=True) == 1
    with factory() as session:
        finding = session.scalar(select(StockLedgerFinding))
        assert finding.difference_kg == 7 and finding.resolved_at is None
        assert session.get(ProductionLot, lot_id).reserved_quantity_kg == finding.recorded_reserved_kg  # not repaired
        assert "stock_ledger_mismatch" in operational_status(session, organization_id=team["org"])["reasons"]
    ledger = http.get("/stock-ledger", headers=H(team))
    assert ledger.status_code == 200 and ledger.json()["balanced"] is False
    with factory() as session:  # a deliberate correction, then the next check resolves the finding
        session.get(ProductionLot, lot_id).reserved_quantity_kg -= D("7")
        session.commit()
    assert worker.run_ledger_check(factory, now + timedelta(seconds=1), force=True) == 0
    with factory() as session:
        assert session.scalar(select(StockLedgerFinding)).resolved_at is not None
        assert "stock_ledger_mismatch" not in operational_status(session, organization_id=team["org"])["reasons"]


# --- Release audit script (requirement 8) ----------------------------------------------------------------------------

def _release_audit():
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "release_audit.py"
    spec = importlib.util.spec_from_file_location("release_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_audit_is_dry_run_first_and_applies_only_the_reviewed_report(http, team, factory) -> None:
    audit = _release_audit()
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    commitment = committed(http, team, order)[0]
    with factory() as session:  # a legacy order closed before WP4 without releasing its reservations
        session.get(Requirement, UUID(order["id"])).lifecycle_status = RequirementLifecycleStatus.CLOSED
        session.commit()
    with factory() as session:
        report = audit.audit(session)
        session.rollback()
    assert [r["allocation_id"] for r in report["releasable"]] == [commitment["id"]]
    assert report["releasable"][0]["kind"] == "close_out"
    with factory() as session:  # nothing was changed by the dry run
        assert session.get(SupplyAllocation, UUID(commitment["id"])).released_quantity_kg == 0
        with pytest.raises(SystemExit):
            audit.apply(session, report, reason="", approval_reference="PO-1", backup_reference="bk-1")
        with pytest.raises(SystemExit):
            audit.apply(session, {**report, "fingerprint": "stale"}, reason="legacy close-out", approval_reference="PO-1", backup_reference="bk-1")
        session.rollback()
    with factory() as session:
        result = audit.apply(session, json.loads(json.dumps(report)), reason="legacy close-out", approval_reference="PO-1", backup_reference="bk-1")
        session.commit()
    assert [r["allocation_id"] for r in result["released"]] == [commitment["id"]] and result["stock_ledger_mismatches_after"] == []
    with factory() as session:
        assert audit.audit(session)["releasable"] == []
        event = session.scalar(select(DomainEvent).where(DomainEvent.event_type == "allocation.reservation_released"))
        assert event.payload["approval_reference"] == "PO-1" and event.actor_id == "release-audit (approval PO-1)"


# --- PostgreSQL concurrency --------------------------------------------------------------------------------------

def _race(factory, functions):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(len(functions))

    def run(fn):
        session = factory()
        try:
            barrier.wait()
            value = fn(session)
            session.commit()
            return ("ok", value)
        except Exception as exc:  # the loser's error is the expected outcome
            session.rollback()
            return ("error", exc)
        finally:
            session.close()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(run, functions))


def _reconciled_order_with_open_request(http, team, factory):
    order = make_order(http, team, "200")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    sublots = [receive(http, team, a["id"], a["quantity_kg"], f"r{i}", accepted=a["quantity_kg"]) for i, a in enumerate(rows)]
    ship(http, team, order, sublots, sum(D(a["quantity_kg"]) for a in rows), "race")
    standby = next(a for a in supply(http, team, order)["allocations"] if a["status"] == "PROPOSED")
    assert http.post(f"/allocations/{standby['id']}/solicit", headers=H(team, key="sol"), json={}).status_code == 200
    assert http.post(f"/requirements/{order['id']}/reconcile", headers=H(team, key="rec"), json={}).status_code == 200
    return order, standby


def test_close_out_racing_a_late_acceptance_never_leaves_stock_held_or_double_counted(http, team, factory) -> None:
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL only")
    from recovery_support import member
    from src.backend.app.reconciliation.application import services as trade
    from src.backend.app.supply.application.commitments import SupplierResponse, respond
    from src.backend.app.supply.domain.planning_models import ConsentDecision
    order, standby = _reconciled_order_with_open_request(http, team, factory)
    with factory() as session:
        coordinator = member(session, RoleCode.SUPPLY_COORDINATOR, team["org"])
        manager = member(session, RoleCode.PROCUREMENT_MANAGER, team["org"])
    accept = SupplierResponse(decision=ConsentDecision.ACCEPTED, attestation_method="phone call with farmer",
                              activation_conditions="only to replace lost supply")
    results = _race(factory, [
        lambda s: respond(s, coordinator, UUID(standby["id"]), accept, "late-accept"),
        lambda s: trade.close_order(s, manager, UUID(order["id"]), accept_variance=True, reason="buyer accepted the count", key="close"),
    ])
    with factory() as session:
        allocation = session.get(SupplyAllocation, UUID(standby["id"]))
        status = session.get(Requirement, UUID(order["id"])).lifecycle_status
        if results[1][0] == "ok":  # close-out won: the open request was withdrawn and its stock released
            assert results[0][0] == "error" and allocation.status == AllocationStatus.WITHDRAWN and not allocation.holds_reservation
            assert status == RequirementLifecycleStatus.CLOSED_WITH_VARIANCE
        else:  # the acceptance won: close-out saw changed records and refused; nothing was released
            assert results[0][0] == "ok" and allocation.status == AllocationStatus.STANDBY
            assert status != RequirementLifecycleStatus.CLOSED_WITH_VARIANCE
    # The factory teardown asserts the stock ledger balances either way.


def test_two_simultaneous_reconciliations_produce_one_version(http, team, factory) -> None:
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL only")
    from recovery_support import member
    from src.backend.app.reconciliation.application import services as trade
    from src.backend.app.reconciliation.domain.models import ReconciliationRecord
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    rows = committed(http, team, order)
    sublots = [receive(http, team, a["id"], a["quantity_kg"], f"r{i}", accepted=a["quantity_kg"]) for i, a in enumerate(rows)]
    ship(http, team, order, sublots, 100, "twin")
    with factory() as session:
        first, second = member(session, RoleCode.SUPPLY_COORDINATOR, team["org"]), member(session, RoleCode.PROCUREMENT_MANAGER, team["org"])
    results = _race(factory, [lambda s: trade.reconcile(s, first, UUID(order["id"]), None, None, "a"),
                              lambda s: trade.reconcile(s, second, UUID(order["id"]), None, None, "b")])
    assert sorted(r[0] for r in results) == ["error", "ok"]
    with factory() as session:
        versions = session.scalars(select(ReconciliationRecord.version).where(ReconciliationRecord.requirement_id == UUID(order["id"]))).all()
        assert versions == [1]
