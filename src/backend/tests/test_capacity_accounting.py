"""WP2 review: capacity accounting across the lot lifecycle and per-allocation standby exposure.

Quantities on a production lot (see docs/product/R1_WP2_REPORT.md, "Quantity meanings"):
* expected_quantity_kg  - the declared harvest;
* available_quantity_kg - planning availability: the most the platform may plan from the lot (delivered included);
* reserved_quantity_kg  - held by commitments, authorized standby and marketplace orders (delivered included);
* reported_capacity_kg  - capacity ceiling from the latest applied report: delivered at the time of the report plus
                          what the supplier said they could still supply. Receipts do not change it.
* delivered             - received against the lot's allocations (received_sublots).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select

from test_capacity_exceptions import H, commit_all, make_order, open_exceptions, org, report, supply  # noqa: F401
from two_orgs import factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app import worker
from src.backend.app.assurance.domain.exceptions import ExceptionKind
from src.backend.app.fulfilment.application.services import receive
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.supply.domain.models import ProductionLot
from src.backend.app.supply.domain.planning_models import (
    AllocationRole, AllocationStatus, ConsentStatus, SupplyAllocation,
)

D = Decimal


def lot_row(http, org, lot_id) -> dict:
    return next(lot for lot in http.get("/production-lots", headers=H(org)).json() if lot["id"] == lot_id)


def committed_on(http, org, order) -> SupplyAllocation:
    return next(a for a in supply(http, org, order)["allocations"] if a["status"] == "COMMITTED")


def deliver(factory, org, allocation_id, kg) -> None:
    with factory() as session:
        node = FulfilmentNode(organization_id=org["org"], name="Hub", node_type="HUB", parish="St. Ann")
        session.add(node); session.flush()
        receive(session, UUID(allocation_id), node.id, D(kg), datetime.now(timezone.utc), "receipt", f"rcv-{uuid4()}")
        session.commit()


def add_standby(factory, order, lot_id, kg, responded_at) -> UUID:
    """An authorized standby on a chosen lot, reserving its stock, as recorded consent would leave it."""
    with factory() as session:
        plan_id = session.scalar(select(SupplyAllocation.supply_plan_id).where(SupplyAllocation.requirement_id == UUID(order["id"])))
        allocation = SupplyAllocation(requirement_id=UUID(order["id"]), supply_plan_id=plan_id, production_lot_id=UUID(lot_id),
                                      role=AllocationRole.STANDBY, status=AllocationStatus.STANDBY, quantity_kg=D(kg),
                                      consent_status=ConsentStatus.RECORDED, holds_reservation=True, plan_version=1,
                                      activation_conditions="only to replace lost supply", responded_at=responded_at)
        session.add(allocation)
        session.get(ProductionLot, UUID(lot_id)).reserved_quantity_kg += D(kg)
        session.commit()
        return allocation.id


def planned(http, org, quantity):
    order = make_order(http, org, quantity)
    assert http.post(f"/requirements/{order['id']}/plan", headers=H(org, key=f"plan-{order['id']}")).status_code == 201
    return order


# --- Item 1: standby exposure is attributed per allocation, never double counted ----------------------------

def test_standby_uncovered_on_a_shared_lot_is_split_not_double_counted(http, org, factory) -> None:
    lot_id = org["lots"][1]["id"]
    first, second = planned(http, org, "100"), planned(http, org, "100")
    earlier, later = datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc)
    add_standby(factory, first, lot_id, "40", earlier)
    add_standby(factory, second, lot_id, "40", later)
    add_standby(factory, second, lot_id, "20", datetime(2026, 10, 3, tzinfo=timezone.utc))  # two on one lot, same order
    with factory() as session:
        committed_here = session.get(ProductionLot, UUID(lot_id)).reserved_quantity_kg - D("100")
    assert report(http, org, lot_id, committed_here + D("50")).status_code == 201  # 100 kg standby, 50 kg of capacity left

    a, b = supply(http, org, first), supply(http, org, second)
    # Earliest authorization keeps its cover: first 40 covered; second's 40 gets 10, its 20 gets none.
    assert D(a["standby_uncovered_kg"]) == D("0")
    assert D(b["standby_uncovered_kg"]) == D("50")
    assert D(a["standby_uncovered_kg"]) + D(b["standby_uncovered_kg"]) == D("50")  # equals the lot's real shortfall


def test_standby_on_different_lots_is_counted_per_lot(http, org, factory) -> None:
    order = planned(http, org, "100")
    for lot in org["lots"]:
        add_standby(factory, order, lot["id"], "30", datetime(2026, 10, 1, tzinfo=timezone.utc))
    for lot in org["lots"]:
        with factory() as session:
            assert report(http, org, lot["id"], session.get(ProductionLot, UUID(lot["id"])).reserved_quantity_kg - D("30") + D("10")).status_code == 201
    assert D(supply(http, org, order)["standby_uncovered_kg"]) == D("40")  # 20 on each lot


# --- Item 2: reports cannot recreate stock that has left planning availability ----------------------------

def test_a_relayed_report_cannot_restore_availability_a_declaration_removed(http, org, factory) -> None:
    lot = org["lots"][0]
    changed = http.patch(f"/production-lots/{lot['id']}", headers=H(org), json={
        "expected_version": lot["version"], "available_quantity_kg": "150",
        "provenance_source": "phone call with farmer", "attestation_method": "verbal: 150 kg sold at market"})
    assert changed.status_code == 200, changed.text
    assert report(http, org, lot["id"], 300).status_code == 201
    row = lot_row(http, org, lot["id"])
    assert D(row["available_quantity_kg"]) == D("150") and D(row["free_kg"]) == D("150")


def test_a_farmers_own_report_may_offer_more_up_to_the_harvest_and_says_so(http, org, factory) -> None:
    lot = org["lots"][0]
    assert report(http, org, lot["id"], 380, who="farmer_user").status_code == 201
    row = lot_row(http, org, lot["id"])
    assert D(row["available_quantity_kg"]) == D("380") and D(row["free_kg"]) == D("380")


def test_delivered_stock_is_not_reported_as_exposure_or_offered_again(http, org, factory) -> None:
    order = make_order(http, org, "200")
    commit_all(http, org, order)
    allocation = committed_on(http, org, order)
    lot_id = allocation["production_lot_id"]
    deliver(factory, org, allocation["id"], "200")
    # After delivering all 200 kg the farmer truthfully says 100 kg is left.
    farmer = "farmer_user" if lot_id == org["lots"][0]["id"] else "other_farmer"
    assert report(http, org, lot_id, 100, who=farmer).status_code == 201
    worker.run_once(factory)
    assert D(supply(http, org, order)["exposed_kg"]) == D("0")
    assert open_exceptions(factory, order["id"], ExceptionKind.CAPACITY_SHORTFALL) == []
    assert D(lot_row(http, org, lot_id)["free_kg"]) == D("100")  # the 200 delivered are not offered again
    # Nothing left: still no exposure, and nothing free.
    assert report(http, org, lot_id, 0, who=farmer).status_code == 201
    worker.run_once(factory)
    assert D(supply(http, org, order)["exposed_kg"]) == D("0") and D(lot_row(http, org, lot_id)["free_kg"]) == D("0")


def test_a_report_cannot_exceed_the_harvest_less_what_was_delivered(http, org, factory) -> None:
    order = make_order(http, org, "200")
    commit_all(http, org, order)
    allocation = committed_on(http, org, order)
    deliver(factory, org, allocation["id"], "200")
    refused = report(http, org, allocation["production_lot_id"], 250)  # declared harvest 400, 200 delivered
    assert refused.status_code == 422 and "delivered" in refused.json()["detail"]
    assert report(http, org, allocation["production_lot_id"], 200).status_code == 201


def test_partial_delivery_then_shortfall_exposes_only_the_undelivered_part(http, org, factory) -> None:
    order = make_order(http, org, "200")
    commit_all(http, org, order)
    allocation = committed_on(http, org, order)
    deliver(factory, org, allocation["id"], "50")
    assert report(http, org, allocation["production_lot_id"], 100).status_code == 201  # 150 still owed, 100 possible
    worker.run_once(factory)
    state = supply(http, org, order)
    row = next(a for a in state["allocations"] if a["id"] == allocation["id"])
    assert (D(state["exposed_kg"]), D(row["covered_kg"]), D(row["exposed_kg"])) == (D("50"), D("150"), D("50"))
    assert D(state["committed_quantity_kg"]) == D("200")  # the commitment is unchanged
    [exception] = open_exceptions(factory, order["id"], ExceptionKind.CAPACITY_SHORTFALL)
    assert exception.shortfall_kg == D("50")


def test_receipts_after_a_report_do_not_change_the_ceiling_and_close_the_exception_when_delivered(http, org, factory) -> None:
    order = make_order(http, org, "200")
    commit_all(http, org, order)
    allocation = committed_on(http, org, order)
    assert report(http, org, allocation["production_lot_id"], 150).status_code == 201
    worker.run_once(factory)
    assert D(supply(http, org, order)["exposed_kg"]) == D("50")
    deliver(factory, org, allocation["id"], "100")  # 100 of the 150 the supplier said they could do
    worker.run_once(factory)
    assert D(supply(http, org, order)["exposed_kg"]) == D("50")
    deliver(factory, org, allocation["id"], "100")  # the supplier delivered everything after all
    worker.run_once(factory)
    assert D(supply(http, org, order)["exposed_kg"]) == D("0")
    assert open_exceptions(factory, order["id"], ExceptionKind.CAPACITY_SHORTFALL) == []
