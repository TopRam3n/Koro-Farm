"""buyer-caused requirement changes

Revision ID: 0007_buyer_order_changes
Revises: 0006_execution_compliance
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_buyer_order_changes"
down_revision = "0006_execution_compliance"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("buyer_order_changes", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False), sa.Column("previous_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("new_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("reason", sa.String(500), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_buyer_order_changes_requirement_id", "buyer_order_changes", ["requirement_id"])

def downgrade() -> None:
    op.drop_table("buyer_order_changes")
