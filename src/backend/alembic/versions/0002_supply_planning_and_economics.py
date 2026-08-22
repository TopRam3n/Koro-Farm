"""supply planning and economics snapshots

Revision ID: 0002_supply_planning_and_economics
Revises: 0001_initial_foundation
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_supply_planning_and_economics"
down_revision = "0001_initial_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    plan_status = sa.Enum("FINALIZED", name="supplyplanstatus", native_enum=False)
    allocation_role = sa.Enum("COMMITTED", "STANDBY", name="allocationrole", native_enum=False)
    allocation_status = sa.Enum("PROPOSED", "SOLICITED", "ACCEPTED", "COMMITTED", "STANDBY", "ACTIVATED", "LOST", "RELEASED", "CANCELLED", name="allocationstatus", native_enum=False)
    op.create_table(
        "supply_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("planner_version", sa.String(length=50), nullable=False),
        sa.Column("status", plan_status, nullable=False),
        sa.Column("required_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("committed_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("standby_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("unfilled_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("required_quantity_kg > 0", name="ck_plan_required_positive"),
        sa.CheckConstraint("committed_quantity_kg >= 0", name="ck_plan_committed_non_negative"),
        sa.CheckConstraint("standby_quantity_kg >= 0", name="ck_plan_standby_non_negative"),
        sa.CheckConstraint("unfilled_quantity_kg >= 0", name="ck_plan_unfilled_non_negative"),
        sa.CheckConstraint("plan_version > 0", name="ck_plan_version_positive"),
        sa.UniqueConstraint("requirement_id", "plan_version", name="uq_supply_plan_requirement_version"),
    )
    op.create_index("ix_supply_plans_requirement_id", "supply_plans", ["requirement_id"])
    op.create_table(
        "supply_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("supply_plan_id", sa.Uuid(), sa.ForeignKey("supply_plans.id"), nullable=False),
        sa.Column("production_lot_id", sa.Uuid(), sa.ForeignKey("production_lots.id"), nullable=False),
        sa.Column("role", allocation_role, nullable=False), sa.Column("status", allocation_status, nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False), sa.Column("consent_evidence_id", sa.Uuid(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True), sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_allocation_quantity_positive"),
    )
    op.create_index("ix_supply_allocations_requirement_id", "supply_allocations", ["requirement_id"])
    op.create_index("ix_supply_allocations_supply_plan_id", "supply_allocations", ["supply_plan_id"])
    op.create_index("ix_supply_allocations_production_lot_id", "supply_allocations", ["production_lot_id"])
    op.create_table(
        "lot_cost_inputs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_lot_id", sa.Uuid(), sa.ForeignKey("production_lots.id"), nullable=False, unique=True),
        sa.Column("farmgate_price_per_kg_jmd", sa.Numeric(12, 2), nullable=False), sa.Column("pickup_cost_jmd", sa.Numeric(12, 2), nullable=False),
        sa.Column("handling_grading_cost_per_kg_jmd", sa.Numeric(12, 2), nullable=False), sa.Column("packaging_cost_per_kg_jmd", sa.Numeric(12, 2), nullable=False),
        sa.Column("transport_cost_jmd", sa.Numeric(12, 2), nullable=False), sa.Column("expected_rejection_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("farmgate_price_per_kg_jmd >= 0", name="ck_cost_farmgate_non_negative"),
        sa.CheckConstraint("pickup_cost_jmd >= 0", name="ck_cost_pickup_non_negative"),
        sa.CheckConstraint("handling_grading_cost_per_kg_jmd >= 0", name="ck_cost_handling_non_negative"),
        sa.CheckConstraint("packaging_cost_per_kg_jmd >= 0", name="ck_cost_packaging_non_negative"),
        sa.CheckConstraint("transport_cost_jmd >= 0", name="ck_cost_transport_non_negative"),
        sa.CheckConstraint("expected_rejection_pct >= 0 AND expected_rejection_pct <= 1", name="ck_cost_rejection_pct"),
    )
    op.create_table(
        "cost_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("supply_plan_id", sa.Uuid(), sa.ForeignKey("supply_plans.id"), nullable=False, unique=True),
        sa.Column("produce_cost_jmd", sa.Numeric(14, 2), nullable=False), sa.Column("pickup_cost_jmd", sa.Numeric(14, 2), nullable=False),
        sa.Column("handling_cost_jmd", sa.Numeric(14, 2), nullable=False), sa.Column("packaging_cost_jmd", sa.Numeric(14, 2), nullable=False),
        sa.Column("transport_cost_jmd", sa.Numeric(14, 2), nullable=False), sa.Column("expected_rejection_cost_jmd", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_landed_cost_jmd", sa.Numeric(14, 2), nullable=False), sa.Column("landed_cost_per_kg_jmd", sa.Numeric(14, 2), nullable=False),
        sa.Column("calculation_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cost_snapshots")
    op.drop_table("lot_cost_inputs")
    op.drop_table("supply_allocations")
    op.drop_table("supply_plans")
