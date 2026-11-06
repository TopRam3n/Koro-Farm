"""Run the full Alembic chain against a fresh, throwaway PostgreSQL database.

SQLite tests build the schema with create_all and do not enforce VARCHAR lengths, so they cannot
catch migration defects. Skipped unless POSTGRES_TEST_DATABASE_URL is set.
"""
import os
from datetime import datetime, timezone
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
        c.execute(text("insert into shipments (id, requirement_id, fulfilment_node_id, reference, status, dispatched_at) "
                       "values (:i, :r, :n, 'LEGACY-1', 'DELIVERED', '2026-09-05T10:00:00+00:00')"),
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
        # 0025: the old dispatch time is labelled as a recording time, never rewritten or guessed.
        legacy = c.execute(text("select dispatched_at, dispatch_time_basis, dispatch_recorded_at from shipments where id = :s"), {"s": shipment}).one()
        assert legacy.dispatch_time_basis == "LEGACY" and legacy.dispatch_recorded_at is None
        assert legacy.dispatched_at == datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
        assert c.execute(text("select recorded_at from deliveries where id = :d"), {"d": delivery}).scalar() is None
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


def _supabase_like_roles(url) -> None:
    """Create Supabase's client roles (cluster-wide, NOLOGIN, harmless) and its default grants in this database."""
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        for role in ("anon", "authenticated", "service_role"):
            if not connection.execute(text("select 1 from pg_roles where rolname = :r"), {"r": role}).first():
                try:
                    connection.execute(text(f'create role "{role}" nologin'))
                except Exception:  # created concurrently by another run
                    pass
        connection.execute(text("alter default privileges in schema public grant all on tables to anon, authenticated, service_role"))
        connection.execute(text("alter default privileges in schema public grant all on sequences to anon, authenticated, service_role"))
        connection.execute(text("alter default privileges in schema public grant all on functions to anon, authenticated, service_role"))
    engine.dispose()


def test_supabase_client_roles_reach_no_table_after_migrating(fresh_database_url, monkeypatch) -> None:
    """0026: on a Supabase-like database the Data API roles hold no privilege and every table has RLS, including
    tables a later migration adds (this test fails if a new table is created without enabling RLS)."""
    from src.backend.app.infrastructure.database.data_api import exposure_findings, lockdown_statements

    _supabase_like_roles(fresh_database_url)
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "0025_physical_event_times")
    engine = create_engine(fresh_database_url)
    with engine.connect() as connection:
        before = exposure_findings(connection)
    assert before["applicable"] and before["exposed"]
    assert {"object": "supply_allocations", "role": "anon"} in before["table_privileges"]

    command.upgrade(config, "head")
    with engine.connect() as connection:
        after = exposure_findings(connection)
        assert after["applicable"] and not after["exposed"], after
        assert after["default_privileges"] == []
        assert lockdown_statements(connection)[:1] == ["revoke all on all tables in schema public from \"anon\", \"authenticated\", \"service_role\""]
        assert not [s for s in lockdown_statements(connection) if "enable row level security" in s]
    # The backend (table owner) is unaffected by RLS; tables created later get no client grants.
    with engine.begin() as connection:
        assert connection.execute(text("select count(*) from roles")).scalar() > 0
        connection.execute(text("create table later_table (id int)"))
        assert not connection.execute(text("select has_table_privilege('anon', 'later_table', 'SELECT')")).scalar()
    with engine.connect() as connection:
        assert exposure_findings(connection)["tables_without_rls"] == ["later_table"]
        assert lockdown_statements(connection)[-1] == 'alter table public."later_table" enable row level security'
    engine.dispose()


def test_data_api_lockdown_needs_the_supabase_roles(fresh_database_url) -> None:
    from src.backend.app.infrastructure.database.data_api import exposure_findings, lockdown_statements

    engine = create_engine(fresh_database_url)
    with engine.connect() as connection:
        absent = ("korofarm_absent_role_a", "korofarm_absent_role_b")
        findings = exposure_findings(connection, absent)
        assert findings["applicable"] is False and findings["exposed"] is False and findings["roles"] == []
        assert not any(findings[key] for key in ("table_privileges", "sequence_privileges", "function_privileges",
                                                 "tables_without_rls", "default_privileges"))
        assert lockdown_statements(connection, absent) == []
    engine.dispose()


