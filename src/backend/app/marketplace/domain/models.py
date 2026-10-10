from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.domain.common import Crop
from src.backend.app.infrastructure.database.base import Base


class MarketplaceOrderStatus(StrEnum):
    PLACED = "PLACED"
    CANCELLED = "CANCELLED"


class MarketplaceOrder(Base):
    __tablename__ = "marketplace_orders"
    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_marketplace_order_quantity_positive"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    buyer_id: Mapped[UUID] = mapped_column(ForeignKey("buyers.id"), nullable=False, index=True)
    customer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    production_lot_id: Mapped[UUID] = mapped_column(ForeignKey("production_lots.id"), nullable=False, index=True)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    status: Mapped[MarketplaceOrderStatus] = mapped_column(
        Enum(MarketplaceOrderStatus, native_enum=False), nullable=False, default=MarketplaceOrderStatus.PLACED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AvailabilityWatch(Base):
    __tablename__ = "availability_watches"
    __table_args__ = (CheckConstraint("minimum_quantity_kg > 0", name="ck_watch_quantity_positive"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    buyer_id: Mapped[UUID] = mapped_column(ForeignKey("buyers.id"), nullable=False, index=True)
    customer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    crop: Mapped[Crop] = mapped_column(Enum(Crop, native_enum=False), nullable=False)
    minimum_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AvailabilityAlert(Base):
    __tablename__ = "availability_alerts"
    __table_args__ = (UniqueConstraint("watch_id", "production_lot_id", name="uq_alert_watch_lot"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    watch_id: Mapped[UUID] = mapped_column(ForeignKey("availability_watches.id"), nullable=False, index=True)
    production_lot_id: Mapped[UUID] = mapped_column(ForeignKey("production_lots.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
