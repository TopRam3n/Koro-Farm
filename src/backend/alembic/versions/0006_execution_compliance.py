"""shipments, reconciliation and verified compliance rules

Revision ID: 0006_execution_compliance
Revises: 0005_received_sublots
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_execution_compliance"
down_revision = "0005_received_sublots"
branch_labels = None
depends_on = None

def upgrade() -> None:
    shipment_status = sa.Enum("OPEN", "DISPATCHED", "DELIVERED", name="shipmentstatus", native_enum=False)
    crop = sa.Enum("GINGER", name="crop", native_enum=False)
    op.create_table("shipments", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False), sa.Column("fulfilment_node_id", sa.Uuid(), sa.ForeignKey("fulfilment_nodes.id"), nullable=False), sa.Column("reference", sa.String(80), nullable=False, unique=True), sa.Column("status", shipment_status, nullable=False), sa.Column("dispatched_at", sa.DateTime(timezone=True)), sa.Column("dispatch_evidence_reference", sa.String(500)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_shipments_requirement_id", "shipments", ["requirement_id"])
    op.create_table("shipment_sublots", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("shipment_id", sa.Uuid(), sa.ForeignKey("shipments.id"), nullable=False), sa.Column("received_sublot_id", sa.Uuid(), sa.ForeignKey("received_sublots.id"), nullable=False, unique=True), sa.Column("accepted_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.UniqueConstraint("shipment_id", "received_sublot_id", name="uq_shipment_sublot"))
    op.create_index("ix_shipment_sublots_shipment_id", "shipment_sublots", ["shipment_id"])
    op.create_table("deliveries", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("shipment_id", sa.Uuid(), sa.ForeignKey("shipments.id"), nullable=False, unique=True), sa.Column("delivered_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False), sa.Column("delivery_evidence_reference", sa.String(500)), sa.Column("buyer_confirmed", sa.Boolean(), nullable=False), sa.Column("buyer_confirmation_evidence", sa.String(500)), sa.CheckConstraint("delivered_quantity_kg >= 0", name="ck_delivery_non_negative"))
    op.create_table("requirement_reconciliations", sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), primary_key=True), sa.Column("committed_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("delivered_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("accepted_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("quantity_variance_kg", sa.Numeric(12, 3), nullable=False), sa.Column("accepted_fulfilment_rate_pct", sa.Numeric(7, 3), nullable=False), sa.Column("on_time", sa.Boolean()), sa.Column("buyer_confirmed", sa.Boolean(), nullable=False), sa.Column("dispute_status", sa.String(80)), sa.Column("verification_evidence_reference", sa.String(500)), sa.Column("reconciled_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("compliance_rules", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("origin", sa.String(100), nullable=False), sa.Column("destination", sa.String(100), nullable=False), sa.Column("crop", crop, nullable=False), sa.Column("product_form", sa.String(80), nullable=False), sa.Column("rule_name", sa.String(200), nullable=False), sa.Column("issuing_body", sa.String(200), nullable=False), sa.Column("description", sa.String(1000), nullable=False), sa.Column("required_before", sa.String(100), nullable=False), sa.Column("lead_time", sa.String(100), nullable=False), sa.Column("effective_from", sa.Date(), nullable=False), sa.Column("effective_until", sa.Date()), sa.Column("source_citation", sa.String(1000), nullable=False), sa.Column("source_version", sa.String(100), nullable=False), sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False), sa.Column("verified_by", sa.String(200), nullable=False))

def downgrade() -> None:
    op.drop_table("compliance_rules"); op.drop_table("requirement_reconciliations"); op.drop_table("deliveries"); op.drop_table("shipment_sublots"); op.drop_table("shipments")
