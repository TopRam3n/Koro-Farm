"""Marketplace receipts and inspections, independent of legacy allocations.

Revision ID: 0015_marketplace_fulfilment
Revises: 0014_access_requests

Prerequisite: Phase 2's farmer_offers table is already installed. That table
is introduced by the earlier Phase 2 SQL migration, not Alembic's 0014.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_marketplace_fulfilment"
down_revision: Union[str, None] = "0014_access_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("farmer_offers"):
        raise RuntimeError("Marketplace Phase 2 farmer_offers table is missing. Apply the prior Phase 2 SQL migration before this Alembic migration.")
    op.create_table(
        "marketplace_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("offer_id", sa.Uuid(), sa.ForeignKey("farmer_offers.id"), nullable=False),
        sa.Column("fulfilment_node_id", sa.Uuid(), sa.ForeignKey("fulfilment_nodes.id"), nullable=False),
        sa.Column("received_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_evidence_reference", sa.String(500), nullable=False),
        sa.Column("receipt_key", sa.String(150), nullable=False),
        sa.Column("received_by", sa.Uuid(), nullable=False),
        sa.Column("inspection_status", sa.String(30), nullable=False),
        sa.Column("accepted_quantity_kg", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("rejected_quantity_kg", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("assigned_grade", sa.String(10), nullable=True),
        sa.Column("rejection_reason", sa.String(200), nullable=True),
        sa.Column("inspection_evidence_reference", sa.String(500), nullable=True),
        sa.Column("inspection_key", sa.String(150), nullable=True),
        sa.Column("inspected_by", sa.Uuid(), nullable=True),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("received_quantity_kg > 0", name="ck_marketplace_receipt_positive"),
        sa.CheckConstraint("accepted_quantity_kg >= 0", name="ck_marketplace_receipt_accepted_nonnegative"),
        sa.CheckConstraint("rejected_quantity_kg >= 0", name="ck_marketplace_receipt_rejected_nonnegative"),
        sa.CheckConstraint("accepted_quantity_kg + rejected_quantity_kg <= received_quantity_kg", name="ck_marketplace_receipt_graded_within_received"),
        sa.UniqueConstraint("organization_id", "receipt_key", name="uq_marketplace_receipt_command"),
        sa.UniqueConstraint("organization_id", "inspection_key", name="uq_marketplace_inspection_command"),
    )
    op.create_index("ix_marketplace_receipts_organization_id", "marketplace_receipts", ["organization_id"])
    op.create_index("ix_marketplace_receipts_offer_id", "marketplace_receipts", ["offer_id"])
    op.create_index("ix_marketplace_receipts_fulfilment_node_id", "marketplace_receipts", ["fulfilment_node_id"])


def downgrade() -> None:
    op.drop_index("ix_marketplace_receipts_fulfilment_node_id", table_name="marketplace_receipts")
    op.drop_index("ix_marketplace_receipts_offer_id", table_name="marketplace_receipts")
    op.drop_index("ix_marketplace_receipts_organization_id", table_name="marketplace_receipts")
    op.drop_table("marketplace_receipts")
