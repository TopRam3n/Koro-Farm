from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.domain.common.types import CROP_CODE_LENGTH
from src.backend.app.infrastructure.database.base import Base


class CropRecord(Base):
    """A crop that orders and lots may reference.

    ``organization_id`` NULL marks the shared catalogue; otherwise the crop is private to one organization.
    A code is unique within the shared catalogue and within each organization.
    """
    __tablename__ = "crops"
    __table_args__ = (
        Index("uq_crops_global_code", "code", unique=True, postgresql_where=text("organization_id IS NULL"),
              sqlite_where=text("organization_id IS NULL")),
        Index("uq_crops_org_code", "organization_id", "code", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(CROP_CODE_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Shared catalogue seeded by migration 0016: the nine crops the platform already supported, plus scotch bonnet.
SHARED_CROPS = {
    "BANANA": "Banana", "BREADFRUIT": "Breadfruit", "CALLALOO": "Callaloo", "CASSAVA": "Cassava",
    "GINGER": "Ginger", "MANGO": "Mango", "PLANTAIN": "Plantain", "SCOTCH_BONNET": "Scotch bonnet pepper",
    "SWEET_POTATO": "Sweet potato", "YAM": "Yam",
}


def ensure_shared_crops(session) -> None:
    """Idempotently insert the shared catalogue (for databases built with create_all rather than Alembic)."""
    import uuid
    from sqlalchemy import select
    existing = set(session.scalars(select(CropRecord.code).where(CropRecord.organization_id.is_(None))))
    for code, name in SHARED_CROPS.items():
        if code not in existing:
            session.add(CropRecord(id=uuid.uuid5(uuid.NAMESPACE_URL, f"korofarm:crop:{code}"), organization_id=None,
                                   code=code, name=name, active=True))
    session.flush()
