"""recorded supplier consent; classify legacy consent ids as unsupported

Revision ID: 0018_supplier_consent
Revises: 0017_order_supply_records

Before this revision the planner stored a randomly generated consent_evidence_id on every allocation
and wrote allocations directly as COMMITTED/STANDBY without any supplier acceptance. Those ids are not
evidence. This migration:

* creates supplier_consents (immutable decision records);
* adds supply_allocations.consent_status and classifies every existing allocation that carries a
  consent_evidence_id as UNSUPPORTED_LEGACY. The ids themselves are preserved for history;
* adds holds_reservation (TRUE for existing rows, which did reserve stock), activation conditions,
  authorization expiry and solicitation/response timestamps;
* widens supply_allocations.status to VARCHAR(20) for the DECLINED/WITHDRAWN/EXPIRED states.

Nothing is deleted or rewritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_supplier_consent"
down_revision: Union[str, None] = "0017_order_supply_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("supply_allocations") as batch:
        batch.alter_column("status", type_=sa.String(20), existing_nullable=False)
        batch.add_column(sa.Column("consent_status", sa.String(30), nullable=False, server_default="NONE"))
        batch.add_column(sa.Column("holds_reservation", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("activation_conditions", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("authorization_valid_until", sa.Date(), nullable=True))
        batch.add_column(sa.Column("solicited_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE supply_allocations SET consent_status = 'UNSUPPORTED_LEGACY' WHERE consent_evidence_id IS NOT NULL"))
    # Proposed/solicited rows written before this revision without a reservation do not hold stock.
    op.execute(sa.text("UPDATE supply_allocations SET holds_reservation = false WHERE status = 'PROPOSED'"))

    op.create_table(
        "supplier_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("allocation_id", sa.Uuid(), sa.ForeignKey("supply_allocations.id"), nullable=False),
        sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("production_lot_id", sa.Uuid(), sa.ForeignKey("production_lots.id"), nullable=False),
        sa.Column("consent_type", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("attestation_method", sa.String(100), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("activation_conditions", sa.String(1000), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_consent_quantity_positive"),
    )
    op.create_index("ix_supplier_consents_organization_id", "supplier_consents", ["organization_id"])
    op.create_index("ix_supplier_consents_allocation_id", "supplier_consents", ["allocation_id"])
    op.create_index("ix_supplier_consents_farmer_id", "supplier_consents", ["farmer_id"])


def downgrade() -> None:
    op.drop_table("supplier_consents")
    with op.batch_alter_table("supply_allocations") as batch:
        for column in ("responded_at", "solicited_at", "authorization_valid_until", "activation_conditions",
                       "holds_reservation", "consent_status"):
            batch.drop_column(column)
