"""buyer memberships and customer marketplace

Revision ID: 0013_marketplace_roles
Revises: 0012_ingestion
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_marketplace_roles"
down_revision: Union[str, None] = "0012_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_PERMISSIONS = {
    "farmer_supply.report": "Report expected farmer harvest and quality",
    "marketplace.view": "View marketplace availability",
    "order.view": "View customer orders",
    "order.create": "Place a customer order",
    "availability_alert.manage": "Manage produce availability alerts",
}


def _ensure_catalog_row(table: str, columns: str, values: str, parameters: dict, key_column: str, key: str) -> None:
    op.execute(sa.text(
        f"INSERT INTO {table} ({columns}) SELECT {values} WHERE NOT EXISTS "
        f"(SELECT 1 FROM {table} WHERE {key_column} = :key)"
    ).bindparams(**parameters, key=key))


def upgrade() -> None:
    op.add_column("organization_memberships", sa.Column("buyer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_membership_buyer_id", "organization_memberships", "buyers", ["buyer_id"], ["id"])
    op.create_index("ix_organization_memberships_buyer_id", "organization_memberships", ["buyer_id"])

    op.create_table(
        "marketplace_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("production_lot_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_marketplace_order_quantity_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["customer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["production_lot_id"], ["production_lots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "buyer_id", "customer_user_id", "production_lot_id"):
        op.create_index(f"ix_marketplace_orders_{column}", "marketplace_orders", [column])

    op.create_table(
        "availability_watches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("crop", sa.String(20), nullable=False),
        sa.Column("minimum_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("minimum_quantity_kg > 0", name="ck_watch_quantity_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"]),
        sa.ForeignKeyConstraint(["customer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "buyer_id", "customer_user_id"):
        op.create_index(f"ix_availability_watches_{column}", "availability_watches", [column])

    op.create_table(
        "availability_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("watch_id", sa.Uuid(), nullable=False),
        sa.Column("production_lot_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["watch_id"], ["availability_watches.id"]),
        sa.ForeignKeyConstraint(["production_lot_id"], ["production_lots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watch_id", "production_lot_id", name="uq_alert_watch_lot"),
    )
    for column in ("organization_id", "watch_id", "production_lot_id"):
        op.create_index(f"ix_availability_alerts_{column}", "availability_alerts", [column])

    _ensure_catalog_row("roles", "code, name, description, internal_only", ":code, :name, :description, :internal_only",
                        {"code": "BUYER", "name": "Buyer", "description": "KoroFarm buyer/customer role", "internal_only": False}, "code", "BUYER")
    for code, description in NEW_PERMISSIONS.items():
        _ensure_catalog_row("permissions", "code, description", ":code, :description",
                            {"code": code, "description": description}, "code", code)
    role_permissions = {
        "FARMER": ("farmer_supply.report",),
        "BUYER": ("marketplace.view", "order.view", "order.create", "availability_alert.manage"),
    }
    for role, permissions in role_permissions.items():
        for permission in permissions:
            op.execute(sa.text(
                "INSERT INTO role_permissions (role_code, permission_code) "
                "SELECT :role, :permission WHERE NOT EXISTS "
                "(SELECT 1 FROM role_permissions WHERE role_code = :role AND permission_code = :permission)"
            ).bindparams(role=role, permission=permission))


def downgrade() -> None:
    op.drop_table("availability_alerts")
    op.drop_table("availability_watches")
    for column in ("production_lot_id", "customer_user_id", "buyer_id", "organization_id"):
        op.drop_index(f"ix_marketplace_orders_{column}", table_name="marketplace_orders")
    op.drop_table("marketplace_orders")
    op.drop_index("ix_organization_memberships_buyer_id", table_name="organization_memberships")
    op.drop_constraint("fk_membership_buyer_id", "organization_memberships", type_="foreignkey")
    op.drop_column("organization_memberships", "buyer_id")

    for permission in NEW_PERMISSIONS:
        op.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = :permission")
                   .bindparams(permission=permission))
    op.execute(sa.text("DELETE FROM roles WHERE code = 'BUYER'"))
    for permission in NEW_PERMISSIONS:
        op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=permission))
