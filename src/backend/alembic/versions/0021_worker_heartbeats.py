"""worker heartbeats for supply-exception monitoring

Revision ID: 0021_worker_heartbeats
Revises: 0020_capacity_delivered

Additive only. Each worker process records its last tick, so the API can report whether exception detection and
deadline enforcement are actually running instead of assuming it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_worker_heartbeats"
down_revision: Union[str, None] = "0020_capacity_delivered"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(200), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_tick", sa.JSON(), nullable=False),
    )
    op.create_index("ix_worker_heartbeats_last_beat_at", "worker_heartbeats", ["last_beat_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_last_beat_at", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
