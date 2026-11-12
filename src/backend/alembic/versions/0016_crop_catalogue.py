"""configurable crop catalogue; widen crop columns

Revision ID: 0016_crop_catalogue
Revises: 0015_event_tenancy

Earlier migrations created every crop column as a non-native enum holding only "GINGER", which is
VARCHAR(6) on PostgreSQL, so PLANTAIN, CASSAVA, CALLALOO, BREADFRUIT and SWEET_POTATO could not be
stored even though the API accepted them. This migration:

* widens requirements/production_lots/compliance_rules/availability_watches.crop to VARCHAR(64).
  Widening preserves every existing value; nothing is rewritten.
* creates the `crops` catalogue (shared rows have organization_id NULL; organizations may add their own)
  and seeds the shared catalogue with the nine previously supported crops plus SCOTCH_BONNET.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_crop_catalogue"
down_revision: Union[str, None] = "0015_event_tenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CROP_TABLES = ("requirements", "production_lots", "compliance_rules", "availability_watches")
SHARED_CROPS = {
    "BANANA": "Banana", "BREADFRUIT": "Breadfruit", "CALLALOO": "Callaloo", "CASSAVA": "Cassava",
    "GINGER": "Ginger", "MANGO": "Mango", "PLANTAIN": "Plantain", "SCOTCH_BONNET": "Scotch bonnet pepper",
    "SWEET_POTATO": "Sweet potato", "YAM": "Yam",
}


def upgrade() -> None:
    for table in CROP_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("crop", type_=sa.String(64), existing_nullable=False)

    crops = op.create_table(
        "crops",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crops_organization_id", "crops", ["organization_id"])
    op.create_index("uq_crops_org_code", "crops", ["organization_id", "code"], unique=True)
    op.create_index("uq_crops_global_code", "crops", ["code"], unique=True,
                    postgresql_where=sa.text("organization_id IS NULL"), sqlite_where=sa.text("organization_id IS NULL"))
    op.bulk_insert(crops, [{"id": uuid.uuid5(uuid.NAMESPACE_URL, f"korofarm:crop:{code}"), "organization_id": None,
                            "code": code, "name": name, "active": True} for code, name in SHARED_CROPS.items()])


def downgrade() -> None:
    op.drop_index("uq_crops_global_code", table_name="crops")
    op.drop_index("uq_crops_org_code", table_name="crops")
    op.drop_index("ix_crops_organization_id", table_name="crops")
    op.drop_table("crops")
    # Columns are left at VARCHAR(64): narrowing could truncate or reject stored crop codes.
