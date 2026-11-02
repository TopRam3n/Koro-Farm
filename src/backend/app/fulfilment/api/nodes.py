"""Fulfilment sites (R1 WP4, M2): where produce is received. Organization-scoped; deactivated, never deleted."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.events import record_event
from src.backend.app.fulfilment.domain.models import FulfilmentNode
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context, require_permission
from src.backend.app.identity.domain.permissions import PermissionCode
from src.backend.app.main_dependencies import get_session

router = APIRouter(prefix="/fulfilment-nodes", tags=["fulfilment sites"])


class NodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    node_type: str = Field(min_length=2, max_length=80, description="e.g. packhouse, aggregation hub, cold store")
    parish: str = Field(min_length=2, max_length=100)


class NodeRead(BaseModel):
    id: UUID
    name: str
    node_type: str
    parish: str
    active: bool
    created_at: datetime


def _read(node: FulfilmentNode) -> NodeRead:
    return NodeRead(id=node.id, name=node.name, node_type=node.node_type, parish=node.parish, active=node.active, created_at=node.created_at)


@router.get("", response_model=list[NodeRead], dependencies=[Depends(require_permission(PermissionCode.RECEIVING_VIEW))])
def list_nodes(include_inactive: bool = False, session: Session = Depends(get_session),
               context: AuthorizationContext = Depends(get_authorization_context)) -> list[NodeRead]:
    statement = select(FulfilmentNode).where(FulfilmentNode.organization_id == context.organization_id)
    if not include_inactive:
        statement = statement.where(FulfilmentNode.active.is_(True))
    return [_read(n) for n in session.scalars(statement.order_by(FulfilmentNode.name))]


@router.post("", response_model=NodeRead, status_code=201, dependencies=[Depends(require_permission(PermissionCode.FULFILMENT_SITE_MANAGE))])
def create_node(payload: NodeCreate, session: Session = Depends(get_session),
                context: AuthorizationContext = Depends(get_authorization_context)) -> NodeRead:
    node = FulfilmentNode(organization_id=context.organization_id, name=payload.name.strip(), node_type=payload.node_type.strip(),
                          parish=payload.parish.strip(), active=True)
    session.add(node)
    session.flush()
    session.commit()
    session.refresh(node)
    return _read(node)


@router.post("/{fulfilment_node_id}/deactivate", response_model=NodeRead,
             dependencies=[Depends(require_permission(PermissionCode.FULFILMENT_SITE_MANAGE))])
def deactivate_node(fulfilment_node_id: UUID, session: Session = Depends(get_session),
                    context: AuthorizationContext = Depends(get_authorization_context)) -> NodeRead:
    node = session.scalar(select(FulfilmentNode).where(FulfilmentNode.id == fulfilment_node_id).with_for_update())
    if not node.active:
        raise HTTPException(409, "this site is already deactivated")
    node.active = False
    session.commit()
    session.refresh(node)
    return _read(node)
