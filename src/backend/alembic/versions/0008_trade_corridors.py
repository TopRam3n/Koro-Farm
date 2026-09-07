"""configurable inter-island trade corridors

Revision ID: 0008_trade_corridors
Revises: 0007_buyer_order_changes
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_trade_corridors"
down_revision = "0007_buyer_order_changes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("trade_corridors", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("name", sa.String(200), nullable=False, unique=True), sa.Column("origin_country", sa.String(100), nullable=False), sa.Column("destination_country", sa.String(100), nullable=False), sa.Column("transport_mode", sa.String(40), nullable=False), sa.Column("default_dispatch_lead_hours", sa.Integer(), nullable=False), sa.Column("export_node_id", sa.Uuid(), sa.ForeignKey("fulfilment_nodes.id")), sa.Column("import_node_id", sa.Uuid(), sa.ForeignKey("fulfilment_nodes.id")), sa.Column("active", sa.Boolean(), nullable=False), sa.Column("last_verified_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.add_column("requirements", sa.Column("trade_corridor_id", sa.Uuid(), sa.ForeignKey("trade_corridors.id")))
    op.create_index("ix_requirements_trade_corridor_id", "requirements", ["trade_corridor_id"])

def downgrade() -> None:
    op.drop_index("ix_requirements_trade_corridor_id", table_name="requirements"); op.drop_column("requirements", "trade_corridor_id"); op.drop_table("trade_corridors")
