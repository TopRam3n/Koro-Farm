"""outbound notifications and consent to be contacted (R1 WP5, M3)

Revision ID: 0028_notifications_consent
Revises: 0027_supabase_data_api_hardening

Additive: three new tables, nothing existing is changed.
* contact_consents: append-only consent (or withdrawal) per subject, channel and address, with purposes, wording
  version and how it was given.
* notifications: one message per (domain event, template, recipient), with its status. No address is stored.
* notification_status_events: every status change.
On a Supabase project (client roles present) the new tables get row-level security, matching 0026: the Data API roles
hold no privileges on them (0026/0027 default privileges) and see no rows even if a grant reappears.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_notifications_consent"
down_revision: Union[str, None] = "0027_supabase_data_api_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("contact_consents", "notifications", "notification_status_events")

ROW_LEVEL_SECURITY = """
do $$
declare
    item text;
begin
    if not exists (select 1 from pg_roles where rolname in ('anon', 'authenticated', 'service_role')) then
        return;
    end if;
    foreach item in array array['contact_consents', 'notifications', 'notification_status_events'] loop
        execute format('alter table public.%I enable row level security', item);
    end loop;
end
$$;
"""


def upgrade() -> None:
    op.create_table(
        "contact_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subject_type", sa.String(20), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("purposes", sa.JSON(), nullable=False),
        sa.Column("wording_version", sa.String(40), nullable=False),
        sa.Column("how_given", sa.String(200), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("contact_consents.id"), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("subject_type in ('FARMER', 'BUYER')", name="ck_contact_consent_subject_type"),
        sa.CheckConstraint("channel in ('SMS', 'WHATSAPP', 'EMAIL')", name="ck_contact_consent_channel"),
        sa.CheckConstraint("state in ('GRANTED', 'WITHDRAWN')", name="ck_contact_consent_state"),
    )
    op.create_index("ix_contact_consents_organization_id", "contact_consents", ["organization_id"])
    op.create_index("ix_contact_consents_subject_id", "contact_consents", ["subject_id"])
    op.create_index("ix_contact_consents_current", "contact_consents", ["organization_id", "subject_type", "subject_id", "channel", "created_at"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), sa.ForeignKey("domain_events.id"), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=True),
        sa.Column("template_key", sa.String(60), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("recipient_type", sa.String(20), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=True),
        sa.Column("consent_id", sa.Uuid(), sa.ForeignKey("contact_consents.id"), nullable=True),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_event_id", "template_key", "recipient_type", "recipient_id",
                            name="uq_notification_per_event_recipient"),
        sa.CheckConstraint("attempts >= 0", name="ck_notification_attempts"),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_source_event_id", "notifications", ["source_event_id"])
    op.create_index("ix_notifications_requirement_id", "notifications", ["requirement_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index("ix_notifications_due", "notifications", ["status", "next_attempt_at"])
    op.create_table(
        "notification_status_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("notification_id", sa.Uuid(), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notification_status_events_notification_id", "notification_status_events", ["notification_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(ROW_LEVEL_SECURITY)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
