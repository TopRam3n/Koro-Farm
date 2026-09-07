"""Destructively reset only a clearly named PostgreSQL demo/test database."""
import os

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from src.backend.app.infrastructure.database.seed import seed_competition_demo
from src.backend.app.infrastructure.database.session import create_engine_from_url, create_session_factory


def assert_safe(url: str) -> None:
    parsed = make_url(url)
    environment = os.getenv("APP_ENV", "").lower()
    database = parsed.database or ""
    if parsed.get_backend_name() != "postgresql":
        raise SystemExit("Refusing reset: demo reset requires PostgreSQL")
    if environment not in {"test", "demo"}:
        raise SystemExit("Refusing reset: APP_ENV must be test or demo")
    if not database.endswith(("_test", "_demo")):
        raise SystemExit("Refusing reset: database name must end in _test or _demo")


def main() -> None:
    url = os.getenv("DATABASE_URL", "")
    assert_safe(url)
    engine = create_engine_from_url(url)
    tables = [name for name in inspect(engine).get_table_names() if name != "alembic_version"]
    if not tables:
        raise SystemExit("Refusing reset: migrated application tables were not found")
    quoted = ", ".join(f'"{name}"' for name in tables)
    with engine.begin() as connection:
        connection.exec_driver_sql(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    session = create_session_factory(url)()
    try:
        requirement_id = seed_competition_demo(session)
        print(f"Competition demo reset complete: requirement_id={requirement_id}")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
