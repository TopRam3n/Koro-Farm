from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.demand.domain.models import Buyer
from app.domain.common import Crop
from app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from app.identity.domain.permissions import PermissionCode, RoleCode
from app.main_dependencies import get_session
from app.marketplace.domain.models import (
    AvailabilityAlert,
    AvailabilityWatch,
    MarketplaceOrder,
    MarketplaceOrderStatus,
)
from app.supply.domain.models import Farmer, ProductionLot, ProductionLotStatus

router = APIRouter(prefix="/marketplace", tags=["customer marketplace"])


class OrderCreate(BaseModel):
    production_lot_id: UUID
    quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    buyer_id: UUID | None = None


class WatchCreate(BaseModel):
    crop: Crop
    minimum_quantity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    buyer_id: UUID | None = None


def _buyer_scope(context: AuthorizationContext, session: Session, requested_id: UUID | None = None) -> Buyer | None:
    if context.role == RoleCode.BUYER:
        if context.buyer_id is None:
            raise HTTPException(403, "buyer membership must be linked to a buyer account")
        if requested_id is not None and requested_id != context.buyer_id:
            raise HTTPException(403, "buyer access denied")
        buyer_id = context.buyer_id
    elif context.role == RoleCode.PLATFORM_ADMIN:
        if requested_id is None:
            return None
        buyer_id = requested_id
    else:
        raise HTTPException(403, "buyer membership required")

    buyer = session.scalar(select(Buyer).where(
        Buyer.id == buyer_id, Buyer.organization_id == context.organization_id,
    ))
    if buyer is None:
        raise HTTPException(404, "buyer not found")
    return buyer


def _availability_row(lot: ProductionLot, farmer: Farmer) -> dict:
    return {
        "production_lot_id": str(lot.id),
        "farmer_id": str(farmer.id),
        "farmer_name": farmer.name,
        "parish": farmer.parish,
        "crop": lot.crop.value,
        "quality_grade_estimate": lot.quality_grade_estimate.value,
        "harvest_start": lot.harvest_start,
        "harvest_end": lot.harvest_end,
        "expected_quantity_kg": str(lot.expected_quantity_kg),
        "available_quantity_kg": str(lot.available_quantity_kg - lot.reserved_quantity_kg),
        "availability_confidence": lot.availability_confidence.value,
        "last_reported_at": lot.last_verified_at,
    }


def _order_row(order: MarketplaceOrder, lot: ProductionLot, farmer: Farmer) -> dict:
    return {
        "id": str(order.id),
        "production_lot_id": str(lot.id),
        "farmer_name": farmer.name,
        "parish": farmer.parish,
        "crop": lot.crop.value,
        "quality_grade_estimate": lot.quality_grade_estimate.value,
        "quantity_kg": str(order.quantity_kg),
        "status": order.status.value,
        "created_at": order.created_at,
    }


