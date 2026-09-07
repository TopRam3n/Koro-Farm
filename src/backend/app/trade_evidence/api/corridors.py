from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.main_dependencies import get_session
from src.backend.app.trade_evidence.domain.corridors import TradeCorridor

router = APIRouter(prefix="/trade-corridors", tags=["trade-corridors"])

@router.get("")
def list_corridors(session: Session = Depends(get_session)) -> list[dict]:
    return [{"id": str(c.id), "name": c.name, "origin_country": c.origin_country, "destination_country": c.destination_country, "transport_mode": c.transport_mode, "active": c.active, "last_verified_at": c.last_verified_at} for c in session.scalars(select(TradeCorridor).order_by(TradeCorridor.name))]

@router.get("/{corridor_id}")
def get_corridor(corridor_id: UUID, session: Session = Depends(get_session)) -> dict:
    corridor = session.get(TradeCorridor, corridor_id)
    if corridor is None: raise HTTPException(404, "trade corridor not found")
    return {"id": str(corridor.id), "name": corridor.name, "origin_country": corridor.origin_country, "destination_country": corridor.destination_country, "transport_mode": corridor.transport_mode, "default_dispatch_lead_hours": corridor.default_dispatch_lead_hours, "active": corridor.active, "last_verified_at": corridor.last_verified_at}
