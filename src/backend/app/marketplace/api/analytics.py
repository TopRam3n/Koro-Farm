"""Read-only marketplace analytics, scoped by authenticated organization and buyer."""
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.main_dependencies import get_session
from app.marketplace.api.requests import FarmerOffer, OfferStatus

router = APIRouter(prefix='/marketplace/analytics', tags=['marketplace analytics'])
STAFF = {RoleCode.PLATFORM_ADMIN, RoleCode.ORGANIZATION_ADMIN, RoleCode.PROCUREMENT_MANAGER,
         RoleCode.SUPPLY_COORDINATOR, RoleCode.WAREHOUSE_OPERATOR, RoleCode.AUDITOR}

@router.get('/summary')
def analytics_summary(session: Session = Depends(get_session),
                      ctx: AuthorizationContext = Depends(get_authorization_context)):
    if ctx.role != RoleCode.BUYER and ctx.role not in STAFF:
        raise HTTPException(403, 'buyer or authorized staff role required')
    if ctx.role == RoleCode.BUYER and ctx.buyer_id is None:
        raise HTTPException(403, 'linked buyer account required')
    statement = (select(Requirement, Buyer).join(Buyer, Buyer.id == Requirement.buyer_id)
                 .where(Buyer.organization_id == ctx.organization_id))
    if ctx.role == RoleCode.BUYER:
        statement = statement.where(Buyer.id == ctx.buyer_id)
    rows = session.execute(statement.order_by(Requirement.created_at.desc())).all()
    req_ids = [req.id for req, _ in rows]
    accepted = defaultdict(lambda: Decimal('0'))
    farmer_ids = set()
    if req_ids:
        offers = session.scalars(select(FarmerOffer).where(
            FarmerOffer.organization_id == ctx.organization_id,
            FarmerOffer.requirement_id.in_(req_ids),
            FarmerOffer.status == OfferStatus.ACCEPTED)).all()
        for offer in offers:
            accepted[offer.requirement_id] += offer.quantity_kg
            farmer_ids.add(offer.farmer_id)
    items = []
    totals = defaultdict(lambda: Decimal('0'))
    for req, buyer in rows:
        if req.lifecycle_status == RequirementLifecycleStatus.CANCELLED:
            continue
        requested = req.required_quantity_kg
        covered = accepted[req.id]
        outstanding = max(Decimal('0'), requested - covered)
        totals['requested'] += requested
        totals['accepted'] += covered
        totals['outstanding'] += outstanding
        items.append({'id': str(req.id), 'buyer_name': buyer.name, 'crop': req.crop.value,
                      'grade': req.grade.value, 'status': req.lifecycle_status.value,
                      'requested_kg': str(requested), 'accepted_kg': str(covered),
                      'outstanding_kg': str(outstanding),
                      'delivery_start': req.delivery_window_start.isoformat(),
                      'delivery_end': req.delivery_window_end.isoformat()})
    return {'scope': 'buyer' if ctx.role == RoleCode.BUYER else 'organization',
            'totals': {'requirements': len(items), 'participating_farmers': len(farmer_ids),
                       'requested_kg': str(totals['requested']),
                       'accepted_kg': str(totals['accepted']),
                       'outstanding_kg': str(totals['outstanding'])},
            'items': items,
            'note': 'Accepted offers are commitments, not proof of physical receipt, grading or delivery. Cancelled requirements are excluded.'}