def test_alembic_accepts_url_encoded_passwords(fresh_database_url, monkeypatch) -> None:
    """A password containing reserved characters is URL-encoded (%40 for @); configparser must not choke on it."""
    name = f"kf_pct_{uuid4().hex[:8]}"
    admin = create_engine(fresh_database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"create role {name} login password 'p@ss%word'"))
        connection.execute(text(f"grant all on schema public to {name}"))
        # A migration role also needs CREATE on the database for 0029's agri schema.
        connection.execute(text(f'grant create on database "{fresh_database_url.database}" to {name}'))
    user_engine = None
    try:
        url = fresh_database_url.set(username=name, password="p@ss%word")
        rendered = url.render_as_string(hide_password=False)
        assert "%40" in rendered and "%25" in rendered
        monkeypatch.setenv("DATABASE_URL", rendered)
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")
        user_engine = create_engine(url)
        with user_engine.connect() as connection:
            from alembic.script import ScriptDirectory
            head = ScriptDirectory.from_config(config).get_current_head()
            assert connection.execute(text("select version_num from alembic_version")).scalar() == head
    finally:
        if user_engine is not None:
            user_engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f"drop owned by {name}"))
            connection.execute(text(f"drop role {name}"))
        admin.dispose()


def test_readiness_check_against_a_migrated_supabase_like_database(fresh_database_url, monkeypatch) -> None:
    """check_staging's database checks on a real PostgreSQL: migrations at head, no Data API exposure. The local
    disposable server has no TLS, and the check must say so rather than pass."""
    from src.backend.scripts import check_staging

    _supabase_like_roles(fresh_database_url)
    engine = create_engine(fresh_database_url)
    behind = check_staging.check_migrations(engine)
    assert behind.status == "FAIL" and "run the migrations" in behind.detail
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    database = {c.name: c for c in check_staging.check_database(engine)}
    assert database["database"].status == "PASS" and "PostgreSQL" in database["database"].detail
    with engine.connect() as connection:
        encrypted = connection.execute(text("select ssl from pg_stat_ssl where pid = pg_backend_pid()")).scalar()
    assert database["database_tls"].status == ("PASS" if encrypted else "FAIL")
    assert encrypted or "NOT encrypted" in database["database_tls"].detail
    assert check_staging.check_migrations(engine).status == "PASS"
    grants = check_staging.check_data_api_grants(engine)
    assert grants.status == "PASS", grants.detail
    with engine.begin() as connection:
        connection.execute(text("grant select on organizations to anon"))
    exposed = check_staging.check_data_api_grants(engine)
    assert exposed.status == "FAIL" and "1 tables granted" in exposed.detail
    engine.dispose()


def test_lockdown_can_be_reapplied_after_grants_reappear(fresh_database_url, monkeypatch, capsys) -> None:
    """After a restore into a project with default grants, data_api_lockdown removes them again (dry run first)."""
    from src.backend.app.infrastructure.database.data_api import exposure_findings
    from src.backend.scripts import data_api_lockdown

    _supabase_like_roles(fresh_database_url)
    monkeypatch.setenv("DATABASE_URL", fresh_database_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    engine = create_engine(fresh_database_url)
    with engine.begin() as connection:  # what a restore under the new project's default grants looks like
        connection.execute(text("grant all on all tables in schema public to anon, authenticated"))
        connection.execute(text("alter table users disable row level security"))
    assert data_api_lockdown.main([], env={"APP_ENV": "staging"}, engine=engine) == 0
    assert "dry run: nothing was changed" in capsys.readouterr().out
    with engine.connect() as connection:
        assert exposure_findings(connection)["exposed"]
    assert data_api_lockdown.main(["--apply"], env={"APP_ENV": "staging"}, engine=engine) == 0
    assert "applied; nothing exposed" in capsys.readouterr().out
    with engine.connect() as connection:
        assert not exposure_findings(connection)["exposed"]
        assert connection.execute(text("select count(*) from roles")).scalar() == 8  # rows untouched
    assert data_api_lockdown.main(["--apply"], env={"APP_ENV": "production"}, engine=engine) == 2
    engine.dispose()



def _migrate(url, monkeypatch, revision="head"):
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, revision)


def _drop_roles(engine, *roles) -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        for role in roles:
            if connection.execute(text("select 1 from pg_roles where rolname = :r"), {"r": role}).first():
                connection.execute(text(f'drop owned by "{role}" cascade'))
                connection.execute(text(f'drop role "{role}"'))


