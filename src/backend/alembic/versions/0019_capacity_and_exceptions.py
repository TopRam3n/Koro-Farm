"""supplier capacity reports, supply exceptions, response deadlines, outbox processing state

Revision ID: 0019_capacity_exceptions
Revises: 0018_supplier_consent

Additive only.
* capacity_reports: immutable record of every supplier capacity report.
* production_lots.reported_capacity_kg / capacity_reported_at: the latest reported capacity, kept apart from
  reserved stock so commitments are preserved and exposure is reported separately.
* supply_exceptions: actionable exceptions; a partial unique index makes an OPEN dedupe key unique, so
  repeated or concurrent detection cannot open duplicates.
* supply_allocations.response_due_at / reminder_sent_at: supplier response deadlines and reminders.
* outbox_messages: processing state for the exception worker. Existing rows are marked processed so that
  historical events are not replayed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_capacity_exceptions"
down_revision: Union[str, None] = "0018_supplier_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("production_lots") as batch:
        batch.add_column(sa.Column("reported_capacity_kg", sa.Numeric(12, 3), nullable=True))
        batch.add_column(sa.Column("capacity_reported_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "capacity_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("production_lot_id", sa.Uuid(), sa.ForeignKey("production_lots.id"), nullable=False),
        sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id"), nullable=False),
        sa.Column("reported_capacity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("previous_reported_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column("committed_at_report_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("original_source", sa.String(200), nullable=False),
        sa.Column("attestation_method", sa.String(100), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("reported_capacity_kg >= 0", name="ck_capacity_report_non_negative"),
    )
    op.create_index("ix_capacity_reports_lot", "capacity_reports", ["production_lot_id", "effective_at"])
    op.create_index("ix_capacity_reports_organization_id", "capacity_reports", ["organization_id"])

    op.create_table(
        "supply_exceptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("shortfall_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolution", sa.String(500), nullable=True),
        sa.CheckConstraint("shortfall_kg >= 0", name="ck_exception_shortfall_non_negative"),
    )
    op.create_index("ix_supply_exceptions_org_status", "supply_exceptions", ["organization_id", "status"])
    op.create_index("ix_supply_exceptions_requirement_id", "supply_exceptions", ["requirement_id"])
    op.create_index("uq_supply_exceptions_open_dedupe", "supply_exceptions", ["dedupe_key"], unique=True,
                    postgresql_where=sa.text("status = 'OPEN'"), sqlite_where=sa.text("status = 'OPEN'"))

    with op.batch_alter_table("supply_allocations") as batch:
        batch.add_column(sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("outbox_messages") as batch:
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"))
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_error", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE outbox_messages SET status = 'PROCESSED', processed_at = CURRENT_TIMESTAMP"))
    op.create_index("ix_outbox_messages_pending", "outbox_messages", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_pending", table_name="outbox_messages")
    with op.batch_alter_table("outbox_messages") as batch:
        for column in ("available_at", "processed_at", "last_error", "attempts", "status"):
            batch.drop_column(column)
    with op.batch_alter_table("supply_allocations") as batch:
        batch.drop_column("reminder_sent_at")
        batch.drop_column("response_due_at")
    op.drop_table("supply_exceptions")
    op.drop_table("capacity_reports")
    with op.batch_alter_table("production_lots") as batch:
        batch.drop_column("capacity_reported_at")
        batch.drop_column("reported_capacity_kg")
