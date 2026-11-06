"""Source lineage of model runs and explicit rights decisions for derived output (R1 WP5 review correction).

A forecast is derived data. Whether it may be sent to an external model provider (or published, or used
commercially) is not inferred from the licences of its sources: a person records a decision per model run and purpose,
seeing the run's lineage and each source's licence status at that moment (`record_rights_decision`). The rules:
* Lineage is complete only when the run has at least one recorded input and every input resolves to an observation,
  its dataset and its source. Unknown lineage blocks every use that needs a decision.
* A decision is append-only; the current one is the newest per run and purpose. PERMITTED needs an approval reference.
* No decision, or NOT_PERMITTED, means no. Code never turns source licences into a derived-data decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.app.agriculture.domain.models import (
    Dataset, DerivedRightsDecision, ModelRun, ModelRunInput, Observation, Source,
)

PURPOSES = ("EXTERNAL_LLM", "PUBLICATION", "COMMERCIAL_USE")


@dataclass
class Lineage:
    model_run_id: str
    inputs: int = 0
    unresolved: int = 0
    sources: list[dict] = field(default_factory=list)  # [{"code", "licence_review_status", "observations"}]

    @property
    def complete(self) -> bool:
        return self.inputs > 0 and self.unresolved == 0 and bool(self.sources)

    def as_dict(self) -> dict:
        return {"model_run_id": self.model_run_id, "inputs": self.inputs, "unresolved": self.unresolved,
                "complete": self.complete, "sources": self.sources}


def lineage_of(session: Session, model_run_id: UUID) -> Lineage:
    lineage = Lineage(str(model_run_id))
    rows = session.execute(
        select(ModelRunInput.observation_id, Source.code, Source.licence_review_status)
        .select_from(ModelRunInput)
        .outerjoin(Observation, Observation.id == ModelRunInput.observation_id)
        .outerjoin(Dataset, Dataset.id == Observation.dataset_id)
        .outerjoin(Source, Source.id == Dataset.source_id)
        .where(ModelRunInput.model_run_id == model_run_id)).all()
    counts: dict[tuple[str, str], int] = {}
    for _, code, status in rows:
        lineage.inputs += 1
        if code is None:
            lineage.unresolved += 1
            continue
        counts[(code, status)] = counts.get((code, status), 0) + 1
    lineage.sources = [{"code": code, "licence_review_status": status, "observations": n}
                       for (code, status), n in sorted(counts.items())]
    return lineage


def current_decision(session: Session, model_run_id: UUID, purpose: str) -> DerivedRightsDecision | None:
    return session.scalar(select(DerivedRightsDecision).where(
        DerivedRightsDecision.model_run_id == model_run_id, DerivedRightsDecision.purpose == purpose)
        .order_by(DerivedRightsDecision.created_at.desc(), DerivedRightsDecision.id.desc()).limit(1))


class RightsDecisionError(ValueError):
    pass


def record_rights_decision(session: Session, *, model_run_id: UUID, purpose: str, permitted: bool, basis: str,
                           decided_by: str, approval_reference: str | None = None) -> DerivedRightsDecision:
    """Record a person's decision. PERMITTED needs complete lineage and an approval reference; the source licence
    statuses seen at decision time are stored with it."""
    from datetime import datetime, timezone
    if purpose not in PURPOSES:
        raise RightsDecisionError(f"purpose must be one of {PURPOSES}")
    if session.get(ModelRun, model_run_id) is None:
        raise RightsDecisionError("model run not found")
    if len(basis.strip()) < 10:
        raise RightsDecisionError("state the basis for the decision")
    lineage = lineage_of(session, model_run_id)
    if permitted and not lineage.complete:
        raise RightsDecisionError("lineage is incomplete: a use cannot be permitted for output whose sources are unknown")
    if permitted and not (approval_reference or "").strip():
        raise RightsDecisionError("a permitted use needs the approval reference")
    decision = DerivedRightsDecision(model_run_id=model_run_id, purpose=purpose, decision="PERMITTED" if permitted else "NOT_PERMITTED",
                                     basis=basis.strip(), source_statuses=lineage.sources, decided_by=decided_by,
                                     approval_reference=(approval_reference or "").strip() or None,
                                     created_at=datetime.now(timezone.utc))
    session.add(decision)
    session.flush()
    return decision
