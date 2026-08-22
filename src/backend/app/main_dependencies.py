from collections.abc import Generator

from sqlalchemy.orm import Session

from src.backend.app.infrastructure.database.session import create_session_factory

SessionLocal = create_session_factory()


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
