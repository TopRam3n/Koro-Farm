"""recovery agent: tasks, incidents, steps, proposals, approvals, executions, approval policy; role policy

Revision ID: 0022_recovery_agent
Revises: 0021_worker_heartbeats

Additive tables, plus the WP3 recovery role policy for databases created before it:
* supply coordinators may approve ordinary recovery (recovery.approve);
* procurement managers and organization administrators may give elevated approval (recovery.approve_elevated);
* procurement managers may ask for recovery planning (recovery.propose);
* no role holds recovery.execute: only the gateway executes, and only an approved proposal.
The permission rows are informational (authorization reads identity/domain/permissions.py); they are kept in step.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_recovery_agent"
down_revision: Union[str, None] = "0021_worker_heartbeats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE = "status IN ('QUEUED','AWAITING_APPROVAL','EXECUTING','AWAITING_SUPPLIER','ESCALATED')"
GRANTS = [("SUPPLY_COORDINATOR", "recovery.approve"), ("PROCUREMENT_MANAGER", "recovery.approve_elevated"),
          ("PROCUREMENT_MANAGER", "recovery.propose"), ("ORGANIZATION_ADMIN", "recovery.approve_elevated"),
          ("PLATFORM_ADMIN", "recovery.approve_elevated")]
REVOKES = [("SUPPLY_COORDINATOR", "recovery.execute"), ("PLATFORM_ADMIN", "recovery.execute")]


def _uuid(name, *args, **kw):
    return sa.Column(name, sa.Uuid(), *args, **kw)


def upgrade() -> None:
    op.create_table(
        "recovery_tasks",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposals_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("step_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalated_kg", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("terminal_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recovery_tasks_organization_id", "recovery_tasks", ["organization_id"])
    op.create_index("ix_recovery_tasks_requirement_id", "recovery_tasks", ["requirement_id"])
    op.create_index("ix_recovery_tasks_runnable", "recovery_tasks", ["status", "next_run_at"])
    op.create_index("uq_recovery_tasks_active_requirement", "recovery_tasks", ["requirement_id"], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))

    op.create_table(
        "recovery_incidents",
        _uuid("id", primary_key=True),
        _uuid("task_id", sa.ForeignKey("recovery_tasks.id"), nullable=False),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("source_key", sa.String(200), nullable=False),
        _uuid("exception_id", sa.ForeignKey("supply_exceptions.id"), nullable=True),
        _uuid("source_event_id", nullable=True),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "source_key", name="uq_recovery_incident_source"),
    )
    for column in ("task_id", "organization_id", "requirement_id"):
        op.create_index(f"ix_recovery_incidents_{column}", "recovery_incidents", [column])

    op.create_table(
        "recovery_steps",
        _uuid("id", primary_key=True),
        _uuid("task_id", sa.ForeignKey("recovery_tasks.id"), nullable=False),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        _uuid("proposal_id", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "sequence", name="uq_recovery_step_sequence"),
    )
    for column in ("task_id", "organization_id"):
        op.create_index(f"ix_recovery_steps_{column}", "recovery_steps", [column])

    op.create_table(
        "recovery_proposals",
        _uuid("id", primary_key=True),
        _uuid("task_id", sa.ForeignKey("recovery_tasks.id"), nullable=False),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("task_id", "version", name="uq_recovery_proposal_version"),
    )
    for column in ("task_id", "organization_id", "requirement_id"):
        op.create_index(f"ix_recovery_proposals_{column}", "recovery_proposals", [column])

    op.create_table(
        "recovery_approvals",
        _uuid("id", primary_key=True),
        _uuid("proposal_id", sa.ForeignKey("recovery_proposals.id"), nullable=False),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        _uuid("reviewer_user_id", nullable=False),
        _uuid("reviewer_membership_id", nullable=False),
        sa.Column("reviewer_role", sa.String(30), nullable=False),
        sa.Column("elevated", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("proposal_id", "reviewer_user_id", name="uq_recovery_approval_reviewer"),
    )
    for column in ("proposal_id", "organization_id"):
        op.create_index(f"ix_recovery_approvals_{column}", "recovery_approvals", [column])

    op.create_table(
        "recovery_executions",
        _uuid("id", primary_key=True),
        _uuid("proposal_id", sa.ForeignKey("recovery_proposals.id"), nullable=False),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("action_index", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("proposal_id", "action_index", name="uq_recovery_execution_action"),
    )
    for column in ("proposal_id", "organization_id"):
        op.create_index(f"ix_recovery_executions_{column}", "recovery_executions", [column])

    op.create_table(
        "recovery_approval_policies",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("max_cost_increase_jmd", sa.Numeric(14, 2), nullable=True),
        sa.Column("max_cost_increase_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        _uuid("set_by_user_id", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "version", name="uq_recovery_policy_version"),
    )
    op.create_index("ix_recovery_approval_policies_organization_id", "recovery_approval_policies", ["organization_id"])

    bind = op.get_bind()
    # Explicit casts: PostgreSQL cannot infer parameter types in INSERT ... SELECT.
    bind.execute(sa.text("INSERT INTO permissions (code, description) SELECT CAST(:code AS VARCHAR(100)), CAST(:description AS VARCHAR(500)) "
                         "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)"),
                 {"code": "recovery.approve_elevated", "description": "Recovery Approve Elevated"})
    for role, permission in GRANTS:
        bind.execute(sa.text("INSERT INTO role_permissions (role_code, permission_code) "
                             "SELECT CAST(:role AS VARCHAR(30)), CAST(:permission AS VARCHAR(100)) "
                             "WHERE EXISTS (SELECT 1 FROM roles WHERE code = :role) AND NOT EXISTS "
                             "(SELECT 1 FROM role_permissions WHERE role_code = :role AND permission_code = :permission)"),
                     {"role": role, "permission": permission})
    for role, permission in REVOKES:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE role_code = :role AND permission_code = :permission"),
                     {"role": role, "permission": permission})


def downgrade() -> None:
    bind = op.get_bind()
    for role, permission in GRANTS:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE role_code = :role AND permission_code = :permission"),
                     {"role": role, "permission": permission})
    for role, permission in REVOKES:
        bind.execute(sa.text("INSERT INTO role_permissions (role_code, permission_code) "
                             "SELECT CAST(:role AS VARCHAR(30)), CAST(:permission AS VARCHAR(100)) WHERE NOT EXISTS (SELECT 1 FROM role_permissions WHERE role_code = :role AND permission_code = :permission)"),
                     {"role": role, "permission": permission})
    for table in ("recovery_approval_policies", "recovery_executions", "recovery_approvals", "recovery_proposals",
                  "recovery_steps", "recovery_incidents", "recovery_tasks"):
        op.drop_table(table)
