"""identity, organizations, memberships, roles and permissions

Revision ID: 0010_identity_access
Revises: 0009_programmes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.backend.app.identity.domain.permissions import PermissionCode, ROLE_PERMISSIONS, RoleCode

revision: str = "0010_identity_access"
down_revision: Union[str, None] = "0009_programmes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_active_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("email"),
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("internal_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(30), nullable=False),
        sa.Column("permission_code", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["role_code"], ["roles.code"]),
        sa.ForeignKeyConstraint(["permission_code"], ["permissions.code"]),
        sa.PrimaryKeyConstraint("role_code", "permission_code"),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(30), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("farmer_id", sa.Uuid()),
        sa.Column("invited_by", sa.Uuid()),
        sa.Column("invitation_token_hash", sa.String(64)),
        sa.Column("invited_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["role_code"], ["roles.code"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_organization"),
        sa.UniqueConstraint("invitation_token_hash"),
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    role_table = sa.table(
        "roles", sa.column("code", sa.String()), sa.column("name", sa.String()),
        sa.column("description", sa.String()), sa.column("internal_only", sa.Boolean()),
    )
    permission_table = sa.table(
        "permissions", sa.column("code", sa.String()), sa.column("description", sa.String()),
    )
    role_permission_table = sa.table(
        "role_permissions", sa.column("role_code", sa.String()), sa.column("permission_code", sa.String()),
    )
    op.bulk_insert(role_table, [{"code": role.value, "name": role.value.replace("_", " ").title(),
                                 "description": f"KoroFarm {role.value.lower()} role",
                                 "internal_only": role == RoleCode.PLATFORM_ADMIN} for role in RoleCode])
    op.bulk_insert(permission_table, [{"code": permission.value,
                                       "description": permission.value.replace(".", " ").title()}
                                      for permission in PermissionCode])
    op.bulk_insert(role_permission_table, [
        {"role_code": role.value, "permission_code": permission.value}
        for role, permissions in ROLE_PERMISSIONS.items() for permission in permissions
    ])


def downgrade() -> None:
    op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
    op.drop_index("ix_organization_memberships_user_id", table_name="organization_memberships")
    op.drop_table("organization_memberships")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("organizations")
