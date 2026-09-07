from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from src.backend.app.compliance.domain.models import ComplianceRule
from src.backend.app.demand.domain.models import Requirement
from src.backend.app.main_dependencies import get_session
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor

router = APIRouter(prefix="/requirements", tags=["compliance"])

@router.get("/{requirement_id}/compliance")
def applicable_rules(requirement_id: UUID, product_form: str = "FRESH", session: Session = Depends(get_session)) -> dict:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, "requirement not found")
    origin = destination = "Jamaica"
    corridor_name = None
    if requirement.trade_corridor_id:
        corridor = session.get(TradeCorridor, requirement.trade_corridor_id)
        if corridor is None or not corridor.active:
            return {"requirement_id": str(requirement_id), "status": "no_verified_rule_on_file", "rules": []}
        origin, destination, corridor_name = corridor.origin_country, corridor.destination_country, corridor.name
    today = date.today()
    rules = list(session.scalars(select(ComplianceRule).where(
        ComplianceRule.origin == origin, ComplianceRule.destination == destination,
        ComplianceRule.crop == requirement.crop, ComplianceRule.product_form == product_form,
        ComplianceRule.effective_from <= today,
        or_(ComplianceRule.effective_until.is_(None), ComplianceRule.effective_until >= today),
        ComplianceRule.last_verified_at <= datetime.now(timezone.utc),
        ComplianceRule.source_citation != "", ComplianceRule.source_version != "",
        ComplianceRule.verified_by != "", ComplianceRule.issuing_body != "",
    ).order_by(ComplianceRule.required_before, ComplianceRule.rule_name)))
    if not rules:
        return {"requirement_id": str(requirement_id), "corridor": corridor_name, "status": "no_verified_rule_on_file", "rules": []}
    return {"requirement_id": str(requirement_id), "corridor": corridor_name, "status": "verified_rules_found", "rules": [{
        "id": str(rule.id), "rule_name": rule.rule_name, "issuing_body": rule.issuing_body,
        "description": rule.description, "required_before": rule.required_before, "lead_time": rule.lead_time,
        "source_citation": rule.source_citation, "source_version": rule.source_version,
        "last_verified_at": rule.last_verified_at, "verified_by": rule.verified_by,
    } for rule in rules]}