def test_functions_executable_through_public_are_caught_and_closed_by_0027(fresh_database_url, monkeypatch) -> None:
    """0026 revoked only direct grants. PostgreSQL gives every new function EXECUTE through PUBLIC, which the client
    roles inherit; the checker must see it (existing function, default and probe) and 0027 must close it."""
    from src.backend.app.infrastructure.database.data_api import exposure_findings
    from src.backend.scripts import check_staging

    _supabase_like_roles(fresh_database_url)
    _migrate(fresh_database_url, monkeypatch, "0026_supabase_data_api_lockdown")
    engine = create_engine(fresh_database_url)
    with engine.begin() as connection:
        connection.execute(text("create function public.kf_existing() returns integer language sql as 'select 1'"))
    with engine.connect() as connection:
        before = exposure_findings(connection)
    assert {"object": "kf_existing()", "role": "anon", "via_public": True} in before["function_privileges"]
    assert {"owner": make_url(POSTGRES_URL).username, "object_type": "f", "grantee": "PUBLIC", "role": "anon",
            "source": "built-in default"} in before["default_privileges"]
    assert {"object": "function", "role": "anon"} in before["future_objects"]["exposed"]
    grants = check_staging.check_data_api_grants(engine)
    assert grants.status == "FAIL" and "through PUBLIC" in grants.detail and "would be reachable" in grants.detail

    _migrate(fresh_database_url, monkeypatch)
    with engine.connect() as connection:
        after = exposure_findings(connection)
        assert not after["exposed"] and after["verified"], after
    with engine.begin() as connection:
        connection.execute(text("create function public.kf_later() returns integer language sql as 'select 2'"))
        assert not connection.execute(text("select has_function_privilege('anon', 'public.kf_later()', 'EXECUTE')")).scalar()
    assert check_staging.check_data_api_grants(engine).status == "PASS"
    engine.dispose()


def test_column_grants_and_grants_through_role_membership_are_effective_privileges(fresh_database_url, monkeypatch) -> None:
    from src.backend.app.infrastructure.database.data_api import exposure_findings
    from src.backend.scripts import check_staging

    _supabase_like_roles(fresh_database_url)
    _migrate(fresh_database_url, monkeypatch)
    engine = create_engine(fresh_database_url)
    intermediary = f"kf_intermediary_{uuid4().hex[:8]}"
    try:
        with engine.begin() as connection:
            connection.execute(text("grant select (name) on organizations to anon"))  # column-level only
            assert not connection.execute(text("select has_table_privilege('anon', 'organizations', 'SELECT')")).scalar()
        with engine.connect() as connection:
            assert {"object": "organizations", "role": "anon"} in exposure_findings(connection)["table_privileges"]
        assert check_staging.check_data_api_grants(engine).status == "FAIL"
        with engine.begin() as connection:
            connection.execute(text("revoke all on organizations from anon"))
            connection.execute(text(f'create role "{intermediary}" nologin'))
            connection.execute(text(f'grant select on farmers to "{intermediary}"'))
            connection.execute(text(f'grant "{intermediary}" to authenticated'))
        with engine.connect() as connection:
            findings = exposure_findings(connection)
        assert findings["table_privileges"] == [{"object": "farmers", "role": "authenticated"}]
        assert check_staging.check_data_api_grants(engine).status == "FAIL"
    finally:
        _drop_roles(engine, intermediary)
        engine.dispose()


def test_default_privileges_for_new_objects_are_caught_by_the_catalog_and_the_probe(fresh_database_url, monkeypatch) -> None:
    """Objects created later: a default grant reaching a client role through membership, and the default privileges of
    another role that owns objects in public, which the lockdown (connected role only) cannot remove."""
    from src.backend.app.infrastructure.database.data_api import exposure_findings, lockdown_statements
    from src.backend.scripts import check_staging

    _supabase_like_roles(fresh_database_url)
    _migrate(fresh_database_url, monkeypatch)
    engine = create_engine(fresh_database_url)
    intermediary, other_owner = f"kf_intermediary_{uuid4().hex[:8]}", f"kf_other_owner_{uuid4().hex[:8]}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'create role "{intermediary}" nologin'))
            connection.execute(text(f'grant "{intermediary}" to anon'))
            connection.execute(text(f'alter default privileges in schema public grant select on tables to "{intermediary}"'))
        with engine.connect() as connection:
            findings = exposure_findings(connection)
        assert not findings["table_privileges"]  # nothing reachable today ...
        assert {"object": "table", "role": "anon"} in findings["future_objects"]["exposed"]  # ... but tomorrow
        assert {"object": "view", "role": "anon"} in findings["future_objects"]["exposed"]
        assert [row for row in findings["default_privileges"] if row["grantee"] == intermediary and row["role"] == "anon"]
        grants = check_staging.check_data_api_grants(engine)
        assert grants.status == "FAIL" and "a newly created table (anon)" in grants.detail
        with engine.begin() as connection:
            connection.execute(text(f'alter default privileges in schema public revoke select on tables from "{intermediary}"'))
        assert check_staging.check_data_api_grants(engine).status == "PASS"

        with engine.begin() as connection:
            connection.execute(text(f'create role "{other_owner}" nologin'))
            connection.execute(text("create table public.kf_foreign (id integer)"))
            connection.execute(text("alter table public.kf_foreign enable row level security"))
            connection.execute(text(f'alter table public.kf_foreign owner to "{other_owner}"'))
            connection.execute(text(f'alter default privileges for role "{other_owner}" revoke execute on functions from public'))
            connection.execute(text(f'alter default privileges for role "{other_owner}" in schema public grant select on tables to anon'))
        with engine.begin() as connection:
            for statement in lockdown_statements(connection):
                connection.execute(text(statement))
        with engine.connect() as connection:
            findings = exposure_findings(connection)
        assert {"owner": other_owner, "object_type": "r", "grantee": "anon", "role": "anon",
                "source": "schema public"} in findings["default_privileges"]
        assert {"object": "kf_foreign", "kind": "r", "owner": other_owner} in findings["objects_not_owned"]
        assert check_staging.check_data_api_grants(engine).status == "FAIL"
    finally:
        _drop_roles(engine, intermediary, other_owner)
        engine.dispose()


