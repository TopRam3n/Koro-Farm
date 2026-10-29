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
    engine.dispose()
