"""Integration tests for the Phase 0 / Demand read-only marketplace ledger.

Run with: cd src/backend && python -m pytest tests/test_demand_ledger.py -q
Uses the repository's existing SQLite-backed client/session fixtures.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.domain.common import AvailabilityConfidence, Crop, Grade
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.models import Organization
from app.identity.domain.permissions import ROLE_PERMISSIONS, RoleCode
from app.main import app
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus

ORG_A = UUID('00000000-0000-0000-0000-000000000900')
ORG_B = UUID('00000000-0000-0000-0000-000000000901')


def as_role(role, org, buyer_id=None, farmer_id=None):
    app.dependency_overrides[get_authorization_context] = lambda: AuthorizationContext(
        user_id=uuid4(), organization_id=org, membership_id=uuid4(), role=role,
        permissions=ROLE_PERMISSIONS[role], farmer_id=farmer_id, buyer_id=buyer_id,
    )


def seed_records(session):
    org_a = Organization(id=ORG_A, name='Demo A', slug='demo-a')
    org_b = Organization(id=ORG_B, name='Demo B', slug='demo-b')
    buyer_a = Buyer(organization_id=ORG_A, name='Bath Fountain Hotel', buyer_type='HOTEL', destination='Bath')
    buyer_a2 = Buyer(organization_id=ORG_A, name='Another A Buyer', buyer_type='HOTEL', destination='Kingston')
    buyer_b = Buyer(organization_id=ORG_B, name='Other Tenant Buyer', buyer_type='HOTEL', destination='Montego Bay')
    farmer = Farmer(organization_id=ORG_A, name='Test Ginger Farmer', parish='St. Thomas')
    session.add_all([org_a, org_b, buyer_a, buyer_a2, buyer_b, farmer])
    session.flush()
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=7)
    def requirement(buyer):
        return Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
                           required_quantity_kg=Decimal('500.000'),
                           delivery_window_start=start, delivery_window_end=end,
                           lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    r1, r2, r3 = requirement(buyer_a), requirement(buyer_a2), requirement(buyer_b)
    session.add_all([r1, r2, r3])
    lot = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=start,
                        harvest_end=end, expected_quantity_kg=Decimal('800'),
                        available_quantity_kg=Decimal('800'), reserved_quantity_kg=Decimal('0'),
                        quality_grade_estimate=Grade.A, availability_confidence=AvailabilityConfidence.HIGH,
                        parish='St. Thomas', status=ProductionLotStatus.AVAILABLE,
                        last_verified_at=datetime.now(timezone.utc))
    session.add(lot)
    session.flush()
    pending = FarmerOffer(organization_id=ORG_A, requirement_id=r1.id,
                          farmer_id=farmer.id, production_lot_id=lot.id,
                          quantity_kg=Decimal('300'), status=OfferStatus.PENDING)
    session.add(pending)
    session.commit()
    return buyer_a, buyer_a2, buyer_b, r1, r2, r3, lot, pending


def test_demand_accepted_offer_is_counted_only_after_buyer_acceptance(client, session):
    buyer, _, _, req, _, _, lot, offer = seed_records(session)
    as_role(RoleCode.BUYER, ORG_A, buyer_id=buyer.id)
    before = client.get('/marketplace/demand')
    assert before.status_code == 200, before.text
    assert before.json()['pagination']['total'] == 1
    row = before.json()['items'][0]
    assert row['id'] == str(req.id)
    assert Decimal(row['pending_offer_quantity_kg']) == 300
    assert Decimal(row['accepted_offer_quantity_kg']) == 0
    assert Decimal(row['remaining_offer_quantity_kg']) == 500

    accepted = client.post(f'/marketplace/requests/offers/{offer.id}/accept')
    assert accepted.status_code == 200, accepted.text
    session.refresh(lot)
    assert lot.reserved_quantity_kg == Decimal('300')
    after = client.get('/marketplace/demand')
    assert after.status_code == 200, after.text
    row = after.json()['items'][0]
    assert Decimal(row['accepted_offer_quantity_kg']) == 300
    assert Decimal(row['remaining_offer_quantity_kg']) == 200
    assert Decimal(row['pending_offer_quantity_kg']) == 0
    assert row['offer_coverage_pct'] == 60.0
    assert row['coverage_status'] == 'PARTIALLY_COVERED'
    assert Decimal(after.json()['summary']['page_accepted_offer_kg']) == 300


def test_buyer_cannot_see_another_buyers_requirements(client, session):
    buyer, second, _, r1, r2, _, _, _ = seed_records(session)
    as_role(RoleCode.BUYER, ORG_A, buyer_id=buyer.id)
    first = client.get('/marketplace/demand')
    assert [x['id'] for x in first.json()['items']] == [str(r1.id)]
    as_role(RoleCode.BUYER, ORG_A, buyer_id=second.id)
    alternate = client.get('/marketplace/demand')
    assert [x['id'] for x in alternate.json()['items']] == [str(r2.id)]
    as_role(RoleCode.BUYER, ORG_A)
    assert client.get('/marketplace/demand').status_code == 403


def test_staff_sees_only_active_organization_and_farmer_is_forbidden(client, session):
    buyer, _, _, r1, r2, r3, _, _ = seed_records(session)
    as_role(RoleCode.PROCUREMENT_MANAGER, ORG_A)
    result = client.get('/marketplace/demand')
    assert result.status_code == 200, result.text
    assert {r['id'] for r in result.json()['items']} == {str(r1.id), str(r2.id)}
    assert str(r3.id) not in str(result.json())
    as_role(RoleCode.FARMER, ORG_A)
    assert client.get('/marketplace/demand').status_code == 403
    as_role(RoleCode.PROCUREMENT_MANAGER, ORG_B)
    other = client.get('/marketplace/demand')
    assert {r['id'] for r in other.json()['items']} == {str(r3.id)}


def test_demand_pagination_and_invalid_filters(client, session):
    buyer, _, _, _, _, _, _, _ = seed_records(session)
    as_role(RoleCode.BUYER, ORG_A, buyer_id=buyer.id)
    page = client.get('/marketplace/demand?limit=1&offset=1')
    assert page.status_code == 200
    assert page.json()['items'] == []
    assert page.json()['pagination']['total'] == 1
    assert client.get('/marketplace/demand?limit=0').status_code == 422
    assert client.get('/marketplace/demand?crop=UNKNOWN').status_code == 422
