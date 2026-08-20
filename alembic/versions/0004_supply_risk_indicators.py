"""immutable deterministic supply risk indicators

Revision ID: 0004_supply_risk_indicators
Revises: 0003_supply_assurance_audit
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_supply_risk_indicators"
down_revision = "0003_supply_assurance_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    risk_label = sa.Enum("LOW", "MEDIUM", "HIGH", name="risklabel", native_enum=False)
    op.create_table("risk_snapshots", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("supply_plan_id", sa.Uuid(), sa.ForeignKey("supply_plans.id"), nullable=False, unique=True), sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("committed_farmer_count", sa.Integer(), nullable=False), sa.Column("standby_farmer_count", sa.Integer(), nullable=False),
        sa.Column("committed_parish_count", sa.Integer(), nullable=False), sa.Column("standby_parish_count", sa.Integer(), nullable=False),
        sa.Column("largest_farmer_share_pct", sa.Numeric(12,3), nullable=False), sa.Column("largest_parish_share_pct", sa.Numeric(12,3), nullable=False),
        sa.Column("standby_coverage_pct", sa.Numeric(12,3), nullable=False), sa.Column("replacement_depth_kg", sa.Numeric(12,3), nullable=False), sa.Column("average_availability_confidence", sa.Numeric(12,3), nullable=False),
        sa.Column("committed_quantity_kg", sa.Numeric(12,3), nullable=False), sa.Column("standby_quantity_kg", sa.Numeric(12,3), nullable=False), sa.Column("required_quantity_kg", sa.Numeric(12,3), nullable=False),
        sa.Column("risk_label", risk_label, nullable=False), sa.Column("rules_triggered", sa.JSON(), nullable=False), sa.Column("calculation_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_risk_snapshots_requirement_id", "risk_snapshots", ["requirement_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_snapshots_requirement_id", table_name="risk_snapshots")
    op.drop_table("risk_snapshots")
