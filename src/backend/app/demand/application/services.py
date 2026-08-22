from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime, timezone

from src.backend.app.assurance.domain.models import DomainEvent, OutboxMessage
from src.backend.app.demand.domain.models import Requirement


def create_requirement(session: Session, requirement: Requirement) -> Requirement:
    requirement.validate()
    session.add(requirement)
    session.flush()
    event = DomainEvent(event_type="requirement.created", aggregate_type="requirement", aggregate_id=requirement.id,
                        correlation_id=uuid4(), actor_type="api", payload={"required_kg": str(requirement.required_quantity_kg)},
                        occurred_at=datetime.now(timezone.utc))
    session.add(event)
    session.flush()
    session.add(OutboxMessage(event_id=event.id, topic=event.event_type, payload=event.payload))
    session.commit()
    session.refresh(requirement)
    return requirement
