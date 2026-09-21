"""channel-neutral ingestion and provenance

Revision ID: 0012_ingestion
Revises: 0011_org_ownership
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_ingestion"
down_revision: Union[str, None] = "0011_org_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_records",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False), sa.Column("external_reference", sa.String(200), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()), sa.Column("farmer_id", sa.Uuid()),
        sa.Column("target_entity_type", sa.String(80), nullable=False), sa.Column("target_entity_id", sa.Uuid()),
        sa.Column("payload_schema", sa.String(100), nullable=False), sa.Column("payload_version", sa.String(30), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False), sa.Column("validation_result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("domain_command", sa.String(120)),
        sa.Column("resulting_event_id", sa.Uuid()), sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["resulting_event_id"], ["domain_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "channel", "external_reference", name="uq_ingestion_external_reference"),
    )
    op.create_index("ix_ingestion_records_organization_id", "ingestion_records", ["organization_id"])
    op.create_index("ix_ingestion_records_target_entity_id", "ingestion_records", ["target_entity_id"])
    op.create_index("ix_ingestion_records_correlation_id", "ingestion_records", ["correlation_id"])
    op.create_table(
        "secure_action_links",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("farmer_id", sa.Uuid(), nullable=False), sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("target_entity_type", sa.String(80), nullable=False), sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False), sa.Column("request_reference", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_secure_action_links_organization_id", "secure_action_links", ["organization_id"])
    op.create_index("ix_secure_action_links_farmer_id", "secure_action_links", ["farmer_id"])
    op.create_table(
        "operational_observations",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_record_id", sa.Uuid(), nullable=False),
        sa.Column("target_entity_type", sa.String(80), nullable=False), sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False), sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False), sa.Column("source_actor", sa.String(200), nullable=False),
        sa.Column("source_channel", sa.String(30), nullable=False), sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)), sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("verification_method", sa.String(200)), sa.Column("freshness_status", sa.String(20), nullable=False),
        sa.Column("freshness_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supporting_evidence_reference", sa.String(500)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["ingestion_record_id"], ["ingestion_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operational_observations_organization_id", "operational_observations", ["organization_id"])
    op.create_index("ix_operational_observations_target_entity_id", "operational_observations", ["target_entity_id"])
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("farmer_id", sa.Uuid(), nullable=False), sa.Column("secure_action_link_id", sa.Uuid()),
        sa.Column("intent", sa.String(80), nullable=False), sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False), sa.Column("provider_reference", sa.String(200)),
        sa.Column("delivery_state", sa.String(40), nullable=False), sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.ForeignKeyConstraint(["secure_action_link_id"], ["secure_action_links.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_messages_organization_id", "outbound_messages", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_outbound_messages_organization_id", table_name="outbound_messages")
    op.drop_table("outbound_messages")
    op.drop_index("ix_operational_observations_target_entity_id", table_name="operational_observations")
    op.drop_index("ix_operational_observations_organization_id", table_name="operational_observations")
    op.drop_table("operational_observations")
    op.drop_index("ix_secure_action_links_farmer_id", table_name="secure_action_links")
    op.drop_index("ix_secure_action_links_organization_id", table_name="secure_action_links")
    op.drop_table("secure_action_links")
    op.drop_index("ix_ingestion_records_correlation_id", table_name="ingestion_records")
    op.drop_index("ix_ingestion_records_target_entity_id", table_name="ingestion_records")
    op.drop_index("ix_ingestion_records_organization_id", table_name="ingestion_records")
    op.drop_table("ingestion_records")
