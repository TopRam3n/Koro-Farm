"""Phase 5 tests: farmer history directory, RBAC, tenant isolation and reporting."""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.models import Organization
from app.identity.domain.permissions import ROLE_PERMISSIONS, RoleCode
from app.infrastructure.database.base import Base
from app.main_dependencies import get_session
from app.supply.api.farmer_history import router as history_router
from app.supply.domain.history_models import Farm, FarmerCrop, HistoricalProduction
from app.supply.domain.models import Farmer


@pytest.fixture
def service():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Organization.__table__, Farmer.__table__, Farm.__table__, FarmerCrop.__table__, HistoricalProduction.__table__])
    factory = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    app = FastAPI()
    app.include_router(history_router)
    with factory() as db:
        org_a, org_b = Organization(id=uuid4(), name='Org A', slug='org-a'), Organization(id=uuid4(), name='Org B', slug='org-b')
        farmers = [
            Farmer(id=uuid4(), organization_id=org_a.id, name='Anne Green', parish='Portland'),
            Farmer(id=uuid4(), organization_id=org_a.id, name='Brian Blue', parish='St. Mary'),
            Farmer(id=uuid4(), organization_id=org_b.id, name='Cross Org', parish='Kingston'),
        ]
        db.add_all([org_a, org_b, *farmers]); db.flush()
        db.add_all([
            Farm(farmer_id=farmers[0].id, name='Anne Farms', parish='Portland'),
            FarmerCrop(farmer_id=farmers[0].id, crop='GINGER'),
            HistoricalProduction(farmer_id=farmers[0].id, crop='GINGER', production_year=2023, production_quarter=1, production_kg=Decimal('100.000'), data_source='KOROFARM_DEMO', is_simulated=True),
            HistoricalProduction(farmer_id=farmers[0].id, crop='GINGER', production_year=2025, production_quarter=2, production_kg=Decimal('200.000'), data_source='KOROFARM_DEMO', is_simulated=True),
            HistoricalProduction(farmer_id=farmers[2].id, crop='GINGER', production_year=2024, production_quarter=1, production_kg=Decimal('999.000'), data_source='KOROFARM_DEMO', is_simulated=True),
        ])
        db.commit()

    state = {'context': AuthorizationContext(user_id=uuid4(), organization_id=org_a.id, membership_id=uuid4(), role=RoleCode.SUPPLY_COORDINATOR, permissions=ROLE_PERMISSIONS[RoleCode.SUPPLY_COORDINATOR])}

    def db_provider():
        with factory() as session:
            yield session

    def role_context():
        return state['context']

    app.dependency_overrides[get_session] = db_provider
    app.dependency_overrides[get_authorization_context] = role_context
    with TestClient(app) as client:
        def set_role(role, *, org_id=org_a.id, farmer_id=None):
            state['context'] = AuthorizationContext(user_id=uuid4(), organization_id=org_id, membership_id=uuid4(), role=role, permissions=ROLE_PERMISSIONS[role], farmer_id=farmer_id)
        yield client, farmers, org_a, org_b, set_role
    engine.dispose()


def test_staff_directory_is_scoped_and_reports_years(service):
    client, farmers, *_ = service
    response = client.get('/farmers/history-directory')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['total'] == 2
    assert {item['name'] for item in payload['items']} == {'Anne Green', 'Brian Blue'}
    anne = next(item for item in payload['items'] if item['name'] == 'Anne Green')
    assert (anne['history_record_count'], anne['first_year'], anne['last_year']) == (2, 2023, 2025)
    brian = next(item for item in payload['items'] if item['name'] == 'Brian Blue')
    assert (brian['history_record_count'], brian['first_year'], brian['last_year']) == (0, None, None)


def test_search_and_pagination(service):
    client, farmers, *_ = service
    result = client.get('/farmers/history-directory?q=Portland').json()
    assert result['total'] == 1 and result['items'][0]['name'] == 'Anne Green'
    assert client.get('/farmers/history-directory?q=%25').json()['total'] == 0
    first = client.get('/farmers/history-directory?limit=1&offset=0').json()
    second = client.get('/farmers/history-directory?limit=1&offset=1').json()
    assert first['total'] == second['total'] == 2
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert client.get('/farmers/history-directory?limit=999').status_code == 422


def test_role_permissions_and_farmer_self_access(service):
    client, farmers, org_a, org_b, set_role = service
    set_role(RoleCode.FARMER, farmer_id=farmers[0].id)
    assert client.get('/farmers/history-directory').status_code == 403
    assert client.get(f'/farmers/{farmers[0].id}/profile').status_code == 200
    assert client.get(f'/farmers/{farmers[1].id}/profile').status_code == 404
    assert client.get(f'/farmers/{farmers[2].id}/production-history').status_code == 404
    set_role(RoleCode.BUYER)
    assert client.get('/farmers/history-directory').status_code == 403
    assert client.get(f'/farmers/{farmers[0].id}/profile').status_code == 403


def test_staff_cannot_read_other_organization_or_history(service):
    client, farmers, org_a, org_b, set_role = service
    assert client.get(f'/farmers/{farmers[2].id}/profile').status_code == 404
    assert client.get(f'/farmers/{farmers[2].id}/production-history').status_code == 404
    set_role(RoleCode.SUPPLY_COORDINATOR, org_id=org_b.id)
    listing = client.get('/farmers/history-directory').json()
    assert listing['total'] == 1 and listing['items'][0]['name'] == 'Cross Org'


def test_historical_records_filtered_and_never_mutate_lots(service):
    client, farmers, *_ = service
    rid = farmers[0].id
    profile = client.get(f'/farmers/{rid}/profile').json()
    assert profile['farms'][0]['name'] == 'Anne Farms'
    years = client.get(f'/farmers/{rid}/production-history?year=2025&crop=GINGER')
    assert years.status_code == 200, years.text
    data = years.json()
    assert len(data) == 1 and data[0]['production_kg'] == '200.000'
    assert data[0]['is_simulated'] is True
    assert client.get(f'/farmers/{rid}/production-history?year=2022').json() == []
