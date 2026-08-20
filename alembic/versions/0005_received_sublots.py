"""physical received sublots

Revision ID: 0005_received_sublots
Revises: 0004_supply_risk_indicators
"""
from alembic import op
import sqlalchemy as sa
revision = "0005_received_sublots"; down_revision = "0004_supply_risk_indicators"; branch_labels = None; depends_on = None
def upgrade() -> None:
    status = sa.Enum("RECEIVED", "PENDING_INSPECTION", "ACCEPTED", "PARTIALLY_ACCEPTED", "REJECTED", name="inspectionstatus", native_enum=False); grade = sa.Enum("A", "B", name="grade", native_enum=False)
    op.create_table("received_sublots", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("allocation_id", sa.Uuid(), sa.ForeignKey("supply_allocations.id"), nullable=False), sa.Column("fulfilment_node_id", sa.Uuid(), sa.ForeignKey("fulfilment_nodes.id"), nullable=False), sa.Column("received_quantity_kg", sa.Numeric(12,3), nullable=False), sa.Column("accepted_quantity_kg", sa.Numeric(12,3), nullable=False), sa.Column("rejected_quantity_kg", sa.Numeric(12,3), nullable=False), sa.Column("assigned_grade", grade), sa.Column("inspection_status", status, nullable=False), sa.Column("rejection_reason", sa.String(80)), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False), sa.Column("graded_at", sa.DateTime(timezone=True)), sa.Column("receipt_evidence_reference", sa.String(500)), sa.Column("inspection_evidence_reference", sa.String(500)), sa.Column("version", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.CheckConstraint("received_quantity_kg >= 0", name="ck_sublot_received_non_negative"), sa.CheckConstraint("accepted_quantity_kg >= 0", name="ck_sublot_accepted_non_negative"), sa.CheckConstraint("rejected_quantity_kg >= 0", name="ck_sublot_rejected_non_negative"), sa.CheckConstraint("accepted_quantity_kg + rejected_quantity_kg <= received_quantity_kg", name="ck_sublot_accounted_within_received"))
    op.create_index("ix_received_sublots_allocation_id", "received_sublots", ["allocation_id"]); op.create_index("ix_received_sublots_fulfilment_node_id", "received_sublots", ["fulfilment_node_id"])
def downgrade() -> None: op.drop_table("received_sublots")
