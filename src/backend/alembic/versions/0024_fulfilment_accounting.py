"""fulfilment accounting: reservation release, lot re-verification, receipt adjustments, buyer confirmations,
versioned reconciliation, disputes, audit flags, stock-ledger findings; WP4 role policy

Revision ID: 0024_fulfilment_accounting
Revises: 0023_model_calls_and_leases

Non-destructive. Nothing is deleted or rewritten; legacy rows are preserved and copied forward.
* supply_allocations.released_quantity_kg: reservation released without rewriting the original commitment.
* production_lots: re-verification flag and reason, verified viable_until, withdrawal.
* requirements.lifecycle_status widened to 30 for COMPLETED / CLOSED_WITH_VARIANCE.
* received_sublots: ADJUSTMENT rows (signed corrections linked to their receipt); the non-negative checks apply to
  RECEIPT rows only.
* shipments: references unique per fulfilment site instead of globally (no cross-tenant collision); CANCELLED.
  On SQLite the old unnamed global unique cannot be dropped by name and is kept (stricter, development only).
* deliveries.recorded_by_user_id; new delivery_adjustments, buyer_confirmations, reconciliation_records, disputes,
  dispute_resolutions, audit_flags, stock_ledger_findings.
* recovery_tasks.purpose / request; recovery_approval_policies.commitment_release_without_supplier_consent (false).
* Backfill: each legacy requirement_reconciliations row becomes reconciliation_records version 1 (legacy=true);
  each delivery with the old buyer_confirmed flag gets a LEGACY_UNQUANTIFIED confirmation with no quantity (0), so
  it is never counted as quantified buyer confirmation. The legacy tables and columns stay as they were.
* Informational permission rows for the WP4 role policy (authorization reads identity/domain/permissions.py).
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0024_fulfilment_accounting"
down_revision: Union[str, None] = "0023_model_calls_and_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = ["fulfilment_site.manage", "trade.reconcile", "trade.accept_variance", "buyer_confirmation.relay",
                   "delivery.confirm_own", "dispute.raise", "audit.flag"]
GRANTS = [
    ("ORGANIZATION_ADMIN", "trade.accept_variance"), ("ORGANIZATION_ADMIN", "fulfilment_site.manage"),
    ("ORGANIZATION_ADMIN", "audit.flag"),
    ("PROCUREMENT_MANAGER", "receiving.view"), ("PROCUREMENT_MANAGER", "trade.reconcile"),
    ("PROCUREMENT_MANAGER", "trade.accept_variance"), ("PROCUREMENT_MANAGER", "buyer_confirmation.relay"),
    ("PROCUREMENT_MANAGER", "dispute.raise"),
    ("SUPPLY_COORDINATOR", "fulfilment_site.manage"), ("SUPPLY_COORDINATOR", "trade.reconcile"),
    ("SUPPLY_COORDINATOR", "buyer_confirmation.relay"), ("SUPPLY_COORDINATOR", "dispute.raise"),
    ("WAREHOUSE_OPERATOR", "dispute.raise"),
    ("AUDITOR", "audit.flag"),
    ("BUYER", "delivery.confirm_own"),
] + [("PLATFORM_ADMIN", code) for code in NEW_PERMISSIONS]

OLD_SUBLOT_CHECKS = {
    "ck_sublot_received_non_negative": "received_quantity_kg >= 0",
    "ck_sublot_accepted_non_negative": "accepted_quantity_kg >= 0",
    "ck_sublot_rejected_non_negative": "rejected_quantity_kg >= 0",
    "ck_sublot_accounted_within_received": "accepted_quantity_kg + rejected_quantity_kg <= received_quantity_kg",
}


def _uuid(name, *args, **kw):
    return sa.Column(name, sa.Uuid(), *args, **kw)


def _created():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _global_shipment_reference_unique(bind) -> str | None:
    for constraint in sa.inspect(bind).get_unique_constraints("shipments"):
        if constraint["column_names"] == ["reference"]:
            return constraint["name"]
    return None


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("supply_allocations") as batch:
        batch.add_column(sa.Column("released_quantity_kg", sa.Numeric(12, 3), nullable=False, server_default="0"))
    with op.batch_alter_table("production_lots") as batch:
        batch.add_column(sa.Column("reverification_required", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("reverification_reason", sa.String(300), nullable=True))
        batch.add_column(sa.Column("reverification_required_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("viable_until", sa.Date(), nullable=True))
        batch.add_column(sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("withdrawal_reason", sa.String(500), nullable=True))
    with op.batch_alter_table("requirements") as batch:
        batch.alter_column("lifecycle_status", type_=sa.String(30), existing_nullable=False)

    with op.batch_alter_table("received_sublots") as batch:
        batch.add_column(sa.Column("entry_type", sa.String(20), nullable=False, server_default="RECEIPT"))
        batch.add_column(_uuid("adjusts_sublot_id", sa.ForeignKey("received_sublots.id", name="fk_sublot_adjusts"), nullable=True))
        batch.add_column(sa.Column("adjustment_reason", sa.String(500), nullable=True))
        batch.add_column(_uuid("recorded_by_user_id", nullable=True))
        for name in OLD_SUBLOT_CHECKS:
            batch.drop_constraint(name, type_="check")
    with op.batch_alter_table("received_sublots") as batch:
        for name, condition in OLD_SUBLOT_CHECKS.items():
            batch.create_check_constraint(name, f"entry_type = 'ADJUSTMENT' OR {condition}")
        batch.create_check_constraint("ck_sublot_adjustment_link", "(entry_type = 'ADJUSTMENT') = (adjusts_sublot_id IS NOT NULL)")
    op.create_index("ix_received_sublots_adjusts_sublot_id", "received_sublots", ["adjusts_sublot_id"])

    old_unique = _global_shipment_reference_unique(bind) if bind.dialect.name != "sqlite" else None
    with op.batch_alter_table("shipments") as batch:
        if old_unique:
            batch.drop_constraint(old_unique, type_="unique")
        batch.create_unique_constraint("uq_shipment_site_reference", ["fulfilment_node_id", "reference"])
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cancellation_reason", sa.String(500), nullable=True))
    with op.batch_alter_table("deliveries") as batch:
        batch.add_column(_uuid("recorded_by_user_id", nullable=True))

    op.create_table(
        "delivery_adjustments",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("delivery_id", sa.ForeignKey("deliveries.id"), nullable=False),
        sa.Column("delta_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        _uuid("recorded_by_user_id", nullable=False),
        _created(),
    )
    op.create_table(
        "buyer_confirmations",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=False),
        _uuid("delivery_id", sa.ForeignKey("deliveries.id"), nullable=False),
        sa.Column("confirmed_quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("buyer_representative", sa.String(200), nullable=True),
        sa.Column("communication_channel", sa.String(100), nullable=True),
        sa.Column("attestation", sa.String(300), nullable=True),
        sa.Column("stated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        _uuid("recorded_by_user_id", nullable=True),
        _uuid("supersedes_id", sa.ForeignKey("buyer_confirmations.id"), nullable=True),
        _created(),
        sa.CheckConstraint("confirmed_quantity_kg >= 0", name="ck_confirmation_non_negative"),
    )
    op.create_table(
        "reconciliation_records",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        _uuid("supersedes_id", sa.ForeignKey("reconciliation_records.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("figures", sa.JSON(), nullable=False),
        sa.Column("variances", sa.JSON(), nullable=False),
        sa.Column("basis", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("evidence_reference", sa.String(500), nullable=True),
        sa.Column("material_change", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("legacy", sa.Boolean(), nullable=False, server_default=sa.false()),
        _uuid("created_by_user_id", nullable=True),
        _uuid("reviewed_by_user_id", nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.UniqueConstraint("requirement_id", "version", name="uq_reconciliation_version"),
    )
    op.create_table(
        "disputes",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=False),
        _uuid("delivery_id", sa.ForeignKey("deliveries.id"), nullable=True),
        _uuid("raised_by_user_id", nullable=False),
        sa.Column("raised_by_party", sa.String(20), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created(),
    )
    op.create_table(
        "dispute_resolutions",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("dispute_id", sa.ForeignKey("disputes.id"), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("resolution", sa.String(1000), nullable=False),
        _uuid("resolved_by_user_id", nullable=False),
        _created(),
        sa.UniqueConstraint("dispute_id", name="uq_dispute_resolution_once"),
    )
    op.create_table(
        "audit_flags",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("requirement_id", sa.ForeignKey("requirements.id"), nullable=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        _uuid("raised_by_user_id", nullable=False),
        _created(),
    )
    op.create_table(
        "stock_ledger_findings",
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey("organizations.id"), nullable=False),
        _uuid("production_lot_id", sa.ForeignKey("production_lots.id"), nullable=False),
        sa.Column("recorded_reserved_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("expected_reserved_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("difference_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    indexes = {
        "delivery_adjustments": ["organization_id", "delivery_id"],
        "buyer_confirmations": ["organization_id", "requirement_id", "delivery_id"],
        "reconciliation_records": ["organization_id", "requirement_id"],
        "disputes": ["organization_id", "requirement_id"],
        "dispute_resolutions": ["organization_id", "dispute_id"],
        "audit_flags": ["organization_id", "requirement_id"],
        "stock_ledger_findings": ["organization_id", "production_lot_id"],
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])

    with op.batch_alter_table("recovery_tasks") as batch:
        batch.add_column(sa.Column("purpose", sa.String(20), nullable=False, server_default="RECOVERY"))
        batch.add_column(sa.Column("request", sa.JSON(), nullable=True))
    with op.batch_alter_table("recovery_approval_policies") as batch:
        batch.add_column(sa.Column("commitment_release_without_supplier_consent", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))

    _backfill(bind)

    # Explicit casts: PostgreSQL cannot infer parameter types in INSERT ... SELECT.
    for code in NEW_PERMISSIONS:
        bind.execute(sa.text("INSERT INTO permissions (code, description) SELECT CAST(:code AS VARCHAR(100)), CAST(:description AS VARCHAR(500)) "
                             "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)"),
                     {"code": code, "description": code.replace(".", " ").replace("_", " ").title()})
    for role, permission in GRANTS:
        bind.execute(sa.text("INSERT INTO role_permissions (role_code, permission_code) "
                             "SELECT CAST(:role AS VARCHAR(30)), CAST(:permission AS VARCHAR(100)) "
                             "WHERE EXISTS (SELECT 1 FROM roles WHERE code = :role) "
                             "AND EXISTS (SELECT 1 FROM permissions WHERE code = :permission) AND NOT EXISTS "
                             "(SELECT 1 FROM role_permissions WHERE role_code = :role AND permission_code = :permission)"),
                     {"role": role, "permission": permission})


def _backfill(bind) -> None:
    """Copy legacy records forward. The legacy rows themselves are left untouched."""
    records = sa.table("reconciliation_records", *[sa.column(c) for c in (
        "id", "organization_id", "requirement_id", "version", "status", "reason", "evidence_reference",
        "material_change", "legacy")],
        sa.column("figures", sa.JSON()), sa.column("variances", sa.JSON()), sa.column("basis", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)))
    legacy = bind.execute(sa.text(
        "SELECT r.requirement_id, b.organization_id, r.committed_quantity_kg, r.delivered_quantity_kg, "
        "r.accepted_quantity_kg, r.quantity_variance_kg, r.accepted_fulfilment_rate_pct, r.on_time, r.buyer_confirmed, "
        "r.dispute_status, r.verification_evidence_reference, r.reconciled_at "
        "FROM requirement_reconciliations r JOIN requirements q ON q.id = r.requirement_id "
        "JOIN buyers b ON b.id = q.buyer_id")).all()
    rows = []
    for row in legacy:
        rows.append({
            "id": uuid4(), "organization_id": row.organization_id, "requirement_id": row.requirement_id, "version": 1,
            "status": "EFFECTIVE", "reason": "migrated from the record kept before versioned reconciliation (R1 WP4)",
            "evidence_reference": row.verification_evidence_reference, "material_change": False, "legacy": True,
            "figures": {"committed_kg": str(row.committed_quantity_kg), "delivered_kg": str(row.delivered_quantity_kg),
                        "accepted_kg": str(row.accepted_quantity_kg),
                        "accepted_fulfilment_rate_pct": str(row.accepted_fulfilment_rate_pct), "on_time": row.on_time,
                        "legacy_buyer_confirmed_flag": bool(row.buyer_confirmed), "dispute_status": row.dispute_status},
            "variances": {"legacy_quantity_variance_kg": str(row.quantity_variance_kg)},
            "basis": {"legacy_requirement_reconciliation": str(row.requirement_id)},
            "created_at": row.reconciled_at,
        })
    if rows:
        op.bulk_insert(records, rows)

    confirmations = sa.table("buyer_confirmations", *[sa.column(c) for c in (
        "id", "organization_id", "requirement_id", "delivery_id", "confirmed_quantity_kg", "outcome", "channel",
        "note", "evidence_reference", "created_at")])
    flagged = bind.execute(sa.text(
        "SELECT d.id AS delivery_id, s.requirement_id, b.organization_id, d.buyer_confirmation_evidence, d.delivered_at "
        "FROM deliveries d JOIN shipments s ON s.id = d.shipment_id JOIN requirements q ON q.id = s.requirement_id "
        "JOIN buyers b ON b.id = q.buyer_id WHERE d.buyer_confirmed = :yes"), {"yes": True}).all()
    if flagged:
        op.bulk_insert(confirmations, [{
            "id": uuid4(), "organization_id": row.organization_id, "requirement_id": row.requirement_id,
            "delivery_id": row.delivery_id, "confirmed_quantity_kg": 0, "outcome": "CONFIRMED",
            "channel": "LEGACY_UNQUANTIFIED", "evidence_reference": row.buyer_confirmation_evidence,
            "note": "migrated yes/no flag from before R1 WP4; no quantity was recorded, so this is not counted as "
                    "buyer-confirmed quantity", "created_at": row.delivered_at,
        } for row in flagged])


def downgrade() -> None:
    bind = op.get_bind()
    # The pre-WP4 schema cannot represent receipt adjustments; refuse rather than delete physical evidence.
    if bind.execute(sa.text("SELECT COUNT(*) FROM received_sublots WHERE entry_type = 'ADJUSTMENT'")).scalar():
        raise RuntimeError("received_sublots holds ADJUSTMENT rows; downgrading past 0024 would lose them")
    for role, permission in GRANTS:
        if (role, permission) == ("PROCUREMENT_MANAGER", "receiving.view"):
            continue  # may have been granted before 0024; leave it
        bind.execute(sa.text("DELETE FROM role_permissions WHERE role_code = :role AND permission_code = :permission"),
                     {"role": role, "permission": permission})
    for code in NEW_PERMISSIONS:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = :code"), {"code": code})
        bind.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})

    with op.batch_alter_table("recovery_approval_policies") as batch:
        batch.drop_column("commitment_release_without_supplier_consent")
    with op.batch_alter_table("recovery_tasks") as batch:
        batch.drop_column("request")
        batch.drop_column("purpose")
    for table in ("stock_ledger_findings", "audit_flags", "dispute_resolutions", "disputes", "reconciliation_records",
                  "buyer_confirmations", "delivery_adjustments"):
        op.drop_table(table)
    with op.batch_alter_table("deliveries") as batch:
        batch.drop_column("recorded_by_user_id")
    with op.batch_alter_table("shipments") as batch:
        batch.drop_column("cancellation_reason")
        batch.drop_column("cancelled_at")
        batch.drop_constraint("uq_shipment_site_reference", type_="unique")
        if bind.dialect.name != "sqlite":
            batch.create_unique_constraint("shipments_reference_key", ["reference"])
    op.drop_index("ix_received_sublots_adjusts_sublot_id", table_name="received_sublots")
    with op.batch_alter_table("received_sublots") as batch:
        batch.drop_constraint("ck_sublot_adjustment_link", type_="check")
        for name in OLD_SUBLOT_CHECKS:
            batch.drop_constraint(name, type_="check")
    with op.batch_alter_table("received_sublots") as batch:
        for name, condition in OLD_SUBLOT_CHECKS.items():
            batch.create_check_constraint(name, condition)
        batch.drop_constraint("fk_sublot_adjusts", type_="foreignkey")
        batch.drop_column("recorded_by_user_id")
        batch.drop_column("adjustment_reason")
        batch.drop_column("adjusts_sublot_id")
        batch.drop_column("entry_type")
    # requirements.lifecycle_status stays at 30: narrowing could truncate COMPLETED / CLOSED_WITH_VARIANCE rows.
    with op.batch_alter_table("production_lots") as batch:
        for column in ("withdrawal_reason", "withdrawn_at", "viable_until", "reverification_required_at",
                       "reverification_reason", "reverification_required"):
            batch.drop_column(column)
    with op.batch_alter_table("supply_allocations") as batch:
        batch.drop_column("released_quantity_kg")
