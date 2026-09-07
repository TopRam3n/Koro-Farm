from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.domain.common import Crop
from src.backend.app.infrastructure.database.base import Base


class ComplianceRule(Base):
    __tablename__ = "compliance_rules"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    origin: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    crop: Mapped[Crop] = mapped_column(Enum(Crop, native_enum=False), nullable=False)
    product_form: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuing_body: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    required_before: Mapped[str] = mapped_column(String(100), nullable=False)
    lead_time: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date)
    source_citation: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_by: Mapped[str] = mapped_column(String(200), nullable=False)
