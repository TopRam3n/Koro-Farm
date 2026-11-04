"""Database engine and sessions.

DATABASE_URL selects the database; the development default below is refused in staging and production
(core/config.py). Connection settings, all optional:

  DB_POOL_SIZE (5), DB_MAX_OVERFLOW (10), DB_POOL_RECYCLE_SECONDS (1800), DB_CONNECT_TIMEOUT_SECONDS (10),
  DB_APPLICATION_NAME (korofarm), DB_PREPARED_STATEMENTS (auto | on | off)

Supabase's shared pooler in transaction mode (port 6543) does not support prepared statements, so psycopg's
automatic preparation is switched off for it ("auto"). Session mode (port 5432) and direct connections keep it.
"""
import os
from collections.abc import Mapping

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://korofarm:korofarm@localhost:5432/korofarm"
TRANSACTION_POOLER_PORT = 6543


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def engine_options(url: str, env: Mapping[str, str] | None = None) -> dict:
    """create_engine keyword arguments for this URL; nothing here reads or returns a credential."""
    env = os.environ if env is None else env
    parsed = make_url(url)
    options: dict = {"pool_pre_ping": True}
    if parsed.get_backend_name() != "postgresql":
        return options
    options.update(
        pool_size=int(env.get("DB_POOL_SIZE", "5")),
        max_overflow=int(env.get("DB_MAX_OVERFLOW", "10")),
        pool_recycle=int(env.get("DB_POOL_RECYCLE_SECONDS", "1800")),
    )
    connect_args: dict = {
        "connect_timeout": int(env.get("DB_CONNECT_TIMEOUT_SECONDS", "10")),
        "application_name": env.get("DB_APPLICATION_NAME", "korofarm")[:63],
    }
    prepared = env.get("DB_PREPARED_STATEMENTS", "auto").strip().lower()
    if prepared not in ("auto", "on", "off"):
        raise ValueError("DB_PREPARED_STATEMENTS must be auto, on or off")
    if prepared == "off" or (prepared == "auto" and parsed.port == TRANSACTION_POOLER_PORT):
        if parsed.get_driver_name() == "psycopg":
            connect_args["prepare_threshold"] = None
    options["connect_args"] = connect_args
    return options


def create_engine_from_url(url: str | None = None) -> Engine:
    url = url or database_url()
    return create_engine(url, **engine_options(url))


def create_session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine_from_url(url), autoflush=False, expire_on_commit=False)
