"""WP2 review: the API reports supply-exception monitoring truthfully and never assumes the worker is running."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update

from test_capacity_exceptions import H, commit_all, make_order, org, report, supply  # noqa: F401
from two_orgs import add_member, as_user, ensure_roles, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app import worker
from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage, WorkerHeartbeat
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.supply.domain.planning_models import SupplyAllocation

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def beat(factory, at):
    worker.beat(factory, f"test-{uuid4().hex[:6]}", at, {"messages": 0}, now=at)


def probe(http):
    response = http.get("/health/worker")
    return response.status_code, response.json()


def test_no_worker_ever_seen_is_degraded_not_operational(http, factory) -> None:
    code, body = probe(http)
    assert code == 503 and body["status"] == "DEGRADED" and "worker_never_started" in body["reasons"]
    assert http.get("/health").json() == {"status": "ok"}  # the API itself is up; that is all /health says


def test_a_fresh_heartbeat_is_operational_and_a_silent_worker_is_stopped(http, factory) -> None:
    beat(factory, NOW())
    assert probe(http) == (200, probe(http)[1]) and probe(http)[1]["status"] == "OPERATIONAL"
    with factory() as session:
        session.execute(update(WorkerHeartbeat).values(last_beat_at=NOW() - timedelta(minutes=5)))
        session.commit()
    code, body = probe(http)
    assert code == 503 and body["worker"] == "STOPPED" and "worker_not_running" in body["reasons"]


def test_backlog_overdue_deadlines_and_dead_letters_degrade_monitoring_even_with_a_live_worker(http, org, factory) -> None:
    beat(factory, NOW())
    assert report(http, org, org["lots"][0]["id"], 250).status_code == 201
    with factory() as session:  # the worker has not picked the report up for two minutes
        session.execute(update(OutboxMessage).values(created_at=NOW() - timedelta(minutes=2)))
        session.commit()
    assert "processing_overdue" in probe(http)[1]["reasons"]

    worker.run_once(factory)
    beat(factory, NOW())
    assert probe(http)[0] == 200

    order = make_order(http, org, "100")
    commit_all(http, org, order, roles=())  # planned only
    allocation_id = supply(http, org, order)["allocations"][0]["id"]
    assert http.post(f"/allocations/{allocation_id}/solicit", headers=H(org, key="sol"), json={}).status_code == 200
    with factory() as session:  # its deadline passed and no timer has handled it
        session.execute(update(SupplyAllocation).values(response_due_at=NOW() - timedelta(minutes=5)))
        session.commit()
    assert "deadlines_overdue" in probe(http)[1]["reasons"]
    worker.run_once(factory)
    beat(factory, NOW())
    assert probe(http)[0] == 200

    with factory() as session:
        session.execute(update(OutboxMessage).values(status="DEAD", last_error="boom"))
        session.commit()
    code, body = probe(http)
    assert code == 503 and "dead_letters" in body["reasons"]


def test_status_is_for_signed_in_staff_and_counts_only_their_organization(http, org, factory) -> None:
    beat(factory, NOW())
    assert report(http, org, org["lots"][0]["id"], 250).status_code == 201
    with factory() as session:
        session.execute(update(OutboxMessage).where(OutboxMessage.topic == "lot.capacity_reported").values(status="DEAD", last_error="boom"))
        ensure_roles(session)
        other = Organization(id=uuid4(), name="Elsewhere", slug=f"else-{uuid4().hex[:6]}")
        session.add(other); session.flush()
        outsider = add_member(session, other.id, RoleCode.SUPPLY_COORDINATOR, "outsider")
        session.commit()
        assert session.scalar(select(DomainEvent.organization_id).join(OutboxMessage, OutboxMessage.event_id == DomainEvent.id)
                              .where(OutboxMessage.status == "DEAD")) == org["org"]

    mine = http.get("/system/status", headers=H(org)).json()
    assert mine["status"] == "DEGRADED" and mine["processing"]["dead_letters"] == 1
    theirs = http.get("/system/status", headers=as_user(outsider.id, other.id)).json()
    assert theirs["processing"]["dead_letters"] == 0 and theirs["worker"]["state"] == "RUNNING"
    assert http.get("/system/status", headers=H(org, "farmer_user")).status_code == 403
    # This harness replaces bearer auth with a required test header, so "no identity" is refused as 422 here (401 live).
    assert http.get("/system/status").status_code in (401, 422)
