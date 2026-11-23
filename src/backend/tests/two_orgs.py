"""Shared two-organization fixtures for tenancy and workflow tests.

Authorization runs through the real membership lookup; only the Supabase token check is replaced by a
test identity header (X-Test-User-ID). Fixtures run on SQLite always and on PostgreSQL when
POSTGRES_TEST_DATABASE_URL is set.
"""
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.app.compliance.domain.models import ComplianceRule
from src.backend.app.core.auth import get_current_user
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.economics.domain.models import LotCostInput
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, Role, UserAccount
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.infrastructure.database.base import Base
from src.backend.app.main import app
from src.backend.app.main_dependencies import get_session
from src.backend.app.programmes.domain.models import Programme
from src.backend.app.supply.domain.crops import ensure_shared_crops
from src.backend.app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not POSTGRES_URL, reason="PostgreSQL test URL not set"))]


@pytest.fixture(params=BACKENDS)
def factory(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    made = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with made() as setup:
        ensure_shared_crops(setup)
        setup.commit()
    yield made
    if request.param == "sqlite":
        Base.metadata.drop_all(engine)
    engine.dispose()


def _test_identity(x_test_user_id: str = Header(...)) -> dict:
    return {"id": x_test_user_id}


@pytest.fixture()
def http(factory):
    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_current_user] = _test_identity
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _org(session, label: str, crop_lot: Crop = Crop.GINGER) -> dict:
    org = Organization(id=uuid4(), name=f"{label} Trading", slug=f"{label.lower()}-{uuid4().hex[:6]}")
    user = UserAccount(id=uuid4(), email=f"{label.lower()}-{uuid4().hex[:6]}@example.test", display_name=f"{label} Coordinator")
    session.add_all([org, user]); session.flush()
    session.add(OrganizationMembership(user_id=user.id, organization_id=org.id, role_code=RoleCode.PLATFORM_ADMIN,
                                       status=MembershipStatus.ACTIVE, accepted_at=datetime.now(timezone.utc)))
    buyer = Buyer(organization_id=org.id, name=f"{label} Hotel", buyer_type="HOTEL", destination="Kingston")
    farmer = Farmer(organization_id=org.id, name=f"{label} Farmer", parish="Manchester")
    node = FulfilmentNode(organization_id=org.id, name=f"{label} Packhouse", node_type="PACKHOUSE", parish="Manchester")
    session.add_all([buyer, farmer, node]); session.flush()
    lot = ProductionLot(farmer_id=farmer.id, crop=crop_lot, harvest_start=date(2026, 12, 1), harvest_end=date(2026, 12, 20),
                        expected_quantity_kg=Decimal("1000"), available_quantity_kg=Decimal("1000"), reserved_quantity_kg=Decimal("0"),
                        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH, parish="Manchester",
                        status=ProductionLotStatus.AVAILABLE, last_verified_at=datetime.now(timezone.utc))
    session.add(lot); session.flush()
    session.add(LotCostInput(production_lot_id=lot.id, farmgate_price_per_kg_jmd=Decimal("300"), pickup_cost_jmd=0,
                             handling_grading_cost_per_kg_jmd=0, packaging_cost_per_kg_jmd=0, transport_cost_jmd=0,
                             expected_rejection_pct=0))
    requirements = []
    for quantity in ("400", "150"):
        requirement = Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A, required_quantity_kg=Decimal(quantity),
                                  delivery_window_start=date(2026, 12, 10), delivery_window_end=date(2026, 12, 15))
        session.add(requirement); requirements.append(requirement)
    programme = Programme(buyer_id=buyer.id, name=f"{label} Programme", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    corridor = TradeCorridor(organization_id=org.id, name=f"{label} corridor {uuid4().hex[:6]}", origin_country="Jamaica",
                             destination_country="Jamaica", transport_mode="ROAD")
    rule = ComplianceRule(organization_id=org.id, origin="Jamaica", destination="Jamaica", crop=Crop.GINGER, product_form="FRESH",
                          rule_name=f"{label} rule", issuing_body="Test body", description="Test-only rule", required_before="DISPATCH",
                          lead_time="1 day", effective_from=date(2020, 1, 1), source_citation="test", source_version="1",
                          last_verified_at=datetime(2026, 1, 1, tzinfo=timezone.utc), verified_by="test")
    session.add_all([programme, corridor, rule]); session.commit()
    return {"org": org.id, "user": user.id, "buyer": buyer.id, "farmer": farmer.id, "node": node.id, "lot": lot.id,
            "requirement": requirements[0].id, "spare_requirement": requirements[1].id, "programme": programme.id,
            "corridor": corridor.id, "rule": rule.id}


def _h(world: dict, key: str | None = None) -> dict:
    headers = {"X-Test-User-ID": str(world["user"]), "X-Organization-ID": str(world["org"])}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def ensure_roles(session) -> None:
    for code in RoleCode:
        if session.get(Role, code) is None:
            session.add(Role(code=code, name=code.value, description="test role", internal_only=False))
    session.flush()


def add_member(session, organization_id, role: RoleCode, label: str = "member", **links) -> UserAccount:
    user = UserAccount(id=uuid4(), email=f"{label}-{uuid4().hex[:8]}@example.test", display_name=label.title())
    session.add(user); session.flush()
    session.add(OrganizationMembership(user_id=user.id, organization_id=organization_id, role_code=role,
                                       status=MembershipStatus.ACTIVE, accepted_at=datetime.now(timezone.utc), **links))
    session.flush()
    return user


def as_user(user_id, organization_id, key: str | None = None) -> dict:
    headers = {"X-Test-User-ID": str(user_id), "X-Organization-ID": str(organization_id)}
    if key:
        headers["Idempotency-Key"] = key
    return headers
