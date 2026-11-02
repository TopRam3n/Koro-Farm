"""Run the full Alembic chain against a fresh, throwaway PostgreSQL database.

SQLite tests build the schema with create_all and do not enforce VARCHAR lengths, so they cannot
catch migration defects. Skipped unless POSTGRES_TEST_DATABASE_URL is set.
"""
import os
import pathlib
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="dedicated PostgreSQL test database not configured")
BACKEND = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def fresh_database_url():
    name = f"korofarm_r1_disposable_mig_{uuid4().hex[:10]}"
    admin = create_engine(make_url(POSTGRES_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(POSTGRES_URL).set(database=name)
    try:
        yield url
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_migrations_apply_to_an_empty_database_and_store_long_crop_codes(fresh_database_url, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")

    engine = create_engine(fresh_database_url)
    with engine.begin() as connection:
        widths = dict(connection.execute(text(
            "select table_name, character_maximum_length from information_schema.columns where column_name = 'crop'")).all())
        assert widths == {"requirements": 64, "production_lots": 64, "compliance_rules": 64, "availability_watches": 64}
        shared = set(connection.execute(text("select code from crops where organization_id is null")).scalars())
        assert {"GINGER", "SWEET_POTATO", "SCOTCH_BONNET"} <= shared
        organization = connection.execute(text("select id from organizations limit 1")).scalar()
        buyer = uuid4()
        connection.execute(text("insert into buyers (id, organization_id, name, buyer_type, destination) "
                                "values (:id, :org, 'Migration buyer', 'HOTEL', 'Negril')"), {"id": buyer, "org": organization})
        for crop in ("SCOTCH_BONNET", "SWEET_POTATO"):
            connection.execute(text(
                "insert into requirements (id, buyer_id, crop, grade, required_quantity_kg, delivery_window_start, "
                "delivery_window_end, lifecycle_status, supply_health, plan_version, version) values "
                "(:id, :buyer, :crop, 'A', 730, '2026-12-01', '2026-12-12', 'DRAFT', 'UNPLANNED', 0, 1)"),
                {"id": uuid4(), "buyer": buyer, "crop": crop})
        stored = set(connection.execute(text("select crop from requirements")).scalars())
        assert stored == {"SCOTCH_BONNET", "SWEET_POTATO"}
        events = {row[0] for row in connection.execute(text(
            "select column_name from information_schema.columns where table_name = 'domain_events'"))}
        assert {"organization_id", "actor_id", "causation_id", "schema_version", "idempotency_key"} <= events
        lot_default = connection.execute(text(
            "select column_default from information_schema.columns "
            "where table_name = 'production_lots' and column_name = 'capacity_verification'")).scalar()
        assert "UNSPECIFIED" in lot_default
        unit_default = connection.execute(text(
            "select quantity_unit from requirements limit 1")).scalar()
        assert unit_default == "kg"
    engine.dispose()


def test_existing_consent_ids_are_classified_unsupported_not_deleted(fresh_database_url, monkeypatch) -> None:
    """An allocation written by the old planner keeps its (random) consent id but is marked UNSUPPORTED_LEGACY."""
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "0017_order_supply_records")

    engine = create_engine(fresh_database_url)
    legacy_consent, allocation = uuid4(), uuid4()
    with engine.begin() as c:
        organization = c.execute(text("select id from organizations limit 1")).scalar()
        buyer, farmer, lot, requirement, plan = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        c.execute(text("insert into buyers (id, organization_id, name, buyer_type, destination) values (:i, :o, 'B', 'HOTEL', 'X')"), {"i": buyer, "o": organization})
        c.execute(text("insert into farmers (id, organization_id, name, parish, active) values (:i, :o, 'F', 'Manchester', true)"), {"i": farmer, "o": organization})
        c.execute(text("insert into production_lots (id, farmer_id, crop, harvest_start, harvest_end, expected_quantity_kg, available_quantity_kg, "
                       "reserved_quantity_kg, quality_grade_estimate, availability_confidence, parish, status, last_verified_at, version) values "
                       "(:i, :f, 'GINGER', '2026-09-01', '2026-09-10', 100, 100, 80, 'A', 'HIGH', 'Manchester', 'AVAILABLE', now(), 1)"), {"i": lot, "f": farmer})
        c.execute(text("insert into requirements (id, buyer_id, crop, grade, required_quantity_kg, delivery_window_start, delivery_window_end, "
                       "lifecycle_status, supply_health, plan_version, version) values (:i, :b, 'GINGER', 'A', 80, '2026-09-01', '2026-09-10', "
                       "'ACTIVE', 'COVERED', 1, 2)"), {"i": requirement, "b": buyer})
        c.execute(text("insert into supply_plans (id, requirement_id, plan_version, planner_version, status, required_quantity_kg, "
                       "committed_quantity_kg, standby_quantity_kg, unfilled_quantity_kg) values (:i, :r, 1, 'legacy', 'FINALIZED', 80, 80, 0, 0)"),
                  {"i": plan, "r": requirement})
        c.execute(text("insert into supply_allocations (id, requirement_id, supply_plan_id, production_lot_id, role, status, quantity_kg, "
                       "consent_evidence_id, plan_version) values (:i, :r, :p, :l, 'COMMITTED', 'COMMITTED', 80, :c, 1)"),
                  {"i": allocation, "r": requirement, "p": plan, "l": lot, "c": legacy_consent})
    command.upgrade(config, "head")
    with engine.begin() as c:
        row = c.execute(text("select consent_status, consent_evidence_id, holds_reservation, status from supply_allocations where id = :i"),
                        {"i": allocation}).one()
        assert row.consent_status == "UNSUPPORTED_LEGACY"
        assert row.consent_evidence_id == legacy_consent  # preserved for history, not trusted
        assert row.holds_reservation is True and row.status == "COMMITTED"
        assert c.execute(text("select count(*) from supplier_consents")).scalar() == 0  # no consent was invented
    engine.dispose()


def test_recovery_role_policy_rows_and_round_trip(fresh_database_url, monkeypatch) -> None:
    """0022 keeps the informational permission rows in step with the WP3 policy, and downgrades cleanly."""
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    command.downgrade(config, "0021_worker_heartbeats")
    command.upgrade(config, "head")
    engine = create_engine(fresh_database_url)
    with engine.begin() as connection:
        rows = set(connection.execute(text("select role_code, permission_code from role_permissions where permission_code like 'recovery.%'")).all())
        assert ("SUPPLY_COORDINATOR", "recovery.approve") in rows
        assert ("PROCUREMENT_MANAGER", "recovery.approve_elevated") in rows and ("ORGANIZATION_ADMIN", "recovery.approve_elevated") in rows
        assert not [row for row in rows if row[1] == "recovery.execute"]
        tables = set(connection.execute(text("select table_name from information_schema.tables where table_name like 'recovery_%'")).scalars())
        assert {"recovery_tasks", "recovery_incidents", "recovery_steps", "recovery_proposals", "recovery_approvals",
                "recovery_executions", "recovery_approval_policies", "recovery_runs", "recovery_model_calls"} <= tables
    engine.dispose()


def test_fulfilment_accounting_backfill_preserves_legacy_records_and_round_trips(fresh_database_url, monkeypatch) -> None:
    """0024 copies legacy reconciliation and buyer-confirmed flags forward without changing them; the old yes/no
    flag becomes an unquantified legacy confirmation that is never counted as buyer-confirmed quantity."""
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "0023_model_calls_and_leases")
    engine = create_engine(fresh_database_url)
    buyer, farmer, lot, requirement, plan, allocation = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    node, sublot, shipment, delivery = uuid4(), uuid4(), uuid4(), uuid4()
    with engine.begin() as c:
        organization = c.execute(text("select id from organizations limit 1")).scalar()
        c.execute(text("insert into buyers (id, organization_id, name, buyer_type, destination) values (:i, :o, 'B', 'HOTEL', 'X')"), {"i": buyer, "o": organization})
        c.execute(text("insert into farmers (id, organization_id, name, parish, active) values (:i, :o, 'F', 'Manchester', true)"), {"i": farmer, "o": organization})
        c.execute(text("insert into production_lots (id, farmer_id, crop, harvest_start, harvest_end, expected_quantity_kg, available_quantity_kg, "
                       "reserved_quantity_kg, quality_grade_estimate, availability_confidence, parish, status, last_verified_at, version) values "
                       "(:i, :f, 'GINGER', '2026-09-01', '2026-09-10', 100, 100, 100, 'A', 'HIGH', 'Manchester', 'AVAILABLE', now(), 1)"), {"i": lot, "f": farmer})
        c.execute(text("insert into requirements (id, buyer_id, crop, grade, required_quantity_kg, delivery_window_start, delivery_window_end, "
                       "lifecycle_status, supply_health, plan_version, version) values (:i, :b, 'GINGER', 'A', 100, '2026-09-01', '2026-09-10', "
                       "'RECONCILED', 'COVERED', 1, 2)"), {"i": requirement, "b": buyer})
        c.execute(text("insert into supply_plans (id, requirement_id, plan_version, planner_version, status, required_quantity_kg, "
                       "committed_quantity_kg, standby_quantity_kg, unfilled_quantity_kg) values (:i, :r, 1, 'legacy', 'FINALIZED', 100, 100, 0, 0)"),
                  {"i": plan, "r": requirement})
        c.execute(text("insert into supply_allocations (id, requirement_id, supply_plan_id, production_lot_id, role, status, quantity_kg, "
                       "plan_version) values (:i, :r, :p, :l, 'COMMITTED', 'COMMITTED', 100, 1)"),
                  {"i": allocation, "r": requirement, "p": plan, "l": lot})
        c.execute(text("insert into fulfilment_nodes (id, organization_id, name, node_type, parish, active) values (:i, :o, 'Packhouse', 'PACKHOUSE', 'Manchester', true)"),
                  {"i": node, "o": organization})
        c.execute(text("insert into received_sublots (id, allocation_id, fulfilment_node_id, received_quantity_kg, accepted_quantity_kg, "
                       "rejected_quantity_kg, inspection_status, received_at, version) values (:i, :a, :n, 100, 95, 5, 'GRADED', now(), 1)"),
                  {"i": sublot, "a": allocation, "n": node})
        c.execute(text("insert into shipments (id, requirement_id, fulfilment_node_id, reference, status) values (:i, :r, :n, 'LEGACY-1', 'DELIVERED')"),
                  {"i": shipment, "r": requirement, "n": node})
        c.execute(text("insert into deliveries (id, shipment_id, delivered_quantity_kg, delivered_at, buyer_confirmed, buyer_confirmation_evidence) "
                       "values (:i, :s, 95, now(), true, 'email-001')"), {"i": delivery, "s": shipment})
        c.execute(text("insert into requirement_reconciliations (requirement_id, committed_quantity_kg, delivered_quantity_kg, accepted_quantity_kg, "
                       "quantity_variance_kg, accepted_fulfilment_rate_pct, on_time, buyer_confirmed, verification_evidence_reference) "
                       "values (:r, 100, 95, 95, -5, 95, true, true, 'check-001')"), {"r": requirement})
    command.upgrade(config, "head")
    with engine.begin() as c:
        record = c.execute(text("select version, status, legacy, figures, evidence_reference from reconciliation_records where requirement_id = :r"),
                           {"r": requirement}).one()
        assert (record.version, record.status, record.legacy, record.evidence_reference) == (1, "EFFECTIVE", True, "check-001")
        assert record.figures["delivered_kg"] == "95.000" and record.figures["legacy_buyer_confirmed_flag"] is True
        confirmation = c.execute(text("select channel, confirmed_quantity_kg, evidence_reference from buyer_confirmations where delivery_id = :d"),
                                 {"d": delivery}).one()
        assert confirmation.channel == "LEGACY_UNQUANTIFIED" and confirmation.confirmed_quantity_kg == 0
        assert confirmation.evidence_reference == "email-001"
        # The legacy rows are untouched.
        assert c.execute(text("select buyer_confirmed from deliveries where id = :d"), {"d": delivery}).scalar() is True
        assert c.execute(text("select count(*) from requirement_reconciliations")).scalar() == 1
        allocation_row = c.execute(text("select quantity_kg, released_quantity_kg from supply_allocations where id = :a"), {"a": allocation}).one()
        assert allocation_row.quantity_kg == 100 and allocation_row.released_quantity_kg == 0
        assert c.execute(text("select entry_type from received_sublots where id = :s"), {"s": sublot}).scalar() == "RECEIPT"
        # References are unique per site, not across tenants.
        other_node = uuid4()
        c.execute(text("insert into fulfilment_nodes (id, organization_id, name, node_type, parish, active) values (:i, :o, 'Other', 'PACKHOUSE', 'Clarendon', true)"),
                  {"i": other_node, "o": organization})
        c.execute(text("insert into shipments (id, requirement_id, fulfilment_node_id, reference, status) values (:i, :r, :n, 'LEGACY-1', 'OPEN')"),
                  {"i": uuid4(), "r": requirement, "n": other_node})
        c.execute(text("update requirements set lifecycle_status = 'CLOSED_WITH_VARIANCE' where id = :r"), {"r": requirement})
        rows = set(c.execute(text("select role_code, permission_code from role_permissions")).all())
        assert ("SUPPLY_COORDINATOR", "trade.reconcile") in rows and ("PROCUREMENT_MANAGER", "trade.reconcile") in rows
        assert ("WAREHOUSE_OPERATOR", "trade.reconcile") not in rows and ("AUDITOR", "audit.flag") in rows
        assert ("BUYER", "delivery.confirm_own") in rows
        c.execute(text("delete from shipments where fulfilment_node_id = :n"), {"n": other_node})
    command.downgrade(config, "0023_model_calls_and_leases")
    command.upgrade(config, "head")
    engine.dispose()
