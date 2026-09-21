from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.app.infrastructure.database.base import Base
from src.backend.app.main import app
from src.backend.app.main_dependencies import get_session
from src.backend.app.core.auth import get_current_user
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context
from src.backend.app.identity.domain.permissions import PermissionCode, RoleCode
from uuid import UUID


@pytest.fixture()
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user"}
    app.dependency_overrides[get_authorization_context] = lambda: AuthorizationContext(
        user_id=UUID("00000000-0000-0000-0000-000000009001"),
        organization_id=UUID("00000000-0000-0000-0000-000000000900"),
        membership_id=UUID("00000000-0000-0000-0000-000000009002"),
        role=RoleCode.PLATFORM_ADMIN,
        permissions=frozenset(PermissionCode),
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
