import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://korofarm:korofarm@localhost:5432/korofarm"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_engine_from_url(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def create_session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine_from_url(url), autoflush=False, expire_on_commit=False)
