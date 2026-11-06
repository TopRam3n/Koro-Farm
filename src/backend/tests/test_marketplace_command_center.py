"""Command Center integration contracts using the existing SQLite TestClient fixture.

Run with: python3 -m pytest tests/test_marketplace_command_center.py -q
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


def as_role(role, organization_id, buyer_id=None, farmer_id=None):
    app.dependency_overrides[get_authorization_context] = lambda: AuthorizationContext(
        user_id=uuid4(), organization_id=organization_id, membership_id=uuid4(),
        role=role, permissions=ROLE_PERMISSIONS[role],
        buyer_id=buyer_id, farmer_id=farmer_id,
    )


def seeded(session):
    org_a = Organization(id=ORG_A, name='Test A', slug='command-a')
    org_b = Organization(id=ORG_B, name='Test B', slug='command-b')
    buyer_a = Buyer(organization_id=ORG_A, name='Bath Fountain Hotel', buyer_type='HOTEL', destination='Bath')
    buyer_a2 = Buyer(organization_id=ORG_A, name='Different Hotel', buyer_type='HOTEL', destination='Kingston')
    buyer_b = Buyer(organization_id=ORG_B, name='Other Organization', buyer_type='HOTEL', destination='Montego Bay')
    farmer = Farmer(organization_id=ORG_A, name='St Thomas Grower', parish='St. Thomas')
    session.add_all([org_a, org_b, buyer_a, buyer_a2, buyer_b, farmer])
    session.flush()
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=5)
    request = Requirement(buyer_id=buyer_a.id, crop=Crop.GINGER, grade=Grade.A,
                          required_quantity_kg=Decimal('500.000'), delivery_window_start=start,
                          delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    other = Requirement(buyer_id=buyer_a2.id, crop=Crop.GINGER, grade=Grade.B,
                        required_quantity_kg=Decimal('100.000'), delivery_window_start=start,
                        delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    cross_org = Requirement(buyer_id=buyer_b.id, crop=Crop.GINGER, grade=Grade.A,
                            required_quantity_kg=Decimal('900.000'), delivery_window_start=start,
                            delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.ACTIVE)
    draft = Requirement(buyer_id=buyer_a.id, crop=Crop.GINGER, grade=Grade.A,
                        required_quantity_kg=Decimal('800.000'), delivery_window_start=start,
                        delivery_window_end=end, lifecycle_status=RequirementLifecycleStatus.DRAFT)
    session.add_all([request, other, cross_org, draft])
    lot = ProductionLot(farmer_id=farmer.id, crop=Crop.GINGER, harvest_start=start, harvest_end=end,
                        expected_quantity_kg=Decimal('700'), available_quantity_kg=Decimal('700'),
                        reserved_quantity_kg=Decimal('0'), quality_grade_estimate=Grade.A,
                        availability_confidence=AvailabilityConfidence.HIGH, parish=farmer.parish,
                        status=ProductionLotStatus.AVAILABLE,
                        last_verified_at=datetime.now(timezone.utc))
    session.add(lot)
    session.flush()
    offer = FarmerOffer(organization_id=ORG_A, requirement_id=request.id, farmer_id=farmer.id,
                        production_lot_id=lot.id, quantity_kg=Decimal('300'), status=OfferStatus.PENDING)
    session.add(offer)
    session.commit()
    return buyer_a, buyer_a2, buyer_b, request, other, cross_org, draft, offer


def test_buyer_portfolio_changes_only_after_offer_acceptance(client, session):
    buyer, _, _, req, _, _, _, offer = seeded(session)
    as_role(RoleCode.BUYER, ORG_A, buyer_id=buyer.id)
    url = '/marketplace/command-center/summary'
    before = client.get(url)
    assert before.status_code == 200, before.text
    result = before.json()
    assert result['scope'] == 'buyer'
    assert result['totals']['all_requests'] == 2
    assert result['totals']['active_requests'] == 1
    assert result['totals']['draft_requests'] == 1
    assert Decimal(result['totals']['requested_kg']) == 500
    assert Decimal(result['totals']['accepted_offer_kg']) == 0
    assert Decimal(result['totals']['pending_offer_kg']) == 300
    assert Decimal(result['totals']['remaining_offer_kg']) == 500
    assert result['totals']['coverage_pct'] == 0
    assert [r['id'] for r in result['attention']] == [str(req.id)]

    accepted = client.post(f'/marketplace/requests/offers/{offer.id}/accept')
    assert accepted.status_code == 200, accepted.text
    after = client.get(url)
    assert after.status_code == 200, after.text
    totals = after.json()['totals']
    assert Decimal(totals['accepted_offer_kg']) == 300
    assert Decimal(totals['pending_offer_kg']) == 0
    assert Decimal(totals['remaining_offer_kg']) == 200
    assert totals['coverage_pct'] == 60.0
    assert totals['partially_covered_active_requests'] == 1
    assert after.json()['attention'][0]['coverage_status'] == 'PARTIALLY_COVERED'
    assert after.json()['recent_offers'][0]['status'] == 'ACCEPTED'


def test_staff_all_organization_and_no_cross_tenant_leak(client, session):
    buyer, _, _, request, other, cross_org, _, _ = seeded(session)
    as_role(RoleCode.PROCUREMENT_MANAGER, ORG_A)
    response = client.get('/marketplace/command-center/summary')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['scope'] == 'organization_staff'
    assert data['totals']['active_requests'] == 2
    assert Decimal(data['totals']['requested_kg']) == 600
    assert {r['id'] for r in data['recent_requests']} == {str(request.id), str(other.id)}
    assert str(cross_org.id) not in str(data)
    as_role(RoleCode.PROCUREMENT_MANAGER, ORG_B)
    second = client.get('/marketplace/command-center/summary').json()
    assert second['totals']['active_requests'] == 1
    assert Decimal(second['totals']['requested_kg']) == 900
    assert second['recent_offers'] == []


def test_farmer_and_unlinked_buyer_forbidden(client, session):
    seeded(session)
    as_role(RoleCode.FARMER, ORG_A)
    assert client.get('/marketplace/command-center/summary').status_code == 403
    as_role(RoleCode.BUYER, ORG_A)
    assert client.get('/marketplace/command-center/summary').status_code == 403
    as_role(RoleCode.BUYER, ORG_A, buyer_id=uuid4())
    assert client.get('/marketplace/command-center/summary').status_code == 403


def test_empty_scope_has_no_fake_coverage_or_activity(client, session):
    organization = Organization(id=ORG_A, name='Empty A', slug='empty-command')
    buyer = Buyer(organization_id=ORG_A, name='New Buyer', buyer_type='HOTEL', destination='Kingston')
    session.add_all([organization, buyer]); session.commit()
    as_role(RoleCode.BUYER, ORG_A, buyer_id=buyer.id)
    response = client.get('/marketplace/command-center/summary')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['totals']['active_requests'] == 0
    assert result['totals']['coverage_pct'] is None
    assert result['attention'] == []
    assert result['recent_offers'] == []
    assert result['by_crop'] == []


def test_portfolio_totals_are_not_limited_to_a_demand_page(client, session):
    buyer, _, _, _, _, _, _, _ = seeded(session)
    future = date.today() + timedelta(days=30)
    session.add_all([
        Requirement(buyer_id=buyer.id, crop=Crop.GINGER, grade=Grade.A,
                    required_quantity_kg=Decimal('2.000'),
                    delivery_window_start=future, delivery_window_end=future + timedelta(days=2),
                    lifecycle_status=RequirementLifecycleStatus.ACTIVE)
        for _ in range(105)
    ])
    session.commit()
    as_role(RoleCode.BUYER, ORG_A, buyer_id=buyer.id)
    response = client.get('/marketplace/command-center/summary')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['totals']['active_requests'] == 106
    assert Decimal(result['totals']['requested_kg']) == 710
    assert result['totals']['requests_needing_supply'] == 106
    assert len(result['attention']) == 10
    assert len(result['recent_requests']) == 8
