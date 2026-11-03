"""physical event times kept apart from recording times; sequence reviews (technical-debt item 26)

Revision ID: 0025_physical_event_times
Revises: 0024_fulfilment_accounting

Additive. Nothing is rewritten.
* shipments.dispatch_time_basis: STATED (the operator gave the time the goods left), RECORDED (no time given; the
  recording time) or LEGACY. Every shipment dispatched before this migration is labelled LEGACY: its dispatched_at
  was always the time dispatch was recorded, and it stays exactly as it was.
* shipments.dispatch_recorded_at / dispatch_recorded_by_user_id: system time and author of the dispatch record
  (unknown, so NULL, for legacy rows).
* deliveries.recorded_at: when the delivery was entered (NULL for legacy rows; not guessed).
* fulfilment_sequence_reviews: one review per flagged physical event sequence.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025_physical_event_times"
down_revision: Union[str, None] = "0024_fulfilment_accounting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shipments") as batch:
        batch.add_column(sa.Column("dispatch_time_basis", sa.String(20), nullable=True))
        batch.add_column(sa.Column("dispatch_recorded_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("dispatch_recorded_by_user_id", sa.Uuid(), nullable=True))
    op.get_bind().execute(sa.text("UPDATE shipments SET dispatch_time_basis = 'LEGACY' WHERE dispatched_at IS NOT NULL"))
    with op.batch_alter_table("deliveries") as batch:
        batch.add_column(sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "fulfilment_sequence_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("finding_key", sa.String(120), nullable=False),
        sa.Column("finding", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("requirement_id", "finding_key", name="uq_sequence_review_finding"),
    )
    op.create_index("ix_fulfilment_sequence_reviews_organization_id", "fulfilment_sequence_reviews", ["organization_id"])
    op.create_index("ix_fulfilment_sequence_reviews_requirement_id", "fulfilment_sequence_reviews", ["requirement_id"])


def downgrade() -> None:
    op.drop_table("fulfilment_sequence_reviews")
    with op.batch_alter_table("deliveries") as batch:
        batch.drop_column("recorded_at")
    with op.batch_alter_table("shipments") as batch:
        batch.drop_column("dispatch_recorded_by_user_id")
        batch.drop_column("dispatch_recorded_at")
        batch.drop_column("dispatch_time_basis")
