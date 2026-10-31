"""capacity reports record what had been delivered when they were made

Revision ID: 0020_capacity_delivered
Revises: 0019_capacity_exceptions

Additive only. A supplier reports what they can still supply; the lot's capacity ceiling is that plus what had
already been received. Existing reports were made before any delivery accounting, so they keep 0 delivered and
their ceiling equals what they reported, which is how they were applied.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_capacity_delivered"
down_revision: Union[str, None] = "0019_capacity_exceptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("capacity_reports") as batch:
        batch.add_column(sa.Column("delivered_at_report_kg", sa.Numeric(12, 3), nullable=False, server_default="0"))
        batch.create_check_constraint("ck_capacity_report_delivered_non_negative", "delivered_at_report_kg >= 0")


def downgrade() -> None:
    with op.batch_alter_table("capacity_reports") as batch:
        batch.drop_constraint("ck_capacity_report_delivered_non_negative", type_="check")
        batch.drop_column("delivered_at_report_kg")
