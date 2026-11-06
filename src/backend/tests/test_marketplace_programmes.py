"""Phase 4 programmes: accepted-offer accounting and tenant/role boundaries."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.auth import get_current_user
from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.identity.application.authorization import get_authorization_context
from app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from app.identity.domain.permissions import RoleCode
from app.main import app
from app.marketplace.api.requests import FarmerOffer, OfferStatus
from app.supply.domain.models import Farmer


ORG = UUID('00000000-0000-0000-0000-000000002501')
OTHER_ORG = UUID('00000000-0000-0000-0000-000000002502')


def actor(session, org, role, *, buyer_id=None, farmer_id=None):
    if session.get(Organization, org) is None:
        session.add(Organization(id=org, name='Test Org', slug='p-' + uuid4().hex[:10]))
        session.flush()
    user = UserAccount(id=uuid4(), email=f'{uuid4().hex}@example.test', display_name='Test user')
    session.add(user); session.flush()
    session.add(OrganizationMembership(
        organization_id=org, user_id=user.id,
        role_code=role, status=MembershipStatus.ACTIVE,
        buyer_id=buyer_id, farmer_id=farmer_id,
    )); session.commit()
    return user


def login(user, org):
    app.dependency_overrides.pop(get_authorization_context, None)
    app.dependency_overrides[get_current_user] = lambda: {'id': str(user.id), 'email': user.email}
    return {'X-Organization-ID': str(org)}


def buyers(session):
    a = Buyer(organization_id=ORG, name='Bath Fountain Hotel', buyer_type='HOTEL', destination='Kingston')
    b = Buyer(organization_id=ORG, name='Other Buyer', buyer_type='HOTEL', destination='Montego Bay')
    c = Buyer(organization_id=OTHER_ORG, name='Foreign Organization', buyer_type='HOTEL', destination='Kingston')
    session.add_all([a,b,c]); session.commit()
    return a,b,c


def programme_payload(*, buyer_id=None, name='Ginger Supply 2027'):
    return {
        **({'buyer_id': str(buyer_id)} if buyer_id else {}),
        'name': name, 'commodity_scope': 'GINGER',
        'start_date': str(date.today() + timedelta(days=2)),
        'end_date': str(date.today() + timedelta(days=80)),
    }


def request_payload():
    return {
        'crop': 'GINGER', 'grade': 'A', 'required_quantity_kg': '500',
        'delivery_window_start': str(date.today() + timedelta(days=21)),
        'delivery_window_end': str(date.today() + timedelta(days=26)),
    }


def seed_requirement(session, buyer, *, status=RequirementLifecycleStatus.ACTIVE):
    req = Requirement(
        buyer_id=buyer.id, crop='GINGER', grade='A',
        required_quantity_kg=Decimal('500'),
        delivery_window_start=date.today() + timedelta(days=21),
        delivery_window_end=date.today() + timedelta(days=26),
        lifecycle_status=status,
    )
    session.add(req); session.commit()
    return req



def test_programme_tracks_accepted_marketplace_offers(client, session):
    a,b,c = buyers(session)
    buyer_user = actor(session, ORG, RoleCode.BUYER, buyer_id=a.id)
    admin = actor(session, ORG, RoleCode.ORGANIZATION_ADMIN)
    farmer = Farmer(organization_id=ORG, name='Farmer One', parish='St. Mary')
    session.add(farmer);session.commit()
    farmer_user = actor(session, ORG, RoleCode.FARMER, farmer_id=farmer.id)
    req = seed_requirement(session, a)
    req_id = str(req.id)
    h = login(buyer_user, ORG)
    created = client.post('/marketplace/programmes', headers=h, json=programme_payload())
    assert created.status_code == 201, created.text
    prog_id = created.json()['id']
    assert created.json()['buyer_id'] == str(a.id)
    assert created.json()['requirement_count'] == 0
    linked = client.post(f'/marketplace/programmes/{prog_id}/requirements/{req_id}', headers=h)
    assert linked.status_code == 200, linked.text
    assert linked.json()['already_linked'] is False
    again = client.post(f'/marketplace/programmes/{prog_id}/requirements/{req_id}', headers=h)
    assert again.status_code == 200 and again.json()['already_linked'] is True
    unassigned = client.get('/marketplace/programmes/available-requirements', headers=h)
    assert all(item['id'] != req_id for item in unassigned.json()['items'])

    # Simulate the durable record written by /marketplace/requests/{id}/offers.
    # Status is PENDING until buyer acceptance; no committed quantity yet.
    offer = FarmerOffer(organization_id=ORG, requirement_id=req.id, farmer_id=farmer.id,
                        production_lot_id=uuid4(), quantity_kg=Decimal('300'), status=OfferStatus.PENDING)
    session.add(offer); session.commit()

    h = login(buyer_user, ORG)
    pending = client.get('/marketplace/programmes', headers=h).json()['items'][0]
    assert pending['active_required_kg'] == '500.000'
    assert pending['active_accepted_offer_kg'] == '0'
    assert Decimal(pending['active_pending_offer_kg']) == Decimal('300')
    assert pending['active_offer_coverage_pct'] == 0

    # The existing marketplace acceptance handler persists ACCEPTED. Check
    # that programme metrics react to the persisted status transition.
    offer.status = OfferStatus.ACCEPTED
    session.commit()
    after = client.get(f'/marketplace/programmes/{prog_id}', headers=h)
    assert after.status_code == 200, after.text
    row = after.json()
    assert Decimal(row['active_accepted_offer_kg']) == Decimal('300')
    assert Decimal(row['active_remaining_offer_kg']) == Decimal('200')
    assert row['active_offer_coverage_pct'] == 60.0
    assert row['active_requirement_count'] == 1
    assert row['requirement_count'] == 1
    assert row['recent_requirements'][0]['id'] == req_id

    h_admin = login(admin, ORG)
    assert client.get('/marketplace/programmes', headers=h_admin).json()['items'][0]['id'] == prog_id


def test_buyer_cannot_read_or_relink_other_buyers_or_cross_tenant(client, session):
    a,b,c = buyers(session)
    admin = actor(session, ORG, RoleCode.PLATFORM_ADMIN)
    user_a = actor(session, ORG, RoleCode.BUYER, buyer_id=a.id)
    user_b = actor(session, ORG, RoleCode.BUYER, buyer_id=b.id)
    foreign = actor(session, OTHER_ORG, RoleCode.BUYER, buyer_id=c.id)

    admin_h = login(admin, ORG)
    pa = client.post('/marketplace/programmes', headers=admin_h, json=programme_payload(buyer_id=a.id, name='Buyer A Programme')).json()['id']
    pb = client.post('/marketplace/programmes', headers=admin_h, json=programme_payload(buyer_id=b.id, name='Buyer B Programme')).json()['id']
    assert client.post('/marketplace/programmes', headers=admin_h, json=programme_payload(buyer_id=c.id)).status_code == 404

    foreign_h = login(foreign, OTHER_ORG)
    pc = client.post('/marketplace/programmes', headers=foreign_h, json=programme_payload()).json()['id']
    assert client.get(f'/marketplace/programmes/{pa}', headers=foreign_h).status_code == 404

    ah = login(user_a, ORG)
    assert [p['id'] for p in client.get('/marketplace/programmes', headers=ah).json()['items']] == [pa]
    assert client.get(f'/marketplace/programmes/{pb}', headers=ah).status_code == 404
    assert client.get(f'/marketplace/programmes/{pc}', headers=ah).status_code == 404
    assert client.post('/marketplace/programmes', headers=ah, json=programme_payload(buyer_id=b.id)).status_code == 403
    assert client.get('/marketplace/programmes/available-requirements', headers=ah, params={'buyer_id': str(b.id)}).status_code == 403

    bh = login(user_b, ORG)
    req = seed_requirement(session, b)
    ah = login(user_a, ORG)
    assert client.post(f'/marketplace/programmes/{pa}/requirements/{req.id}', headers=ah).status_code == 404


def test_relink_conflict_status_changes_and_staff_write_restrictions(client, session):
    a,_,_ = buyers(session)
    buyer = actor(session, ORG, RoleCode.BUYER, buyer_id=a.id)
    auditor = actor(session, ORG, RoleCode.AUDITOR)
    farmer = actor(session, ORG, RoleCode.FARMER)
    buyer_h = login(buyer, ORG)
    p1 = client.post('/marketplace/programmes', headers=buyer_h, json=programme_payload(name='Primary programme')).json()['id']
    p2 = client.post('/marketplace/programmes', headers=buyer_h, json=programme_payload(name='Alternate programme')).json()['id']
    req = str(seed_requirement(session, a).id)
    assert client.post(f'/marketplace/programmes/{p1}/requirements/{req}', headers=buyer_h).status_code == 200
    assert client.post(f'/marketplace/programmes/{p2}/requirements/{req}', headers=buyer_h).status_code == 409
    pause = client.patch(f'/marketplace/programmes/{p1}', headers=buyer_h, json={'status': 'PAUSED'})
    assert pause.status_code == 200 and pause.json()['status'] == 'PAUSED'
    assert client.patch(f'/marketplace/programmes/{p1}', headers=buyer_h, json={'status': 'INVALID'}).status_code == 422
    assert client.post(f'/marketplace/programmes/{p1}/requirements/{req}', headers=buyer_h).status_code == 409

    auditor_h = login(auditor, ORG)
    assert client.get(f'/marketplace/programmes/{p1}', headers=auditor_h).status_code == 200
    assert client.post('/marketplace/programmes', headers=auditor_h, json=programme_payload(buyer_id=a.id)).status_code == 403
    assert client.patch(f'/marketplace/programmes/{p1}', headers=auditor_h, json={'status': 'ACTIVE'}).status_code == 403
    assert client.post(f'/marketplace/programmes/{p2}/requirements/{req}', headers=auditor_h).status_code == 403

    farmer_h = login(farmer, ORG)
    assert client.get('/marketplace/programmes', headers=farmer_h).status_code == 403
    assert client.get('/marketplace/programmes/buyers', headers=farmer_h).status_code == 403
    assert client.get('/marketplace/programmes/available-requirements', headers=farmer_h).status_code == 403


def test_programme_pagination_and_date_validation(client, session):
    a,_,_ = buyers(session)
    buyer = actor(session, ORG, RoleCode.BUYER, buyer_id=a.id)
    h = login(buyer, ORG)
    payload = programme_payload()
    payload['end_date'] = str(date.today())
    assert client.post('/marketplace/programmes', headers=h, json=payload).status_code == 422
    for n in range(3):
        assert client.post('/marketplace/programmes', headers=h, json=programme_payload(name=f'Programme {n}')).status_code == 201
    page1 = client.get('/marketplace/programmes?limit=2&offset=0', headers=h).json()
    page2 = client.get('/marketplace/programmes?limit=2&offset=2', headers=h).json()
    assert page1['pagination']['total'] == 3
    assert page1['pagination']['has_more'] is True
    assert page2['pagination']['has_more'] is False
    assert len(page2['items']) == 1
    assert client.get('/marketplace/programmes?limit=201', headers=h).status_code == 422


def test_legacy_staff_programmes_endpoints_are_tenant_scoped(client, session):
    a, _, c = buyers(session)
    org_admin = actor(session, ORG, RoleCode.ORGANIZATION_ADMIN)
    foreign_admin = actor(session, OTHER_ORG, RoleCode.ORGANIZATION_ADMIN)
    auditor = actor(session, ORG, RoleCode.AUDITOR)

    local_headers = login(org_admin, ORG)
    created = client.post('/programmes', headers=local_headers, json=programme_payload(buyer_id=a.id))
    assert created.status_code == 201, created.text
    local_id = created.json()['id']
    assert client.get(f'/programmes/{local_id}', headers=local_headers).status_code == 200
    # A staff member cannot create a programme for a buyer from another org.
    assert client.post('/programmes', headers=local_headers, json=programme_payload(buyer_id=c.id)).status_code == 404

    foreign_headers = login(foreign_admin, OTHER_ORG)
    assert client.get('/programmes', headers=foreign_headers).json() == []
    assert client.get(f'/programmes/{local_id}', headers=foreign_headers).status_code == 404

    audit_headers = login(auditor, ORG)
    assert client.get('/programmes', headers=audit_headers).status_code == 200
    assert client.post('/programmes', headers=audit_headers, json=programme_payload(buyer_id=a.id)).status_code == 403
