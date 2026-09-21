from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.backend.app.assurance.application.recovery import committed_quantity
from src.backend.app.demand.domain.models import Buyer, Requirement, SupplyHealth
from src.backend.app.main_dependencies import get_session
from src.backend.app.programmes.domain.models import Programme, ProgrammeStatus
from src.backend.app.supply.domain.planning_models import AllocationRole, AllocationStatus, SupplyAllocation

router = APIRouter(prefix="/programmes", tags=["programmes"])


class ProgrammeCreate(BaseModel):
    buyer_id: UUID
    name: str = Field(min_length=3, max_length=200)
    commodity_scope: str | None = Field(default=None, max_length=100)
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def valid_dates(cls, value: date, info):
        if start := info.data.get("start_date"):
            if value < start:
                raise ValueError("programme end date must not precede start date")
        return value


class ProgrammeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    buyer_id: UUID
    name: str
    commodity_scope: str | None
    start_date: date
    end_date: date
    status: ProgrammeStatus
    created_at: datetime


def _summary(session: Session, programme: Programme) -> dict:
    requirements = list(session.scalars(select(Requirement).where(Requirement.programme_id == programme.id)))
    committed = sum((committed_quantity(session, requirement.id) for requirement in requirements), Decimal("0"))
    standby = session.scalar(select(func.coalesce(func.sum(SupplyAllocation.quantity_kg), 0)).join(
        Requirement, Requirement.id == SupplyAllocation.requirement_id
    ).where(
        Requirement.programme_id == programme.id,
        SupplyAllocation.role == AllocationRole.STANDBY,
        SupplyAllocation.status == AllocationStatus.STANDBY,
    )) or Decimal("0")
    counts = {health.value: 0 for health in SupplyHealth}
    for requirement in requirements:
        counts[requirement.supply_health.value] += 1
    return {
        "programme": ProgrammeRead.model_validate(programme).model_dump(mode="json"),
        "requirement_count": len(requirements),
        "active_requirements": sum(1 for requirement in requirements if requirement.lifecycle_status.value not in {"CLOSED", "CANCELLED"}),
        "required_quantity_kg": str(sum((requirement.required_quantity_kg for requirement in requirements), Decimal("0"))),
        "committed_quantity_kg": str(committed),
        "standby_quantity_kg": str(standby),
        "requirements_by_supply_health": counts,
    }


@router.post("", response_model=ProgrammeRead, status_code=status.HTTP_201_CREATED)
def create_programme(payload: ProgrammeCreate, session: Session = Depends(get_session)) -> Programme:
    if session.get(Buyer, payload.buyer_id) is None:
        raise HTTPException(404, "buyer not found")
    programme = Programme(**payload.model_dump())
    session.add(programme)
    session.commit()
    session.refresh(programme)
    return programme


@router.get("")
def list_programmes(status_filter: ProgrammeStatus | None = None, offset: int = 0, limit: int = 50,
                    session: Session = Depends(get_session)) -> list[dict]:
    if offset < 0 or limit < 1 or limit > 200:
        raise HTTPException(422, "offset must be non-negative and limit must be between 1 and 200")
    statement = select(Programme)
    if status_filter is not None:
        statement = statement.where(Programme.status == status_filter)
    programmes = session.scalars(statement.order_by(Programme.created_at.desc(), Programme.id).offset(offset).limit(limit))
    return [_summary(session, programme) for programme in programmes]


@router.get("/{programme_id}")
def get_programme(programme_id: UUID, session: Session = Depends(get_session)) -> dict:
    programme = session.get(Programme, programme_id)
    if programme is None:
        raise HTTPException(404, "programme not found")
    return _summary(session, programme)


@router.post("/{programme_id}/requirements/{requirement_id}")
def associate_requirement(programme_id: UUID, requirement_id: UUID,
                          session: Session = Depends(get_session)) -> dict:
    programme = session.get(Programme, programme_id)
    requirement = session.get(Requirement, requirement_id)
    if programme is None or requirement is None:
        raise HTTPException(404, "programme or requirement not found")
    if programme.buyer_id != requirement.buyer_id:
        raise HTTPException(409, "programme and requirement must belong to the same buyer")
    requirement.programme_id = programme.id
    session.commit()
    return {"programme_id": str(programme.id), "requirement_id": str(requirement.id), "associated": True}
