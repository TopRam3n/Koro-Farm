"""audit trail and deterministic recovery runs

Revision ID: 0003_supply_assurance_audit
Revises: 0002_supply_planning_and_economics
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_supply_assurance_audit"
down_revision = "0002_supply_planning_and_economics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    recovery_status = sa.Enum("RUNNING", "COMPLETED", "ESCALATED", name="recoverystatus", native_enum=False)
    op.create_table("domain_events", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False), sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False), sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(50), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])
    op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"])
    op.create_index("ix_domain_events_correlation_id", "domain_events", ["correlation_id"])
    op.create_table("command_deduplications", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("command_type", sa.String(100), nullable=False), sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("command_type", "idempotency_key", name="uq_command_idempotency"))
    op.create_table("recovery_runs", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False), sa.Column("status", recovery_status, nullable=False),
        sa.Column("active_key", sa.String(10)), sa.Column("lost_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("cause", sa.String(200), nullable=False),
        sa.Column("standby_activated_kg", sa.Numeric(12, 3), nullable=False), sa.Column("new_supply_accepted_kg", sa.Numeric(12, 3), nullable=False), sa.Column("remaining_shortfall_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("requirement_id", "active_key", name="uq_active_recovery_per_requirement"))
    op.create_table("outbox_messages", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("event_id", sa.Uuid(), sa.ForeignKey("domain_events.id"), nullable=False),
        sa.Column("topic", sa.String(100), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("event_id"))


def downgrade() -> None:
    op.drop_table("outbox_messages")
    op.drop_table("recovery_runs")
    op.drop_table("command_deduplications")
    op.drop_table("domain_events")
