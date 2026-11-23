from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.backend.app.domain.common import CropCode
from src.backend.app.supply.domain.crops import CropRecord


def visible_crops(organization_id: UUID):
    """The shared catalogue plus the organization's own crops."""
    return select(CropRecord).where(or_(CropRecord.organization_id.is_(None), CropRecord.organization_id == organization_id))


def require_active_crop(session: Session, organization_id: UUID, code: str) -> CropCode:
    """422 unless ``code`` is an active crop visible to the organization."""
    found = session.scalar(visible_crops(organization_id).where(CropRecord.code == str(code), CropRecord.active.is_(True)))
    if found is None:
        raise HTTPException(422, f"crop {code!r} is not in your crop catalogue")
    return CropCode(found.code)
