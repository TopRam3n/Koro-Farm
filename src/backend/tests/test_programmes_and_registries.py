from datetime import date, timedelta
from uuid import UUID

from src.backend.app.assurance.domain.models import RecoveryRun, RecoveryStatus
from src.backend.app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus, SupplyHealth
from src.backend.app.fulfilment.domain.models import ReceivedSublot
from src.backend.app.infrastructure.database.seed import seed, seed_competition_demo
from src.backend.app.programmes.domain.models import Programme
from src.backend.app.reconciliation.domain.models import RequirementReconciliation, Shipment, ShipmentStatus
from src.backend.app.supply.domain.models import Farmer, ProductionLot


def test_programme_owns_requirements_and_reports_assurance(client, session) -> None:
    seed(session)
    buyer = session.query(Buyer).one()
    programme_response = client.post(
        "/programmes",
        json={
            "buyer_id": str(buyer.id),
            "name": "Hotel supply assurance",
            "commodity_scope": "GINGER",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=90)),
        },
    )
    assert programme_response.status_code == 201
    programme_id = programme_response.json()["id"]

    requirement_response = client.post(
        "/requirements",
        json={
            "buyer_id": str(buyer.id),
            "programme_id": programme_id,
            "crop": "GINGER",
            "grade": "A",
            "required_quantity_kg": "500",
            "delivery_window_start": str(date.today() + timedelta(days=5)),
            "delivery_window_end": str(date.today() + timedelta(days=10)),
        },
    )
    assert requirement_response.status_code == 201
    requirement_id = requirement_response.json()["id"]
    assert requirement_response.json()["programme_id"] == programme_id
    assert client.post(
        f"/requirements/{requirement_id}/plan", headers={"Idempotency-Key": "programme-plan"}
    ).status_code == 201

    detail = client.get(f"/programmes/{programme_id}")
    assert detail.status_code == 200
    assert detail.json()["requirement_count"] == 1
    assert detail.json()["requirements_by_supply_health"]["COVERED"] == 1
    assert detail.json()["committed_quantity_kg"] == "500.000"

    filtered = client.get(f"/requirements?programme_id={programme_id}")
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [requirement_id]


def test_programme_rejects_requirement_owned_by_another_buyer(client, session) -> None:
    first = Buyer(name="Buyer one", buyer_type="HOTEL", destination="Kingston")
    second = Buyer(name="Buyer two", buyer_type="EXPORTER", destination="Bridgetown")
    session.add_all([first, second])
    session.commit()
    programme = client.post(
        "/programmes",
        json={
            "buyer_id": str(first.id),
            "name": "Buyer one programme",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
        },
    ).json()
    requirement = client.post(
        "/requirements",
        json={
            "buyer_id": str(second.id),
            "crop": "GINGER",
            "grade": "A",
            "required_quantity_kg": "100",
            "delivery_window_start": "2026-09-10",
            "delivery_window_end": "2026-09-15",
        },
    ).json()
    response = client.post(f"/programmes/{programme['id']}/requirements/{requirement['id']}")
    assert response.status_code == 409


def test_operational_registries_and_command_center_are_source_backed(client, session) -> None:
    seed(session)
    buyer = session.query(Buyer).one()
    requirement = client.post(
        "/requirements",
        json={
            "buyer_id": str(buyer.id),
            "crop": "GINGER",
            "grade": "A",
            "required_quantity_kg": "500",
            "delivery_window_start": str(date.today() + timedelta(days=5)),
            "delivery_window_end": str(date.today() + timedelta(days=10)),
        },
    ).json()
    assert client.post(
        f"/requirements/{requirement['id']}/plan", headers={"Idempotency-Key": "registry-plan"}
    ).status_code == 201

    farmers = client.get("/farmers")
    assert farmers.status_code == 200
    assert len(farmers.json()["items"]) == 12
    assert all("committed_quantity_kg" in farmer for farmer in farmers.json()["items"])

    allocations = client.get(f"/allocations?requirement_id={requirement['id']}")
    assert allocations.status_code == 200
    assert allocations.json()["items"]
    assert all(item["requirement_id"] == requirement["id"] for item in allocations.json()["items"])

    activity = client.get("/activity")
    assert activity.status_code == 200
    assert any(item["event_type"] == "plan.created" for item in activity.json()["items"])

    summary = client.get("/command-center/summary")
    assert summary.status_code == 200
    assert summary.json()["requirements"]["by_supply_health"]["COVERED"] == 1
    assert summary.json()["physical_flow_kg"]["committed"] == "500.000"
    assert summary.json()["committed_concentration_by_parish"]


def test_empty_operational_registries_are_honest(client) -> None:
    assert client.get("/recovery-cases").json()["items"] == []
    assert client.get("/received-sublots").json()["items"] == []
    assert client.get("/shipments").json()["items"] == []
    assert client.get("/compliance-rules").json()["items"] == []


def test_demo_day_seed_has_portfolio_and_operational_scenarios(session) -> None:
    hero_id = seed_competition_demo(session)
    assert session.query(Buyer).count() == 3
    assert session.query(Programme).count() == 3
    assert session.query(Farmer).count() == 16
    assert session.query(ProductionLot).count() == 24
    assert session.query(Requirement).count() == 8
    assert session.query(Requirement).filter(Requirement.supply_health == SupplyHealth.COVERED).count() >= 5
    assert session.query(Requirement).filter(Requirement.supply_health == SupplyHealth.AT_RISK).count() >= 1
    assert session.query(Requirement).filter(Requirement.supply_health == SupplyHealth.UNPLANNED).count() == 1
    assert session.query(RecoveryRun).filter(RecoveryRun.status == RecoveryStatus.COMPLETED).count() >= 2
    assert session.query(ReceivedSublot).count() >= 2
    reconciled = session.get(Requirement, UUID("00000000-0000-0000-0000-000000000503"))
    assert reconciled.lifecycle_status == RequirementLifecycleStatus.RECONCILED
    assert session.get(RequirementReconciliation, reconciled.id).buyer_confirmed is True
    assert session.query(Shipment).filter(Shipment.requirement_id == reconciled.id,
                                          Shipment.status == ShipmentStatus.DELIVERED).count() == 1
    assert session.get(Requirement, hero_id).programme_id is not None

    # Re-running is idempotent and preserves the same logical portfolio.
    assert seed_competition_demo(session) == hero_id
    assert session.query(Requirement).count() == 8
