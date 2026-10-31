"""Recovery tasks, proposals, approvals and executions (R1 WP3).

The recovery agent proposes; deterministic tools decide what is possible; people approve an exact proposal; the
gateway executes it. Every table here is append-only except the task's own state columns and a proposal's status.
A proposal's content and hash never change after it is written.
"""
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.infrastructure.database.base import Base


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"                        # created; the orchestrator will plan it
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # a proposal waits for its approvals
    EXECUTING = "EXECUTING"                  # approvals complete; the gateway will execute
    AWAITING_SUPPLIER = "AWAITING_SUPPLIER"  # approved requests were issued; waiting for supplier answers
    ESCALATED = "ESCALATED"                  # a shortfall remains that no offered option can cover; a person must act
    COMPLETED = "COMPLETED"                  # the order's shortfall is covered (or there was none to recover)
    CANCELLED = "CANCELLED"                  # the order was cancelled, or a person cancelled the task
    FAILED = "FAILED"                        # bounded retries exhausted; reason recorded


ACTIVE_TASK_STATUSES = (TaskStatus.QUEUED, TaskStatus.AWAITING_APPROVAL, TaskStatus.EXECUTING,
                        TaskStatus.AWAITING_SUPPLIER, TaskStatus.ESCALATED)
TERMINAL_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED)


class ProposalStatus(StrEnum):
    PENDING = "PENDING"        # waiting for approvals
    APPROVED = "APPROVED"      # every required approval recorded; not yet executed
    REJECTED = "REJECTED"      # a reviewer rejected it
    SUPERSEDED = "SUPERSEDED"  # the situation changed before approval; a newer proposal replaced it
    STALE = "STALE"            # refused at execution: approval no longer matched current state
    EXECUTED = "EXECUTED"      # every action applied
    PARTIAL = "PARTIAL"        # some actions applied, some failed (each recorded)


class ApprovalTier(StrEnum):
    ORDINARY = "ORDINARY"  # one approver with RECOVERY_APPROVE
    ELEVATED = "ELEVATED"  # two different approvers, at least one with RECOVERY_APPROVE_ELEVATED


class StepKind(StrEnum):
    INCIDENT = "INCIDENT"
    PLAN = "PLAN"
    DECISION = "DECISION"
    PROPOSE = "PROPOSE"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    EXECUTE = "EXECUTE"
    WAIT = "WAIT"
    ESCALATE = "ESCALATE"
    COMPLETE = "COMPLETE"
    CANCEL = "CANCEL"
    ERROR = "ERROR"


class RecoveryTask(Base):
    """One active recovery task per order. Every incident on the order joins it, so two exceptions on one order
    can never be planned independently against the same quantity (partial unique index on active tasks)."""
    __tablename__ = "recovery_tasks"
    __table_args__ = (
        Index("uq_recovery_tasks_active_requirement", "requirement_id", unique=True,
              postgresql_where=text("status IN ('QUEUED','AWAITING_APPROVAL','EXECUTING','AWAITING_SUPPLIER','ESCALATED')"),
              sqlite_where=text("status IN ('QUEUED','AWAITING_APPROVAL','EXECUTING','AWAITING_SUPPLIER','ESCALATED')")),
        Index("ix_recovery_tasks_runnable", "status", "next_run_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, native_enum=False, length=30), nullable=False,
                                               default=TaskStatus.QUEUED)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposals_made: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalated_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecoveryIncident(Base):
    """What started or joined a task: an exception, a dropout, a quality rejection. Recorded once per source."""
    __tablename__ = "recovery_incidents"
    __table_args__ = (UniqueConstraint("task_id", "source_key", name="uq_recovery_incident_source"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_tasks.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    exception_id: Mapped[UUID | None] = mapped_column(ForeignKey("supply_exceptions.id"), nullable=True)
    source_event_id: Mapped[UUID | None] = mapped_column(nullable=True)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecoveryStep(Base):
    """Append-only task timeline: what the orchestrator saw, decided and did, and who acted."""
    __tablename__ = "recovery_steps"
    __table_args__ = (UniqueConstraint("task_id", "sequence", name="uq_recovery_step_sequence"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_tasks.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[StepKind] = mapped_column(Enum(StepKind, native_enum=False, length=20), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)  # "recovery-agent", "recovery-gateway" or a user id
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    proposal_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecoveryProposal(Base):
    """An immutable proposal. `content` holds every bound fact (actions, quantities, costs, authorization validity,
    approval policy) and `content_hash` is its SHA-256; approvals name the hash they approved."""
    __tablename__ = "recovery_proposals"
    __table_args__ = (UniqueConstraint("task_id", "version", name="uq_recovery_proposal_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_tasks.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    requirement_id: Mapped[UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus, native_enum=False, length=20), nullable=False,
                                                   default=ProposalStatus.PENDING)
    tier: Mapped[ApprovalTier] = mapped_column(Enum(ApprovalTier, native_enum=False, length=20), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RecoveryApproval(Base):
    """A reviewer's decision on one proposal hash. A person decides a proposal at most once."""
    __tablename__ = "recovery_approvals"
    __table_args__ = (UniqueConstraint("proposal_id", "reviewer_user_id", name="uq_recovery_approval_reviewer"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_proposals.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # APPROVED / REJECTED
    reviewer_user_id: Mapped[UUID] = mapped_column(nullable=False)
    reviewer_membership_id: Mapped[UUID] = mapped_column(nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(30), nullable=False)
    elevated: Mapped[bool] = mapped_column(nullable=False, default=False)  # reviewer held RECOVERY_APPROVE_ELEVATED
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecoveryExecution(Base):
    """The outcome of one action of an approved proposal. The unique key makes execution idempotent across retries
    and worker restarts: an action is applied at most once."""
    __tablename__ = "recovery_executions"
    __table_args__ = (UniqueConstraint("proposal_id", "action_index", name="uq_recovery_execution_action"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_proposals.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # APPLIED / FAILED
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecoveryApprovalPolicy(Base):
    """An organization's cost tolerance for ordinary recovery approval. Rows are never edited: each change adds a
    new version, and a proposal binds the version it was evaluated under."""
    __tablename__ = "recovery_approval_policies"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_recovery_policy_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Largest landed-cost increase (J$) over the order's current cost per kg that a coordinator may approve alone.
    max_cost_increase_jmd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    max_cost_increase_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    set_by_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
