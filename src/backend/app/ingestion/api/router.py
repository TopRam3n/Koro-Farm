import hashlib
import json
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.ingestion.domain.models import (
    FreshnessStatus, IngestionRecord, IngestionStatus, OperationalObservation,
    SecureActionLink, SecureActionPurpose, SourceChannel, VerificationStatus,
)
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.models import Farmer, ProductionLot

router = APIRouter(prefix="/v1/ingestion", tags=["ingestion"])
public_router = APIRouter(prefix="/v1/secure-actions", tags=["secure farmer actions"])


class SecureLinkCreate(BaseModel):
    farmer_id: UUID
    purpose: SecureActionPurpose
    production_lot_id: UUID
    request_reference: str = Field(min_length=3, max_length=200)
    expires_in_hours: int = Field(default=48, ge=1, le=168)
    constraints: dict = Field(default_factory=dict)


class SecureActionResponse(BaseModel):
    available_quantity_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    harvest_start: date | None = None
    harvest_end: date | None = None
    evidence_reference: str | None = Field(default=None, max_length=500)


class CoordinatorObservation(BaseModel):
    farmer_id: UUID
    production_lot_id: UUID
    action: str
    available_quantity_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    harvest_start: date | None = None
    harvest_end: date | None = None
    source_channel: SourceChannel
    effective_at: datetime
    confirmation_status: str
    notes: str | None = Field(default=None, max_length=1000)
    evidence_reference: str | None = Field(default=None, max_length=500)


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _record(
    session: Session, *, organization_id: UUID, channel: SourceChannel, external_reference: str,
    actor_user_id: UUID | None, farmer_id: UUID, lot: ProductionLot, payload: dict,
    verification: VerificationStatus, effective_at: datetime, evidence: str | None, source_actor: str,
) -> IngestionRecord:
    correlation_id = uuid4()
    event = DomainEvent(
        event_type="production.observation_recorded", aggregate_type="production_lot", aggregate_id=lot.id,
        correlation_id=correlation_id, actor_type="farmer" if channel == SourceChannel.SECURE_LINK else "coordinator",
        payload={"production_lot_id": str(lot.id), "farmer_id": str(farmer_id), "channel": channel.value,
                 "fields": sorted(payload), "verification_status": verification.value},
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(event); session.flush()
    record = IngestionRecord(
        organization_id=organization_id, channel=channel, external_reference=external_reference,
        actor_user_id=actor_user_id, farmer_id=farmer_id, target_entity_type="production_lot",
        target_entity_id=lot.id, payload_schema="production-observation", payload_version="1.0",
        payload_digest=_digest(payload), validation_result={"valid": True, "errors": []},
        status=IngestionStatus.ACCEPTED, domain_command="production_lot.update_observation",
        resulting_event_id=event.id, correlation_id=correlation_id,
    )
    session.add(record); session.flush()
    stale_hours = int(os.getenv("SUPPLY_OBSERVATION_STALE_HOURS", "168"))
    expires_at = _aware(effective_at) + timedelta(hours=stale_hours)
    for field_name, value in payload.items():
        session.add(OperationalObservation(
            organization_id=organization_id, ingestion_record_id=record.id,
            target_entity_type="production_lot", target_entity_id=lot.id, field_name=field_name,
            value={"value": str(value)}, source_type="FARMER_REPORT",
            source_actor=source_actor, source_channel=channel, effective_at=effective_at,
            verified_at=datetime.now(timezone.utc) if verification == VerificationStatus.COORDINATOR_CONFIRMED else None,
            verification_status=verification,
            verification_method="farmer secure response" if channel == SourceChannel.SECURE_LINK else "coordinator-assisted entry",
            freshness_status=FreshnessStatus.CURRENT, freshness_expires_at=expires_at,
            supporting_evidence_reference=evidence,
        ))
    session.add(OutboxMessage(event_id=event.id, topic=event.event_type, payload=event.payload))
    return record


def _apply_observation(lot: ProductionLot, payload: dict) -> None:
    if "available_quantity_kg" in payload:
        quantity = Decimal(str(payload["available_quantity_kg"]))
        if quantity < lot.reserved_quantity_kg:
            raise ValueError("available quantity cannot be below already reserved quantity")
        lot.available_quantity_kg = quantity
    if "harvest_start" in payload or "harvest_end" in payload:
        start = payload.get("harvest_start", lot.harvest_start)
        end = payload.get("harvest_end", lot.harvest_end)
        if end < start:
            raise ValueError("harvest window end must be on or after start")
        lot.harvest_start, lot.harvest_end = start, end
    lot.last_verified_at = datetime.now(timezone.utc)
    lot.version += 1
    lot.validate()


@router.post("/secure-links", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def create_secure_link(payload: SecureLinkCreate,
                       context: AuthorizationContext = Depends(get_authorization_context),
                       session: Session = Depends(get_session)) -> dict:
    if payload.purpose not in {SecureActionPurpose.CONFIRM_QUANTITY, SecureActionPurpose.CHANGE_AVAILABLE_QUANTITY,
                               SecureActionPurpose.CONFIRM_HARVEST_DATE, SecureActionPurpose.DECLINE}:
        raise HTTPException(422, "secure action purpose is not implemented")
    farmer = session.scalar(select(Farmer).where(Farmer.id == payload.farmer_id,
                                                  Farmer.organization_id == context.organization_id))
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == payload.production_lot_id,
                                                      ProductionLot.farmer_id == payload.farmer_id))
    if farmer is None or lot is None:
        raise HTTPException(404, "farmer production lot not found")
    token = secrets.token_urlsafe(32)
    link = SecureActionLink(
        organization_id=context.organization_id, farmer_id=farmer.id, created_by=context.user_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), purpose=payload.purpose,
        target_entity_type="production_lot", target_entity_id=lot.id, constraints=payload.constraints,
        request_reference=payload.request_reference,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours),
    )
    session.add(link); session.commit()
    return {"secure_action_id": str(link.id), "token": token, "purpose": link.purpose.value,
            "expires_at": link.expires_at, "single_use": True}


