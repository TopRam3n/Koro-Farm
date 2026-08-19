"""initial foundation tables

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    crop = sa.Enum("GINGER", name="crop", native_enum=False)
    grade = sa.Enum("A", "B", name="grade", native_enum=False)
    lifecycle = sa.Enum("DRAFT", "PLANNING", "ACTIVE", "IN_FULFILMENT", "RECONCILED", "CLOSED", "CANCELLED", name="requirementlifecyclestatus", native_enum=False)
    health = sa.Enum("UNPLANNED", "COVERED", "AT_RISK", "RECOVERING", "ESCALATION_REQUIRED", name="supplyhealth", native_enum=False)
    confidence = sa.Enum("LOW", "MEDIUM", "HIGH", name="availabilityconfidence", native_enum=False)
    lot_status = sa.Enum("AVAILABLE", "UNAVAILABLE", "EXHAUSTED", name="productionlotstatus", native_enum=False)

    op.create_table("buyers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("buyer_type", sa.String(length=80), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("farmers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parish", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("fulfilment_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("node_type", sa.String(length=80), nullable=False),
        sa.Column("parish", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("requirements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("buyer_id", sa.Uuid(), sa.ForeignKey("buyers.id"), nullable=False),
        sa.Column("crop", crop, nullable=False), sa.Column("grade", grade, nullable=False),
        sa.Column("required_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("delivery_window_start", sa.Date(), nullable=False), sa.Column("delivery_window_end", sa.Date(), nullable=False),
        sa.Column("lifecycle_status", lifecycle, nullable=False), sa.Column("supply_health", health, nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("required_quantity_kg > 0", name="ck_requirement_quantity_positive"),
    )
    op.create_index("ix_requirements_buyer_id", "requirements", ["buyer_id"])
    op.create_table("production_lots",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("crop", crop, nullable=False), sa.Column("harvest_start", sa.Date(), nullable=False), sa.Column("harvest_end", sa.Date(), nullable=False),
        sa.Column("expected_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("available_quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("reserved_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("quality_grade_estimate", grade, nullable=False), sa.Column("availability_confidence", confidence, nullable=False),
        sa.Column("parish", sa.String(length=100), nullable=False), sa.Column("status", lot_status, nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("expected_quantity_kg >= 0", name="ck_lot_expected_non_negative"),
        sa.CheckConstraint("available_quantity_kg >= 0", name="ck_lot_available_non_negative"),
        sa.CheckConstraint("reserved_quantity_kg >= 0", name="ck_lot_reserved_non_negative"),
        sa.CheckConstraint("reserved_quantity_kg <= available_quantity_kg", name="ck_lot_reserved_within_available"),
        sa.CheckConstraint("harvest_end >= harvest_start", name="ck_lot_valid_harvest_window"),
    )
    op.create_index("ix_production_lots_farmer_id", "production_lots", ["farmer_id"])


def downgrade() -> None:
    op.drop_table("production_lots")
    op.drop_table("requirements")
    op.drop_table("fulfilment_nodes")
    op.drop_table("farmers")
    op.drop_table("buyers")
