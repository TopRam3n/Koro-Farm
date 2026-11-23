from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.operations import operational_status
from src.backend.app.identity.application.authorization import AuthorizationContext, get_authorization_context
from src.backend.app.main_dependencies import get_session

router = APIRouter(prefix="/system", tags=["operations"])


@router.get("/status")
def system_status(session: Session = Depends(get_session),
                  context: AuthorizationContext = Depends(get_authorization_context)) -> dict:
    """Whether exception detection and deadline enforcement are running, with this organization's backlog."""
    return operational_status(session, organization_id=context.organization_id)
