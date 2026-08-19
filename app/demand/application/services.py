from sqlalchemy.orm import Session

from app.demand.domain.models import Requirement


def create_requirement(session: Session, requirement: Requirement) -> Requirement:
    requirement.validate()
    session.add(requirement)
    session.commit()
    session.refresh(requirement)
    return requirement
