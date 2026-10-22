"""Read-only scoped supply, offer-lineage and verified-rule views for KoroFarm marketplace."""
from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.main_dependencies import get_session
from app.identity.application.authorization import AuthorizationContext, get_authorization_context
from app.identity.domain.permissions import RoleCode
from app.demand.domain.models import Buyer, Requirement, RequirementLifecycleStatus
from app.supply.domain.models import Farmer, ProductionLot
from app.compliance.domain.models import ComplianceRule
from app.marketplace.api.requests import FarmerOffer, OfferStatus

router = APIRouter(prefix='/marketplace/operations', tags=['marketplace visibility'])

def _scope(ctx: AuthorizationContext):
    if ctx.role == RoleCode.BUYER and ctx.buyer_id:
        return 'buyer'
    if ctx.role == RoleCode.FARMER and ctx.farmer_id:
        return 'farmer'
    raise HTTPException(403, 'linked buyer or farmer account required')

def _lot_view(lot, farmer):
    return dict(id=str(lot.id), farmer_id=str(farmer.id), farmer_name=farmer.name, parish=lot.parish,
        crop=lot.crop.value, grade=lot.quality_grade_estimate.value,
        harvest_start=lot.harvest_start.isoformat(), harvest_end=lot.harvest_end.isoformat(),
        available_kg=str(lot.available_quantity_kg), reserved_kg=str(lot.reserved_quantity_kg),
        unreserved_kg=str(max(Decimal('0'), lot.available_quantity_kg-lot.reserved_quantity_kg)),
        status=lot.status.value, confidence=lot.availability_confidence.value,
        last_verified_at=lot.last_verified_at.isoformat() if lot.last_verified_at else None)

@router.get('/supply')
def supply(session: Session=Depends(get_session), ctx: AuthorizationContext=Depends(get_authorization_context)):
    mode=_scope(ctx)
    q=(select(ProductionLot,Farmer).join(Farmer, Farmer.id==ProductionLot.farmer_id)
       .where(Farmer.organization_id==ctx.organization_id, Farmer.active.is_(True)))
    if mode=='farmer':
        q=q.where(Farmer.id==ctx.farmer_id)
    rows=session.execute(q.order_by(ProductionLot.harvest_start.desc(),ProductionLot.id).limit(200)).all()
    items=[_lot_view(lot,farmer) for lot,farmer in rows]
    return {'scope':mode,'items':items,'totals':{
        'lots':len(items),
        'available_kg':str(sum((Decimal(x['available_kg']) for x in items),Decimal('0'))),
        'reserved_kg':str(sum((Decimal(x['reserved_kg']) for x in items),Decimal('0'))),
        'unreserved_kg':str(sum((Decimal(x['unreserved_kg']) for x in items),Decimal('0'))),
    },'note':'Lot availability is reported stock; not historic production or delivered quantity.'}

@router.get('/traceability')
def traceability(session: Session=Depends(get_session), ctx: AuthorizationContext=Depends(get_authorization_context)):
    mode=_scope(ctx)
    q=(select(FarmerOffer,Requirement,Buyer,ProductionLot,Farmer)
        .join(Requirement,Requirement.id==FarmerOffer.requirement_id)
        .join(Buyer,Buyer.id==Requirement.buyer_id)
        .join(ProductionLot,ProductionLot.id==FarmerOffer.production_lot_id)
        .join(Farmer,Farmer.id==FarmerOffer.farmer_id)
        .where(FarmerOffer.organization_id==ctx.organization_id,Buyer.organization_id==ctx.organization_id,
               Farmer.organization_id==ctx.organization_id,ProductionLot.farmer_id==Farmer.id))
    q=q.where(Requirement.buyer_id==ctx.buyer_id) if mode=='buyer' else q.where(FarmerOffer.farmer_id==ctx.farmer_id)
    rows=session.execute(q.order_by(FarmerOffer.created_at.desc(),FarmerOffer.id).limit(200)).all()
    items=[]
    for offer,req,buyer,lot,farmer in rows:
        items.append({'id':str(offer.id),'status':offer.status.value,'quantity_kg':str(offer.quantity_kg),
          'created_at':offer.created_at.isoformat() if offer.created_at else None,
          'buyer_name':buyer.name,'farmer_name':farmer.name,'parish':lot.parish,
          'crop':req.crop.value,'grade':req.grade.value,'requirement_id':str(req.id),
          'production_lot_id':str(lot.id),'harvest_start':lot.harvest_start.isoformat(),
          'harvest_end':lot.harvest_end.isoformat(),
          'delivery_window_start':req.delivery_window_start.isoformat(),
          'delivery_window_end':req.delivery_window_end.isoformat(),
          'fulfilment_status':'NOT_LINKED'})
    return {'items':items,'scope':mode,'note':'Offer-to-lot attribution only; no receipt, inspection, shipment or delivery is inferred.'}

@router.get('/compliance')
def compliance(session: Session=Depends(get_session), ctx: AuthorizationContext=Depends(get_authorization_context)):
    mode=_scope(ctx)
    q=(select(Requirement,Buyer).join(Buyer, Buyer.id==Requirement.buyer_id)
       .where(Buyer.organization_id==ctx.organization_id,Requirement.lifecycle_status!=RequirementLifecycleStatus.CANCELLED))
    if mode=='buyer':
        q=q.where(Requirement.buyer_id==ctx.buyer_id)
    else:
        q=q.join(FarmerOffer,FarmerOffer.requirement_id==Requirement.id).where(
          FarmerOffer.farmer_id==ctx.farmer_id,FarmerOffer.organization_id==ctx.organization_id,
          FarmerOffer.status==OfferStatus.ACCEPTED).distinct()
    requests=session.execute(q.order_by(Requirement.created_at.desc()).limit(100)).all()
    today=date.today()
    items=[]
    for requirement,buyer in requests:
        # Only verified domestic rules. Cross-border corridors require dedicated verification.
        rules=session.scalars(select(ComplianceRule).where(
            ComplianceRule.organization_id==ctx.organization_id,
            ComplianceRule.origin=='Jamaica',ComplianceRule.destination=='Jamaica',
            ComplianceRule.crop==requirement.crop,ComplianceRule.product_form=='FRESH',
            ComplianceRule.effective_from<=today,
            or_(ComplianceRule.effective_until.is_(None),ComplianceRule.effective_until>=today),
            ComplianceRule.last_verified_at<=datetime.now(timezone.utc),
            ComplianceRule.source_citation!='', ComplianceRule.source_version!='',
            ComplianceRule.verified_by!='', ComplianceRule.issuing_body!='',
        ).order_by(ComplianceRule.rule_name)).all() if requirement.trade_corridor_id is None else []
        items.append({'requirement_id':str(requirement.id),'buyer_name':buyer.name,
          'crop':requirement.crop.value,'grade':requirement.grade.value,
          'status':'VERIFIED_RULES_ON_FILE' if rules else 'NO_VERIFIED_RULE_ON_FILE',
          'corridor_supported':requirement.trade_corridor_id is None,
          'rules':[{'id':str(rule.id),'name':rule.rule_name,'issuing_body':rule.issuing_body,
                    'description':rule.description,'source_citation':rule.source_citation,
                    'source_version':rule.source_version,'required_before':rule.required_before,
                    'verified_at':rule.last_verified_at.isoformat()} for rule in rules]})
    return {'items':items,'scope':mode,'note':'Rule discovery is not compliance certification. Evidence/fulfilment checks are not implemented in this view.'}