def _find_link(token: str, session: Session, lock: bool = False) -> SecureActionLink:
    statement = select(SecureActionLink).where(
        SecureActionLink.token_hash == hashlib.sha256(token.encode()).hexdigest()
    )
    if lock:
        statement = statement.with_for_update()
    link = session.scalar(statement)
    if link is None or link.revoked_at is not None:
        raise HTTPException(404, "secure action not found")
    now = datetime.now(timezone.utc)
    expires_at = _aware(link.expires_at)
    if expires_at <= now:
        raise HTTPException(410, "secure action has expired")
    if link.used_at is not None:
        raise HTTPException(409, "secure action has already been used")
    return link


@public_router.get("/{token}")
def inspect_secure_action(token: str, session: Session = Depends(get_session)) -> dict:
    link = _find_link(token, session)
    farmer = session.get(Farmer, link.farmer_id)
    lot = session.get(ProductionLot, link.target_entity_id)
    return {"purpose": link.purpose.value, "request_reference": link.request_reference,
            "farmer_name": farmer.name, "crop": lot.crop.value, "expires_at": link.expires_at,
            "constraints": link.constraints}


@public_router.post("/{token}")
def execute_secure_action(token: str, payload: SecureActionResponse,
                          idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                          session: Session = Depends(get_session)) -> dict:
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    link = _find_link(token, session, lock=True)
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == link.target_entity_id).with_for_update())
    values: dict = {}
    if link.purpose in {SecureActionPurpose.CONFIRM_QUANTITY, SecureActionPurpose.CHANGE_AVAILABLE_QUANTITY}:
        if payload.available_quantity_kg is None:
            raise HTTPException(422, "available_quantity_kg is required")
        maximum = link.constraints.get("maximum_quantity_kg")
        if maximum is not None and payload.available_quantity_kg > Decimal(str(maximum)):
            raise HTTPException(422, "quantity exceeds the secure action scope")
        values["available_quantity_kg"] = payload.available_quantity_kg
    elif link.purpose == SecureActionPurpose.CONFIRM_HARVEST_DATE:
        if payload.harvest_start is None or payload.harvest_end is None:
            raise HTTPException(422, "harvest_start and harvest_end are required")
        values.update(harvest_start=payload.harvest_start, harvest_end=payload.harvest_end)
    elif link.purpose == SecureActionPurpose.DECLINE:
        values["declined"] = True
    try:
        if values.keys() != {"declined"}:
            _apply_observation(lot, values)
        record = _record(
            session, organization_id=link.organization_id, channel=SourceChannel.SECURE_LINK,
            external_reference=f"secure-link:{link.id}:{idempotency_key}", actor_user_id=None,
            farmer_id=link.farmer_id, lot=lot, payload=values,
            verification=VerificationStatus.SELF_REPORTED, effective_at=datetime.now(timezone.utc),
            evidence=payload.evidence_reference, source_actor=f"farmer:{link.farmer_id}",
        )
        link.used_at = datetime.now(timezone.utc)
        session.commit()
        return {"ingestion_record_id": str(record.id), "status": record.status.value,
                "verification_status": VerificationStatus.SELF_REPORTED.value,
                "freshness_status": FreshnessStatus.CURRENT.value}
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "duplicate ingestion reference") from exc