@router.get("/availability", dependencies=[Depends(require_permission(PermissionCode.MARKETPLACE_VIEW))])
def list_availability(
    crop: Crop | None = None,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    statement = select(ProductionLot, Farmer).join(Farmer, Farmer.id == ProductionLot.farmer_id).where(
        Farmer.organization_id == context.organization_id,
        Farmer.active.is_(True),
        ProductionLot.status == ProductionLotStatus.AVAILABLE,
        ProductionLot.available_quantity_kg > ProductionLot.reserved_quantity_kg,
    )
    if crop is not None:
        statement = statement.where(ProductionLot.crop == crop)
    rows = session.execute(statement.order_by(ProductionLot.harvest_start, Farmer.name, ProductionLot.id)).all()
    return {"items": [_availability_row(lot, farmer) for lot, farmer in rows]}


@router.post("/orders", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.ORDER_CREATE))])
def create_order(
    payload: OrderCreate,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer = _buyer_scope(context, session, payload.buyer_id)
    if buyer is None:
        raise HTTPException(422, "buyer_id is required to attribute a platform administrator order")
    row = session.execute(
        select(ProductionLot, Farmer)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .where(
            ProductionLot.id == payload.production_lot_id,
            Farmer.organization_id == context.organization_id,
            Farmer.active.is_(True),
            ProductionLot.status == ProductionLotStatus.AVAILABLE,
        )
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "available production lot not found")
    lot, farmer = row
    remaining = lot.available_quantity_kg - lot.reserved_quantity_kg
    if payload.quantity_kg > remaining:
        raise HTTPException(409, f"only {remaining} kg remains available")

    lot.reserved_quantity_kg += payload.quantity_kg
    lot.version += 1
    order = MarketplaceOrder(
        organization_id=context.organization_id,
        buyer_id=buyer.id,
        customer_user_id=context.user_id,
        production_lot_id=lot.id,
        quantity_kg=payload.quantity_kg,
        status=MarketplaceOrderStatus.PLACED,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return _order_row(order, lot, farmer)


@router.get("/orders", dependencies=[Depends(require_permission(PermissionCode.ORDER_VIEW))])
def list_orders(
    buyer_id: UUID | None = None,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer = _buyer_scope(context, session, buyer_id)
    statement = (
        select(MarketplaceOrder, ProductionLot, Farmer)
        .join(ProductionLot, ProductionLot.id == MarketplaceOrder.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .where(
            MarketplaceOrder.organization_id == context.organization_id,
        )
        .order_by(MarketplaceOrder.created_at.desc(), MarketplaceOrder.id)
    )
    if buyer is not None:
        statement = statement.where(MarketplaceOrder.buyer_id == buyer.id)
    rows = session.execute(statement).all()
    return {"items": [_order_row(order, lot, farmer) for order, lot, farmer in rows]}


@router.post("/watches", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission(PermissionCode.AVAILABILITY_ALERT_MANAGE))])
def create_watch(
    payload: WatchCreate,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer = _buyer_scope(context, session, payload.buyer_id)
    if buyer is None:
        raise HTTPException(422, "buyer_id is required to attribute a platform administrator availability watch")
    watch = AvailabilityWatch(
        organization_id=context.organization_id,
        buyer_id=buyer.id,
        customer_user_id=context.user_id,
        crop=payload.crop,
        minimum_quantity_kg=payload.minimum_quantity_kg,
    )
    session.add(watch)
    session.commit()
    return {
        "id": str(watch.id),
        "crop": watch.crop.value,
        "minimum_quantity_kg": str(watch.minimum_quantity_kg),
        "active": watch.active,
    }


@router.get("/alerts", dependencies=[Depends(require_permission(PermissionCode.AVAILABILITY_ALERT_MANAGE))])
def list_alerts(
    buyer_id: UUID | None = None,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    buyer = _buyer_scope(context, session, buyer_id)
    watches_statement = select(AvailabilityWatch).where(
        AvailabilityWatch.organization_id == context.organization_id,
        AvailabilityWatch.active.is_(True),
    )
    if buyer is not None:
        watches_statement = watches_statement.where(
            AvailabilityWatch.buyer_id == buyer.id,
            AvailabilityWatch.customer_user_id == context.user_id,
        )
    watches = session.scalars(watches_statement).all()

    try:
        for watch in watches:
            matches = session.execute(
                select(ProductionLot, Farmer)
                .join(Farmer, Farmer.id == ProductionLot.farmer_id)
                .where(
                    Farmer.organization_id == context.organization_id,
                    Farmer.active.is_(True),
                    ProductionLot.crop == watch.crop,
                    ProductionLot.status == ProductionLotStatus.AVAILABLE,
                    ProductionLot.available_quantity_kg - ProductionLot.reserved_quantity_kg >= watch.minimum_quantity_kg,
                )
            ).all()
            for lot, _farmer in matches:
                existing = session.scalar(select(AvailabilityAlert.id).where(
                    AvailabilityAlert.watch_id == watch.id,
                    AvailabilityAlert.production_lot_id == lot.id,
                ))
                if existing is None:
                    session.add(AvailabilityAlert(
                        organization_id=context.organization_id,
                        watch_id=watch.id,
                        production_lot_id=lot.id,
                    ))
        session.commit()
    except IntegrityError:
        session.rollback()

    alerts_statement = (
        select(AvailabilityAlert, AvailabilityWatch, ProductionLot, Farmer)
        .join(AvailabilityWatch, AvailabilityWatch.id == AvailabilityAlert.watch_id)
        .join(ProductionLot, ProductionLot.id == AvailabilityAlert.production_lot_id)
        .join(Farmer, Farmer.id == ProductionLot.farmer_id)
        .where(
            AvailabilityAlert.organization_id == context.organization_id,
        )
    )
    if buyer is not None:
        alerts_statement = alerts_statement.where(
            AvailabilityWatch.buyer_id == buyer.id,
            AvailabilityWatch.customer_user_id == context.user_id,
        )
    rows = session.execute(alerts_statement.order_by(AvailabilityAlert.created_at.desc(), AvailabilityAlert.id)).all()
    return {
        "items": [
            {
                "id": str(alert.id),
                "watch_id": str(watch.id),
                "crop": watch.crop.value,
                "minimum_quantity_kg": str(watch.minimum_quantity_kg),
                "available_quantity_kg": str(lot.available_quantity_kg - lot.reserved_quantity_kg),
                "farmer_name": farmer.name,
                "parish": farmer.parish,
                "quality_grade_estimate": lot.quality_grade_estimate.value,
                "production_lot_id": str(lot.id),
                "created_at": alert.created_at,
                "read": alert.read_at is not None,
            }
            for alert, watch, lot, farmer in rows
        ]
    }


@router.post("/alerts/{alert_id}/read", dependencies=[Depends(require_permission(PermissionCode.AVAILABILITY_ALERT_MANAGE))])
def mark_alert_read(
    alert_id: UUID,
    session: Session = Depends(get_session),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict:
    statement = (
        select(AvailabilityAlert)
        .join(AvailabilityWatch, AvailabilityWatch.id == AvailabilityAlert.watch_id)
        .where(
            AvailabilityAlert.id == alert_id,
            AvailabilityAlert.organization_id == context.organization_id,
        )
    )
    if context.role == RoleCode.BUYER:
        statement = statement.where(
            AvailabilityWatch.buyer_id == context.buyer_id,
            AvailabilityWatch.customer_user_id == context.user_id,
        )
    alert = session.scalar(statement)
    if alert is None:
        raise HTTPException(404, "availability alert not found")
    alert.read_at = datetime.now(timezone.utc)
    session.commit()
    return {"id": str(alert.id), "read": True}
