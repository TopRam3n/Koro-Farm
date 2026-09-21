"""organization ownership for domain roots

Revision ID: 0011_org_ownership
Revises: 0010_identity_access
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_org_ownership"
down_revision: Union[str, None] = "0010_identity_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEMO_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000900"
OWNED_TABLES = ("buyers", "farmers", "fulfilment_nodes", "compliance_rules", "trade_corridors")


def upgrade() -> None:
    organizations = sa.table(
        "organizations", sa.column("id", sa.Uuid()), sa.column("name", sa.String()),
        sa.column("slug", sa.String()), sa.column("active", sa.Boolean()),
    )
    op.bulk_insert(organizations, [{"id": DEMO_ORGANIZATION_ID, "name": "KoroFarm Demo Organization",
                                    "slug": "korofarm-demo", "active": True}])
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("organization_id", sa.Uuid(), nullable=True))
        op.execute(sa.text(f'UPDATE "{table}" SET organization_id = :organization_id').bindparams(
            organization_id=DEMO_ORGANIZATION_ID
        ))
        op.alter_column(table, "organization_id", nullable=False)
        op.create_foreign_key(f"fk_{table}_organization_id", table, "organizations", ["organization_id"], ["id"])
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])


def downgrade() -> None:
    for table in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