@router.post("/coordinator-observations", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def coordinator_observation(payload: CoordinatorObservation,
                            context: AuthorizationContext = Depends(get_authorization_context),
                            session: Session = Depends(get_session)) -> dict:
    if payload.source_channel not in {SourceChannel.PHONE, SourceChannel.WHATSAPP,
                                      SourceChannel.COORDINATOR_ENTRY}:
        raise HTTPException(422, "coordinator source must be phone, WhatsApp, or coordinator entry")
    farmer = session.scalar(select(Farmer).where(Farmer.id == payload.farmer_id,
                                                  Farmer.organization_id == context.organization_id))
    lot = session.scalar(select(ProductionLot).where(ProductionLot.id == payload.production_lot_id,
                                                      ProductionLot.farmer_id == payload.farmer_id))
    if farmer is None or lot is None:
        raise HTTPException(404, "farmer production lot not found")
    values = {}
    if payload.action == "UPDATE_AVAILABLE_QUANTITY" and payload.available_quantity_kg is not None:
        values["available_quantity_kg"] = payload.available_quantity_kg
    elif payload.action == "UPDATE_EXPECTED_HARVEST" and payload.harvest_start and payload.harvest_end:
        values.update(harvest_start=payload.harvest_start, harvest_end=payload.harvest_end)
    else:
        raise HTTPException(422, "action payload is incomplete or unsupported")
    verification = (VerificationStatus.COORDINATOR_CONFIRMED
                    if payload.confirmation_status == "FARMER_CONFIRMED" else VerificationStatus.UNVERIFIED)
    try:
        _apply_observation(lot, values)
        record = _record(
            session, organization_id=context.organization_id, channel=payload.source_channel,
            external_reference=f"coordinator:{uuid4()}", actor_user_id=context.user_id,
            farmer_id=farmer.id, lot=lot, payload=values, verification=verification,
            effective_at=payload.effective_at, evidence=payload.evidence_reference,
            source_actor=f"recorded-by:{context.user_id}; source-farmer:{farmer.id}",
        )
        session.commit()
        return {"ingestion_record_id": str(record.id), "status": record.status.value,
                "recorded_by": str(context.user_id), "source": payload.source_channel.value,
                "verification_status": verification.value}
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from exc
