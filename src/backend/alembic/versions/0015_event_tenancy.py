"""organization and audit attribution on domain events

Revision ID: 0015_event_tenancy
Revises: 0014_access_requests

Additive only. Existing events keep every value they had; organization_id is backfilled where the
aggregate's owner can be determined (requirement and production-lot aggregates) and left NULL
otherwise. NULL-organization events are excluded from tenant activity feeds (fail closed).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_event_tenancy"
down_revision: Union[str, None] = "0014_access_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("domain_events", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("domain_events", sa.Column("actor_id", sa.String(100), nullable=True))
    op.add_column("domain_events", sa.Column("causation_id", sa.Uuid(), nullable=True))
    op.add_column("domain_events", sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("domain_events", sa.Column("idempotency_key", sa.String(300), nullable=True))
    op.create_foreign_key("fk_domain_events_organization_id", "domain_events", "organizations", ["organization_id"], ["id"])
    op.create_index("ix_domain_events_organization_id", "domain_events", ["organization_id"])
    op.create_index("ix_domain_events_org_occurred", "domain_events", ["organization_id", "occurred_at"])
    op.execute(sa.text("""
        UPDATE domain_events SET organization_id = (
            SELECT b.organization_id FROM requirements r JOIN buyers b ON b.id = r.buyer_id
            WHERE r.id = domain_events.aggregate_id)
        WHERE aggregate_type IN ('requirement', 'buyer_requirements') AND organization_id IS NULL
    """))
    op.execute(sa.text("""
        UPDATE domain_events SET organization_id = (
            SELECT f.organization_id FROM production_lots l JOIN farmers f ON f.id = l.farmer_id
            WHERE l.id = domain_events.aggregate_id)
        WHERE aggregate_type IN ('production_lot', 'production_lots') AND organization_id IS NULL
    """))
    op.execute(sa.text("""
        UPDATE domain_events SET organization_id = (
            SELECT f.organization_id FROM farmers f WHERE f.id = domain_events.aggregate_id)
        WHERE aggregate_type = 'farmers' AND organization_id IS NULL
    """))


def downgrade() -> None:
    op.drop_index("ix_domain_events_org_occurred", table_name="domain_events")
    op.drop_index("ix_domain_events_organization_id", table_name="domain_events")
    op.drop_constraint("fk_domain_events_organization_id", "domain_events", type_="foreignkey")
    for column in ("idempotency_key", "schema_version", "causation_id", "actor_id", "organization_id"):
        op.drop_column("domain_events", column)
