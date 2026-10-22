"""Register existing demo farms, crop portfolios and history tables.

Revision ID: 0015_farmer_history
Revises: 0014_access_requests

Safe for environments where tables were already created in Supabase.
Does not remove historical records on downgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_farmer_history"
down_revision = "0014_access_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())
    if "farms" not in existing:
        op.create_table("farms", sa.Column("id", sa.Uuid(), primary_key=True),
                        sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id"), nullable=False),
                        sa.Column("name", sa.String(200), nullable=False),
                        sa.Column("parish", sa.String(100), nullable=False),
                        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
                        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                        sa.UniqueConstraint("farmer_id", "name"))
    if "farmer_crops" not in existing:
        op.create_table("farmer_crops", sa.Column("id", sa.Uuid(), primary_key=True),
                        sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id"), nullable=False),
                        sa.Column("crop", sa.String(100), nullable=False),
                        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
                        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                        sa.UniqueConstraint("farmer_id", "crop"))
    if "historical_production" not in existing:
        op.create_table("historical_production", sa.Column("id", sa.Uuid(), primary_key=True),
                        sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id"), nullable=False),
                        sa.Column("crop", sa.String(100), nullable=False),
                        sa.Column("production_year", sa.Integer(), nullable=False),
                        sa.Column("production_quarter", sa.Integer(), nullable=False),
                        sa.Column("production_kg", sa.Numeric(18, 3), nullable=False),
                        sa.Column("data_source", sa.String(100), nullable=False, server_default="KOROFARM_DEMO"),
                        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.true()),
                        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                        sa.CheckConstraint("production_year BETWEEN 2000 AND 2100", name="valid_production_year"),
                        sa.CheckConstraint("production_quarter BETWEEN 1 AND 4", name="valid_production_quarter"),
                        sa.CheckConstraint("production_kg >= 0", name="valid_production_quantity"),
                        sa.UniqueConstraint("farmer_id", "crop", "production_year", "production_quarter", "data_source"))
    for table in ("farms", "farmer_crops", "historical_production"):
        # Postgres-specific RLS; client API access is denied without policies.
        if conn.dialect.name == "postgresql":
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    if "historical_production" not in existing:
        op.create_index("idx_historical_production_farmer", "historical_production", ["farmer_id"])
        op.create_index("idx_historical_production_year", "historical_production", ["production_year", "production_quarter"])


def downgrade() -> None:
    # Never silently destroy production data that predates this migration.
    raise RuntimeError("Downgrade blocked: historical production tables may contain imported data")
