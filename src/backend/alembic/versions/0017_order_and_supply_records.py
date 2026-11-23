"""order terms, buyer/supplier records and lot provenance

Revision ID: 0017_order_supply_records
Revises: 0016_crop_catalogue

Additive only: new nullable or defaulted columns.

Existing production lots get capacity_verification = 'UNSPECIFIED' because nothing records whether
their capacity was ever verified; new coordinator-entered lots are 'DECLARED'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_order_supply_records"
down_revision: Union[str, None] = "0016_crop_catalogue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    with op.batch_alter_table("buyers") as batch:
        batch.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("notes", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW))
    with op.batch_alter_table("farmers") as batch:
        batch.add_column(sa.Column("contact_phone", sa.String(50), nullable=True))
        batch.add_column(sa.Column("notes", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW))
    with op.batch_alter_table("production_lots") as batch:
        batch.add_column(sa.Column("capacity_verification", sa.String(20), nullable=False, server_default="UNSPECIFIED"))
        batch.add_column(sa.Column("provenance_source", sa.String(200), nullable=True))
        batch.add_column(sa.Column("attestation_method", sa.String(100), nullable=True))
        batch.add_column(sa.Column("evidence_reference", sa.String(500), nullable=True))
        batch.add_column(sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("declared_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("requirements") as batch:
        batch.add_column(sa.Column("product_form", sa.String(80), nullable=True))
        batch.add_column(sa.Column("quantity_unit", sa.String(10), nullable=False, server_default="kg"))
        batch.add_column(sa.Column("origin", sa.String(200), nullable=True))
        batch.add_column(sa.Column("destination", sa.String(200), nullable=True))
        batch.add_column(sa.Column("delivery_terms", sa.String(200), nullable=True))
        batch.add_column(sa.Column("currency", sa.String(3), nullable=True))
        batch.add_column(sa.Column("notes", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cancellation_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    for table, columns in (
        ("requirements", ("cancellation_reason", "cancelled_at", "created_by_user_id", "notes", "currency",
                          "delivery_terms", "destination", "origin", "quantity_unit", "product_form")),
        ("production_lots", ("declared_at", "recorded_by_user_id", "evidence_reference", "attestation_method",
                             "provenance_source", "capacity_verification")),
        ("farmers", ("updated_at", "version", "created_by_user_id", "notes", "contact_phone")),
        ("buyers", ("updated_at", "version", "created_by_user_id", "notes", "active")),
    ):
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)
