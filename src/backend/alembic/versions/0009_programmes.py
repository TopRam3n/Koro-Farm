"""add buyer-facing programmes

Revision ID: 0009_programmes
Revises: 0008_trade_corridors
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_programmes"
down_revision: Union[str, None] = "0008_trade_corridors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "programmes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("commodity_scope", sa.String(length=100), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_programmes_buyer_id"), "programmes", ["buyer_id"], unique=False)
    op.add_column("requirements", sa.Column("programme_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_requirements_programme_id", "requirements", "programmes", ["programme_id"], ["id"])
    op.create_index(op.f("ix_requirements_programme_id"), "requirements", ["programme_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_requirements_programme_id"), table_name="requirements")
    op.drop_constraint("fk_requirements_programme_id", "requirements", type_="foreignkey")
    op.drop_column("requirements", "programme_id")
    op.drop_index(op.f("ix_programmes_buyer_id"), table_name="programmes")
    op.drop_table("programmes")
