"""R1 WP5: role-aware workspace (M1), buyer portal (M2) and the notification foundation (M3).

Runs on SQLite always and on PostgreSQL when POSTGRES_TEST_DATABASE_URL is set (two_orgs fixtures). Notifications
use only the disabled and synthetic providers: nothing here contacts a messaging service.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from test_capacity_exceptions import H, commit_all, make_order, org, supply  # noqa: F401  (fixtures)
from test_fulfilment_accounting import CONFIRM_RELAY, committed, receive, team  # noqa: F401  (fixtures)
from two_orgs import add_member, factory, http  # noqa: F401  (fixtures)
from src.backend.app import worker
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.core.config import UnsafeConfigurationError, validate_runtime_configuration
from src.backend.app.demand.domain.models import Buyer
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import ROLE_PERMISSIONS, RoleCode
from src.backend.app.notifications.application import providers, service
from src.backend.app.notifications.domain.models import Notification, NotificationStatusEvent

D = Decimal
NOW = "2026-10-30T10:00:00Z"


def ship_one(http, team, order, sublot, delivered, key):
    shipment = http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", f"sh-{key}"),
                         json={"fulfilment_node_id": team["node"], "reference": f"SHIP-{key}"}).json()["shipment_id"]
    assert http.post(f"/shipments/{shipment}/sublots", headers=H(team, "warehouse", f"add-{key}"), json={"received_sublot_id": sublot}).status_code == 200
    assert http.post(f"/shipments/{shipment}/dispatch", headers=H(team, "warehouse", f"dis-{key}"), json={}).status_code == 200
    delivery = http.post(f"/shipments/{shipment}/delivery", headers=H(team, "warehouse", f"del-{key}"),
                         json={"delivered_quantity_kg": str(delivered), "delivered_at": NOW})
    assert delivery.status_code == 200, delivery.text
    return shipment, delivery.json()["delivery_id"]


def two_deliveries(http, team):
    """One order with two delivered shipments (30 kg and 20 kg) of a 100 kg order, neither confirmed yet."""
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    allocation = committed(http, team, order)[0]["id"]
    first = receive(http, team, allocation, "30", "a", accepted="30")
    second = receive(http, team, allocation, "20", "b", accepted="20")
    _, delivery_a = ship_one(http, team, order, first, 30, "a")
    _, delivery_b = ship_one(http, team, order, second, 20, "b")
    return order, delivery_a, delivery_b


def other_organization(factory, role=RoleCode.SUPPLY_COORDINATOR, **links):
    with factory() as session:
        organization = Organization(id=uuid4(), name="Elsewhere Ltd", slug=f"else-{uuid4().hex[:6]}")
        session.add(organization); session.flush()
        if "buyer" in links:
            buyer = Buyer(organization_id=organization.id, name="Elsewhere Hotel", buyer_type="HOTEL", destination="Negril")
            session.add(buyer); session.flush()
            links = {"buyer_id": buyer.id}
        user = add_member(session, organization.id, role, "outsider", **links)
        session.commit()
    return {"org": organization.id, "coordinator": user.id}


# --- M1: role-aware workspace ---------------------------------------------------------------------------------------

def test_profile_lists_exactly_the_permissions_of_the_active_role(http, team) -> None:
    for who, role in (("coordinator", RoleCode.SUPPLY_COORDINATOR), ("warehouse", RoleCode.WAREHOUSE_OPERATOR),
                      ("auditor", RoleCode.AUDITOR), ("manager", RoleCode.PROCUREMENT_MANAGER), ("buyer_user", RoleCode.BUYER)):
        me = http.get("/me", headers=H(team, who))
        assert me.status_code == 200, me.text
        assert me.json()["permissions"] == sorted(p.value for p in ROLE_PERMISSIONS[role]), who
        assert "recovery.execute" not in me.json()["permissions"]


def test_fulfilment_overview_collects_each_queue_from_the_records_and_stays_in_the_organization(http, team, factory) -> None:
    order, delivery_a, delivery_b = two_deliveries(http, team)
    allocation = committed(http, team, order)[0]["id"]
    receive(http, team, allocation, "5", "ungraded")  # received, not graded
    open_shipment = http.post(f"/requirements/{order['id']}/shipments", headers=H(team, "warehouse", "open"),
                              json={"fulfilment_node_id": team["node"], "reference": "SHIP-OPEN"})
    assert open_shipment.status_code == 200
    assert http.post(f"/buyer/deliveries/{delivery_a}/confirmation", headers=H(team, "buyer_user", "c1"),
                     json={"confirmed_quantity_kg": "28", "discrepancy": True, "note": "two kilograms short"}).status_code == 200

    overview = http.get("/fulfilment-overview", headers=H(team, "warehouse"))
    assert overview.status_code == 200, overview.text
    queues = overview.json()["queues"]
    assert overview.json()["open_orders"] >= 1
    assert [i["receipt_id"] for i in queues["ungraded_receipts"]["items"]] and queues["ungraded_receipts"]["action_permission"] == "grading.record"
    assert [i["reference"] for i in queues["open_shipments"]["items"]] == ["SHIP-OPEN"]
    assert [i["delivery_id"] for i in queues["awaiting_buyer_confirmation"]["items"]] == [delivery_b]
    assert [i["description"] for i in queues["open_disputes"]["items"]] == ["two kilograms short"]
    assert queues["open_disputes"]["action_permission"] == "trade.reconcile"
    # Read-only for every staff role; buyers use their own portal; another organization sees nothing of this one.
    assert http.get("/fulfilment-overview", headers=H(team, "auditor")).status_code == 200
    assert http.get("/fulfilment-overview", headers=H(team, "buyer_user")).status_code == 403
    outsider = other_organization(factory)
    elsewhere = http.get("/fulfilment-overview", headers=H(outsider)).json()
    assert elsewhere["open_orders"] == 0 and all(q["count"] == 0 for q in elsewhere["queues"].values())


def test_only_supply_managers_can_start_planning(http, team) -> None:
    order = make_order(http, team, "100")
    for who in ("auditor", "warehouse", "manager", "admin"):
        refused = http.post(f"/requirements/{order['id']}/plan", headers=H(team, who, f"plan-{who}"))
        assert refused.status_code == 403, who
    assert http.get(f"/requirements/{order['id']}", headers=H(team)).json()["plan_version"] == 0
    assert http.post(f"/requirements/{order['id']}/plan", headers=H(team, key="plan-ok")).status_code == 201


# --- M2: buyer portal -----------------------------------------------------------------------------------------------

def test_buyer_portal_keeps_own_confirmations_staff_relays_disputes_and_outstanding_apart(http, team) -> None:
    order, delivery_a, delivery_b = two_deliveries(http, team)
    listed = http.get("/buyer/orders", headers=H(team, "buyer_user"))
    assert listed.status_code == 200 and [o["requirement_id"] for o in listed.json()] == [order["id"]]
    q = listed.json()[0]["quantities"]
    assert (q["required_kg"], q["delivered_kg"], q["awaiting_your_confirmation_kg"], q["still_to_deliver_kg"]) == ("100", "50", "50", "50")

    assert http.post(f"/buyer/deliveries/{delivery_a}/confirmation", headers=H(team, "buyer_user", "own"),
                     json={"confirmed_quantity_kg": "30"}).status_code == 200
    relay = {**CONFIRM_RELAY, "note": "=HYPERLINK(\"http://example.invalid\")"}
    assert http.post(f"/deliveries/{delivery_b}/confirmations", headers=H(team, key="relay"),
                     json={"confirmed_quantity_kg": "20", **relay}).status_code == 200
    detail = http.get(f"/buyer/orders/{order['id']}", headers=H(team, "buyer_user"))
    assert detail.status_code == 200, detail.text
    q = detail.json()["quantities"]
    assert (q["confirmed_by_you_kg"], q["relayed_by_staff_kg"], q["awaiting_your_confirmation_kg"]) == ("30", "20", "0")
    sources = {d["shipment_reference"]: d["current_statement"]["source"] for d in detail.json()["deliveries"]}
    assert sources == {"SHIP-a": "BUYER_ACCOUNT", "SHIP-b": "STAFF_RELAYED"}
    relayed = [d for d in detail.json()["deliveries"] if d["shipment_reference"] == "SHIP-b"][0]["current_statement"]
    assert relayed["source_label"] == "Relayed by staff from another channel" and relayed["buyer_representative"] == "Receiving clerk"
    # Staff records stay with staff: no supplier names, receipts or reconciliation versions.
    text = detail.text
    assert "farmer" not in text.lower() and "receipts" not in detail.json() and "reconciliations" not in detail.json()

    # A buyer's correction raises a dispute; its resolution is visible to the buyer. A staff note with no delivery is not.
    assert http.post(f"/buyer/deliveries/{delivery_a}/confirmation", headers=H(team, "buyer_user", "own2"),
                     json={"confirmed_quantity_kg": "27", "discrepancy": True, "note": "three kilograms bruised"}).status_code == 200
    assert http.post(f"/requirements/{order['id']}/disputes", headers=H(team),
                     json={"description": "internal: supplier paperwork late"}).status_code == 200
    detail = http.get(f"/buyer/orders/{order['id']}", headers=H(team, "buyer_user")).json()
    assert [d["description"] for d in detail["disputes"]] == ["three kilograms bruised"]
    assert detail["quantities"]["confirmed_by_you_kg"] == "27"
    history = [d for d in detail["deliveries"] if d["shipment_reference"] == "SHIP-a"][0]["statement_history"]
    assert [s["confirmed_quantity_kg"] for s in history] == ["30", "27"]
    dispute = detail["disputes"][0]["id"]
    assert http.post(f"/disputes/{dispute}/resolution", headers=H(team), json={"outcome": "RESOLVED", "resolution": "credit note for 3 kg"}).status_code == 200
    resolved = http.get(f"/buyer/orders/{order['id']}", headers=H(team, "buyer_user")).json()["disputes"][0]
    assert (resolved["status"], resolved["resolution"], resolved["raised_by"]) == ("RESOLVED", "credit note for 3 kg", "you")

    record = http.get(f"/buyer/orders/{order['id']}/delivery-record", headers=H(team, "buyer_user"))
    assert record.status_code == 200 and record.headers["content-type"].startswith("text/csv")
    assert "attachment" in record.headers["content-disposition"] and record.headers["cache-control"] == "no-store"
    rows = list(csv.DictReader(io.StringIO(record.text)))
    assert [(r["shipment_reference"], r["statement_number"], r["confirmed_kg"], r["current_statement"]) for r in rows] == [
        ("SHIP-a", "1", "30", "no (superseded)"), ("SHIP-a", "2", "27", "yes"), ("SHIP-b", "1", "20", "yes")]
    assert rows[2]["source"] == "Relayed by staff from another channel" and rows[2]["note"].startswith("'=")  # formula neutralised
    as_json = http.get(f"/buyer/orders/{order['id']}/delivery-record?format=json", headers=H(team, "buyer_user"))
    assert as_json.status_code == 200 and len(as_json.json()["rows"]) == 3
    assert http.get(f"/buyer/orders/{order['id']}/delivery-record?format=xlsx", headers=H(team, "buyer_user")).status_code == 422


def test_buyers_see_only_their_own_buyer_records_orders(http, team, factory) -> None:
    order, _, _ = two_deliveries(http, team)
    with factory() as session:
        other = Buyer(organization_id=team["org"], name="Other Hotel", buyer_type="HOTEL", destination="Ocho Rios")
        session.add(other); session.flush()
        team["stranger"] = add_member(session, team["org"], RoleCode.BUYER, "stranger", buyer_id=other.id).id
        team["unlinked"] = add_member(session, team["org"], RoleCode.BUYER, "unlinked").id
        session.commit()
    for who in ("stranger", "unlinked"):
        assert http.get("/buyer/orders", headers=H(team, who)).json() == []
        assert http.get(f"/buyer/orders/{order['id']}", headers=H(team, who)).status_code == 404
        assert http.get(f"/buyer/orders/{order['id']}/delivery-record", headers=H(team, who)).status_code == 404
    outsider = other_organization(factory, RoleCode.BUYER, buyer=True)
    assert http.get("/buyer/orders", headers=H(outsider)).json() == []
    assert http.get(f"/buyer/orders/{order['id']}", headers=H(outsider)).status_code == 404
    # Staff do not use the buyer portal, and a buyer cannot read the staff fulfilment record.
    assert http.get("/buyer/orders", headers=H(team)).status_code == 403
    assert http.get(f"/requirements/{order['id']}/fulfilment-record", headers=H(team, "buyer_user")).status_code == 403


# --- M3: notifications and consent to be contacted ---------------------------------------------------------------

def consent(http, team, farmer_id, address="+18765550123", granted=True, purposes=("SUPPLY_REQUESTS",), who="coordinator"):
    return http.post(f"/farmers/{farmer_id}/contact-consents", headers=H(team, who), json={
        "channel": "SMS", "address": address, "granted": granted, "purposes": list(purposes),
        "wording_version": "draft-2026-11", "how_given": "signed consent form", "evidence_reference": "form 12"})


def notifications(http, team, who="coordinator") -> list[dict]:
    response = http.get("/notifications", headers=H(team, who))
    assert response.status_code == 200, response.text
    return response.json()["notifications"]


@pytest.fixture()
def synthetic(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_PROVIDER", "synthetic")
    providers._synthetic.outbox.clear()
    yield providers._synthetic
    providers._synthetic.outbox.clear()


def test_consent_is_recorded_append_only_with_masked_addresses_and_role_checks(http, team, factory) -> None:
    farmer = team["farmers"][0]["id"]
    first = consent(http, team, farmer)
    assert first.status_code == 201, first.text
    assert first.json()["address"] == "+1876•••0123" and first.json()["state"] == "GRANTED"
    withdrawn = consent(http, team, farmer, granted=False, purposes=())
    assert withdrawn.status_code == 201 and withdrawn.json()["supersedes_id"] == first.json()["id"]
    history = http.get(f"/farmers/{farmer}/contact-consents", headers=H(team, "warehouse"))
    assert history.status_code == 200 and [c["state"] for c in history.json()] == ["WITHDRAWN", "GRANTED"]
    assert "0123" not in history.text.replace("•••0123", "")  # never the full number
    assert consent(http, team, farmer, who="auditor").status_code == 403
    assert consent(http, team, farmer, purposes=("MARKETING",)).status_code == 422
    assert consent(http, team, farmer, purposes=()).status_code == 422
    outsider = other_organization(factory)
    assert http.get(f"/farmers/{farmer}/contact-consents", headers=H(outsider)).status_code == 404
    with factory() as session:  # the address never enters the event stream
        events = session.scalars(select(DomainEvent).where(DomainEvent.event_type == "contact_consent.recorded")).all()
        assert events and all("+1876" not in str(e.payload) for e in events)


def test_requests_without_consent_are_blocked_and_visible(http, team, factory, synthetic) -> None:
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    worker.run_once(factory)
    rows = notifications(http, team)
    requests = [n for n in rows if n["template_key"] == "SUPPLIER_REQUEST"]
    assert requests and {n["status"] for n in requests} == {"BLOCKED_NO_CONSENT"}
    assert synthetic.outbox == []


def test_consented_requests_are_sent_through_the_synthetic_provider_and_withdrawal_stops_queued_ones(http, team, factory, synthetic) -> None:
    for farmer in team["farmers"]:
        assert consent(http, team, farmer["id"]).status_code == 201
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    worker.run_once(factory)
    sent = [n for n in notifications(http, team) if n["template_key"] == "SUPPLIER_REQUEST"]
    assert sent and {n["status"] for n in sent} == {"SENT"} and {n["provider"] for n in sent} == {"synthetic"}
    assert synthetic.outbox and all("kg of scotch bonnet" in m.body and m.address == "+18765550123" for m in synthetic.outbox)
    detail = http.get(f"/notifications/{sent[0]['id']}", headers=H(team)).json()
    assert [h["status"] for h in detail["history"]] == ["QUEUED", "SENT"] and detail["address"] == "+1876•••0123"
    # Processing the same events again creates nothing new.
    with factory() as session:
        count = len(session.scalars(select(Notification)).all())
        for message in session.scalars(select(OutboxMessage).where(OutboxMessage.topic == "solicitation.sent")):
            service.on_event(session, message)
        session.flush()
        assert len(session.scalars(select(Notification)).all()) == count

    # A withdrawal between queueing and sending stops the message.
    with factory() as session:
        event = session.scalars(select(DomainEvent).where(DomainEvent.event_type == "solicitation.sent")).first()
        message = OutboxMessage(event_id=uuid4(), topic="solicitation.sent", payload=event.payload)
        copy = DomainEvent(event_type="solicitation.sent", aggregate_type="requirement", aggregate_id=event.aggregate_id,
                           correlation_id=uuid4(), actor_type="user", actor_id="x", organization_id=event.organization_id,
                           payload=event.payload)
        session.add(copy); session.flush()
        message.event_id = copy.id
        queued = service.on_event(session, message)
        session.commit()
        recipient = str(queued[0].recipient_id)
    assert consent(http, team, recipient, granted=False, purposes=()).status_code == 201
    worker.run_once(factory)
    stopped = http.get(f"/notifications/{queued[0].id}", headers=H(team)).json()
    assert stopped["status"] == "BLOCKED_NO_CONSENT" and "withdrawn" in stopped["history"][-1]["detail"]


def test_failed_sends_retry_with_backoff_then_fail_visibly_and_disabled_provider_sends_nothing(http, team, factory, monkeypatch) -> None:
    farmer = team["farmers"][0]["id"]
    assert consent(http, team, farmer, address="+18765550199-fail").status_code == 201
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    monkeypatch.setenv("NOTIFICATION_PROVIDER", "none")
    worker.run_once(factory)
    rows = notifications(http, team)
    assert {n["status"] for n in rows if n["recipient_id"] == farmer} <= {"NOT_SENT_PROVIDER_DISABLED"}
    assert any(n["status"] == "NOT_SENT_PROVIDER_DISABLED" for n in rows if n["recipient_id"] == farmer)

    provider = providers.SyntheticProvider()
    with factory() as session:
        target = session.scalars(select(Notification).where(Notification.recipient_id == UUID(farmer))).first()
        target.status, target.attempts, target.next_attempt_at = "QUEUED", 0, None
        session.commit()
        target_id = target.id
    moment = datetime.now(timezone.utc)
    for attempt in range(service.MAX_ATTEMPTS):
        with factory() as session:
            service.dispatch_due(session, provider, moment)
            session.commit()
            row = session.get(Notification, target_id)
        moment += timedelta(seconds=service.RETRY_BASE_SECONDS * 2 ** attempt + 1)
    assert row.status == "FAILED" and row.attempts == service.MAX_ATTEMPTS and "synthetic failure" in row.last_error
    with factory() as session:
        statuses = [e.status for e in session.scalars(select(NotificationStatusEvent).where(
            NotificationStatusEvent.notification_id == target_id).order_by(NotificationStatusEvent.created_at, NotificationStatusEvent.id))]
    assert statuses.count("RETRY_SCHEDULED") == service.MAX_ATTEMPTS - 1 and statuses[-1] == "FAILED"
    assert provider.outbox == []


def test_agent_events_never_produce_a_message(http, team, factory) -> None:
    order = make_order(http, team, "100")
    commit_all(http, team, order)
    with factory() as session:
        original = session.scalars(select(DomainEvent).where(DomainEvent.event_type == "solicitation.sent")).first()
        drafted = DomainEvent(event_type="solicitation.sent", aggregate_type="requirement", aggregate_id=original.aggregate_id,
                              correlation_id=uuid4(), actor_type="agent", actor_id="recovery-agent",
                              organization_id=original.organization_id, payload=original.payload)
        session.add(drafted); session.flush()
        assert service.on_event(session, OutboxMessage(event_id=drafted.id, topic="solicitation.sent", payload=original.payload)) == []
        assert service.on_event(session, OutboxMessage(event_id=original.id, topic="requirement.updated", payload={})) == []


def test_notification_provider_configuration_fails_closed() -> None:
    validate_runtime_configuration({"APP_ENV": "development", "NOTIFICATION_PROVIDER": "synthetic"})
    for env in ({"APP_ENV": "development", "NOTIFICATION_PROVIDER": "twilio"},
                {"APP_ENV": "production", "NOTIFICATION_PROVIDER": "synthetic"}):
        with pytest.raises(UnsafeConfigurationError):
            validate_runtime_configuration(env)
    assert service.mask("grower@example.org") == "gr•••@example.org" and service.mask("123") == "•••"
