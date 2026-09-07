from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class TradeCorridor(Base):
    """A configured route, not a claim that a shipment is trade-compliant."""
    __tablename__ = "trade_corridors"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    origin_country: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(100), nullable=False)
    transport_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    default_dispatch_lead_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48)
    export_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("fulfilment_nodes.id"))
    import_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("fulfilment_nodes.id"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
