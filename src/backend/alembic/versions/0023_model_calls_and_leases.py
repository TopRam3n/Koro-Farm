"""recovery model calls and lock-free planning leases

Revision ID: 0023_model_calls_and_leases
Revises: 0022_recovery_agent

Additive only.
* recovery_tasks.planning_lease_id / planning_lease_until / planning_fingerprint: a worker asks a model with no
  database transaction open; it may use the answer only while its lease stands and the evidence is unchanged.
* recovery_model_calls: one append-only row per model call (provider, exact model, latency, token usage, estimated
  cost and its price version, validation outcome, fallback reason). No prompts, reasoning or credentials.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_model_calls_and_leases"
down_revision: Union[str, None] = "0022_recovery_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("recovery_tasks") as batch:
        batch.add_column(sa.Column("planning_lease_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("planning_lease_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("planning_fingerprint", sa.String(64), nullable=True))
    op.create_table(
        "recovery_model_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("recovery_tasks.id"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("configured_model", sa.String(120), nullable=False),
        sa.Column("structured_mode", sa.String(20), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("price_version", sa.String(40), nullable=False),
        sa.Column("cost_basis", sa.String(200), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("error_kind", sa.String(30), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("violations", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recovery_model_calls_task_id", "recovery_model_calls", ["task_id"])
    op.create_index("ix_recovery_model_calls_organization_id", "recovery_model_calls", ["organization_id"])


def downgrade() -> None:
    op.drop_table("recovery_model_calls")
    with op.batch_alter_table("recovery_tasks") as batch:
        batch.drop_column("planning_fingerprint")
        batch.drop_column("planning_lease_until")
        batch.drop_column("planning_lease_id")