def test_the_probe_leaves_nothing_behind_and_unverifiable_new_objects_fail(fresh_database_url, monkeypatch) -> None:
    from src.backend.app.infrastructure.database.data_api import exposure_findings
    from src.backend.scripts import check_staging

    _supabase_like_roles(fresh_database_url)
    _migrate(fresh_database_url, monkeypatch)
    engine = create_engine(fresh_database_url)
    count = text("select (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                 "where n.nspname = 'public') + (select count(*) from pg_proc p join pg_namespace n "
                 "on n.oid = p.pronamespace where n.nspname = 'public')")
    with engine.connect() as connection:
        before = connection.execute(count).scalar()
        assert exposure_findings(connection)["future_objects"]["ran"]
        assert connection.execute(count).scalar() == before
    with engine.connect() as connection:
        assert connection.execute(count).scalar() == before  # nothing committed either

    reader = f"kf_reader_{uuid4().hex[:8]}"  # can read the catalog but cannot create in public
    try:
        with engine.begin() as connection:
            connection.execute(text(f'create role "{reader}" nologin'))
            connection.execute(text(f'grant usage on schema public to "{reader}"'))
            connection.execute(text(f'alter default privileges for role "{reader}" revoke execute on functions from public'))
        as_reader = create_engine(fresh_database_url, connect_args={"options": f"-c role={reader}"})
        with as_reader.connect() as connection:
            assert connection.execute(text("select current_user")).scalar() == reader
            future = exposure_findings(connection)["future_objects"]
        assert future["ran"] is False and future["reason"]
        grants = check_staging.check_data_api_grants(as_reader)
        assert grants.status == "FAIL" and "could not be verified" in grants.detail
        as_reader.dispose()
    finally:
        _drop_roles(engine, reader)
        engine.dispose()


def test_migrations_explain_a_missing_database_privilege_and_leave_nothing_half_applied(fresh_database_url, monkeypatch) -> None:
    """Documented privileges (deploy/sql/README.md): the migration role needs CREATE on the database for 0029's agri
    schema. Without it the upgrade stops with that explanation, and the transaction leaves no agri schema behind."""
    name = f"kf_restricted_{uuid4().hex[:8]}"
    admin = create_engine(fresh_database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"create role {name} login password 'restricted-pw-1'"))
        connection.execute(text(f"grant all on schema public to {name}"))
    try:
        url = fresh_database_url.set(username=name, password="restricted-pw-1")
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        with pytest.raises(Exception, match="needs CREATE on database"):
            command.upgrade(config, "head")
        with admin.connect() as connection:
            assert not connection.execute(text("select exists (select 1 from pg_namespace where nspname = 'agri')")).scalar()
        # With the documented privilege the same role migrates to head.
        with admin.connect() as connection:
            connection.execute(text(f'grant create on database "{fresh_database_url.database}" to {name}'))
        command.upgrade(config, "head")
        from alembic.script import ScriptDirectory
        user_engine = create_engine(url)
        with user_engine.connect() as connection:
            assert connection.execute(text("select version_num from alembic_version")).scalar() == ScriptDirectory.from_config(config).get_current_head()
        user_engine.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f"drop owned by {name} cascade"))
            connection.execute(text(f"revoke all on database \"{fresh_database_url.database}\" from {name}"))
            connection.execute(text(f"drop role {name}"))
        admin.dispose()
