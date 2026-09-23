import hashlib
import csv
import io
import json
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.ingestion.domain.models import (
    BulkImport, BulkImportRow, FreshnessStatus, ImportStatus, IngestionRecord, IngestionStatus, OperationalObservation,
    SecureActionLink, SecureActionPurpose, SourceChannel, VerificationStatus,
)
from src.backend.app.main_dependencies import get_session
from src.backend.app.supply.domain.models import Farmer, ProductionLot
from src.backend.app.demand.domain.models import Buyer, Requirement
from src.backend.app.domain.common import AvailabilityConfidence, Crop, Grade
from src.backend.app.supply.domain.models import ProductionLotStatus

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


class ImportPreviewCommand(BaseModel):
    entity_type: str
    source_file_name: str = Field(min_length=1, max_length=255)
    csv_content: str = Field(min_length=1, max_length=2_000_000)


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


def _find_link(token: str, session: Session, lock: bool = False, allow_used: bool = False) -> SecureActionLink:
    statement = select(SecureActionLink).where(
        SecureActionLink.token_hash == hashlib.sha256(token.encode()).hexdigest()
    )
    if lock:
        statement = statement.with_for_update()
    link = session.scalar(statement)
    if link is None or link.revoked_at is not None:
        raise HTTPException(404, "secure action not found")
    if link.used_at is not None:
        if allow_used:
            return link
        raise HTTPException(409, "secure action has already been used")
    now = datetime.now(timezone.utc)
    expires_at = _aware(link.expires_at)
    if expires_at <= now:
        raise HTTPException(410, "secure action has expired")
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
    link = _find_link(token, session, lock=True, allow_used=True)
    external_reference = f"secure-link:{link.id}:{idempotency_key}"
    if link.used_at is not None:
        prior = session.scalar(select(IngestionRecord).where(
            IngestionRecord.external_reference == external_reference
        ))
        if prior is None:
            raise HTTPException(409, "secure action has already been used")
        return {"ingestion_record_id": str(prior.id), "status": prior.status.value,
                "verification_status": VerificationStatus.SELF_REPORTED.value,
                "freshness_status": FreshnessStatus.CURRENT.value}
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
        if "declined" not in values:
            _apply_observation(lot, values)
        record = _record(
            session, organization_id=link.organization_id, channel=SourceChannel.SECURE_LINK,
            external_reference=external_reference, actor_user_id=None,
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


IMPORT_FIELDS = {
    "farmers": ["name", "parish"],
    "production_lots": ["farmer_id", "crop", "harvest_start", "harvest_end", "expected_quantity_kg",
                        "available_quantity_kg", "grade", "availability_confidence", "parish"],
    "buyer_requirements": ["buyer_id", "crop", "grade", "required_quantity_kg",
                           "delivery_window_start", "delivery_window_end"],
}


def _validate_import_row(entity_type: str, row: dict[str, str], session: Session,
                         organization_id: UUID) -> tuple[dict, list[str], list[str]]:
    normalized = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
    errors = [f"{field} is required" for field in IMPORT_FIELDS[entity_type] if not normalized.get(field)]
    warnings: list[str] = []
    if errors:
        return normalized, errors, warnings
    try:
        if entity_type == "farmers":
            duplicate = session.scalar(select(Farmer.id).where(
                Farmer.organization_id == organization_id, Farmer.name == normalized["name"],
                Farmer.parish == normalized["parish"],
            ))
            if duplicate:
                warnings.append(f"possible duplicate farmer {duplicate}")
        elif entity_type == "production_lots":
            farmer_id = UUID(normalized["farmer_id"])
            if session.scalar(select(Farmer.id).where(Farmer.id == farmer_id,
                                                       Farmer.organization_id == organization_id)) is None:
                errors.append("farmer_id was not found in the active organization")
            Crop(normalized["crop"]); Grade(normalized["grade"])
            AvailabilityConfidence(normalized["availability_confidence"])
            start, end = date.fromisoformat(normalized["harvest_start"]), date.fromisoformat(normalized["harvest_end"])
            expected, available = Decimal(normalized["expected_quantity_kg"]), Decimal(normalized["available_quantity_kg"])
            if start > end: errors.append("harvest window is invalid")
            if expected < 0 or available < 0: errors.append("quantities cannot be negative")
        else:
            buyer_id = UUID(normalized["buyer_id"])
            if session.scalar(select(Buyer.id).where(Buyer.id == buyer_id,
                                                      Buyer.organization_id == organization_id)) is None:
                errors.append("buyer_id was not found in the active organization")
            Crop(normalized["crop"]); Grade(normalized["grade"])
            quantity = Decimal(normalized["required_quantity_kg"])
            start = date.fromisoformat(normalized["delivery_window_start"])
            end = date.fromisoformat(normalized["delivery_window_end"])
            if quantity <= 0: errors.append("required quantity must be positive")
            if start > end: errors.append("delivery window is invalid")
    except (ValueError, ArithmeticError) as exc:
        errors.append(f"invalid typed value: {exc}")
    return normalized, errors, warnings


@router.get("/imports/templates/{entity_type}", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_VIEW))])
def import_template(entity_type: str) -> Response:
    if entity_type not in IMPORT_FIELDS:
        raise HTTPException(404, "import template not found")
    content = ",".join(IMPORT_FIELDS[entity_type]) + "\r\n"
    return Response(content, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="korofarm-{entity_type}-template.csv"'})


@router.post("/imports/preview", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def preview_import(payload: ImportPreviewCommand,
                   context: AuthorizationContext = Depends(get_authorization_context),
                   session: Session = Depends(get_session)) -> dict:
    if payload.entity_type not in IMPORT_FIELDS:
        raise HTTPException(422, "supported entity_type values are farmers, production_lots, buyer_requirements")
    file_digest = hashlib.sha256(payload.csv_content.encode()).hexdigest()
    existing = session.scalar(select(BulkImport).where(
        BulkImport.organization_id == context.organization_id, BulkImport.entity_type == payload.entity_type,
        BulkImport.file_digest == file_digest,
    ))
    if existing:
        raise HTTPException(409, detail={"message": "duplicate import file", "import_id": str(existing.id)})
    reader = csv.DictReader(io.StringIO(payload.csv_content))
    if reader.fieldnames is None:
        raise HTTPException(422, "CSV header is required")
    missing_headers = [field for field in IMPORT_FIELDS[payload.entity_type] if field not in reader.fieldnames]
    if missing_headers:
        raise HTTPException(422, f"missing CSV columns: {', '.join(missing_headers)}")
    parsed = []
    seen_row_digests: set[str] = set()
    for number, row in enumerate(reader, start=2):
        normalized, errors, warnings = _validate_import_row(payload.entity_type, row, session, context.organization_id)
        row_digest = _digest(normalized)
        if row_digest in seen_row_digests:
            errors.append("duplicate row in file")
        seen_row_digests.add(row_digest)
        parsed.append((number, normalized, errors, warnings))
    if not parsed:
        raise HTTPException(422, "CSV contains no data rows")
    item = BulkImport(
        organization_id=context.organization_id, actor_user_id=context.user_id, entity_type=payload.entity_type,
        source_file_name=payload.source_file_name, file_digest=file_digest, status=ImportStatus.PREVIEWED,
        accepted_rows=sum(not errors for _, _, errors, _ in parsed),
        rejected_rows=sum(bool(errors) for _, _, errors, _ in parsed),
        warning_rows=sum(bool(warnings) for _, _, _, warnings in parsed),
    )
    session.add(item); session.flush()
    rows = []
    for number, normalized, errors, warnings in parsed:
        import_row = BulkImportRow(
            import_id=item.id, row_number=number, row_digest=_digest(normalized), normalized_payload=normalized,
            validation_errors=errors, warnings=warnings,
        )
        session.add(import_row)
        rows.append({"row_number": number, "accepted": not errors, "errors": errors, "warnings": warnings})
    session.commit()
    return {"import_id": str(item.id), "status": item.status.value, "accepted_rows": item.accepted_rows,
            "rejected_rows": item.rejected_rows, "warning_rows": item.warning_rows, "rows": rows}


@router.post("/imports/{import_id}/confirm", dependencies=[Depends(require_permission(PermissionCode.SUPPLY_MANAGE))])
def confirm_import(import_id: UUID, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                   context: AuthorizationContext = Depends(get_authorization_context),
                   session: Session = Depends(get_session)) -> dict:
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    item = session.scalar(select(BulkImport).where(BulkImport.id == import_id,
                                                   BulkImport.organization_id == context.organization_id).with_for_update())
    if item is None:
        raise HTTPException(404, "import not found")
    if item.status == ImportStatus.IMPORTED:
        return {"import_id": str(item.id), "status": item.status.value, "imported_rows": item.accepted_rows,
                "rejected_rows": item.rejected_rows}
    rows = session.scalars(select(BulkImportRow).where(BulkImportRow.import_id == item.id).order_by(
        BulkImportRow.row_number)).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.validation_errors:
            continue
        data = row.normalized_payload
        if item.entity_type == "farmers":
            entity = Farmer(organization_id=context.organization_id, name=data["name"], parish=data["parish"])
        elif item.entity_type == "production_lots":
            entity = ProductionLot(
                farmer_id=UUID(data["farmer_id"]), crop=Crop(data["crop"]),
                harvest_start=date.fromisoformat(data["harvest_start"]), harvest_end=date.fromisoformat(data["harvest_end"]),
                expected_quantity_kg=Decimal(data["expected_quantity_kg"]),
                available_quantity_kg=Decimal(data["available_quantity_kg"]), reserved_quantity_kg=Decimal("0"),
                quality_grade_estimate=Grade(data["grade"]),
                availability_confidence=AvailabilityConfidence(data["availability_confidence"]),
                parish=data["parish"], status=ProductionLotStatus.AVAILABLE, last_verified_at=now,
            )
            entity.validate()
        else:
            entity = Requirement(
                buyer_id=UUID(data["buyer_id"]), crop=Crop(data["crop"]), grade=Grade(data["grade"]),
                required_quantity_kg=Decimal(data["required_quantity_kg"]),
                delivery_window_start=date.fromisoformat(data["delivery_window_start"]),
                delivery_window_end=date.fromisoformat(data["delivery_window_end"]),
            )
            entity.validate()
        session.add(entity); session.flush(); row.resulting_entity_id = entity.id
        correlation_id = uuid4()
        event_type = "requirement.created" if item.entity_type == "buyer_requirements" else "ingestion.entity_created"
        event = DomainEvent(
            event_type=event_type, aggregate_type=item.entity_type, aggregate_id=entity.id,
            correlation_id=correlation_id, actor_type="import",
            payload={"entity_type": item.entity_type, "entity_id": str(entity.id),
                     "import_id": str(item.id), "row_number": row.row_number},
            occurred_at=now,
        )
        session.add(event); session.flush()
        session.add(OutboxMessage(event_id=event.id, topic=event.event_type, payload=event.payload))
        session.add(IngestionRecord(
            organization_id=context.organization_id, channel=SourceChannel.CSV_IMPORT,
            external_reference=f"import:{item.id}:row:{row.row_number}", actor_user_id=context.user_id,
            target_entity_type=item.entity_type, target_entity_id=entity.id, payload_schema=f"{item.entity_type}-csv",
            payload_version="1.0", payload_digest=row.row_digest,
            validation_result={"valid": True, "errors": [], "warnings": row.warnings},
            status=IngestionStatus.ACCEPTED, domain_command=f"{item.entity_type}.create",
            resulting_event_id=event.id, correlation_id=correlation_id,
        ))
    item.status = ImportStatus.IMPORTED; item.imported_at = now
    session.commit()
    return {"import_id": str(item.id), "status": item.status.value, "imported_rows": item.accepted_rows,
            "rejected_rows": item.rejected_rows}
