# Governance phase status

Assessment date: 2026-09-21

## Implemented

- Separate user identity, organization, membership, role, permission, and
  role-permission models.
- Centrally defined roles and permission grants; no `is_admin` shortcut.
- Invite-only local membership lifecycle: invite, accept, role change,
  membership deactivation, profile, and explicit organization selection.
- Tenant administrators cannot assign or manage `PLATFORM_ADMIN` membership.
- Organization ownership on buyer, farmer, fulfilment-node, compliance-rule,
  and trade-corridor roots. Requirements and production lots inherit an
  unequivocal parent boundary.
- Organization-scoped requirement access and organization/farmer-scoped
  production-lot access with non-leaking `404` behavior.
- Automated authorization matrix for allowed, wrong-role, cross-tenant,
  inactive, unauthenticated, auditor, warehouse, and farmer cases.
- Invite-only frontend posture, supported Supabase login/reset/logout path,
  organization header propagation, and role-derived My Work.
- Versioned capability inventory, CLI evaluation runner, structured report,
  filters, adversarial fixtures, and zero-tolerance release safety policy.

## Not yet certified

- Permission and object-scope enforcement has not yet been applied to every
  legacy assurance, recovery, receiving, shipment, reconciliation, registry,
  compliance, and trade-evidence endpoint.
- Recovery proposal/approval/execution persistence and configurable thresholds
  are not yet implemented.
- The complete lifecycle state machine and transition ledger are not yet
  implemented as a single governed projection.
- The Administration frontend surfaces currently explain the live boundary but
  do not yet edit backend records.
- The internal Agent Lab backend persistence and `PLATFORM_ADMIN` UI are not yet
  implemented.
- The evaluation corpus is a first safety-contract suite, not yet the full
  statistical corpus requested for every boundary and failure mode.
- Fresh PostgreSQL migrations, PostgreSQL concurrency tests, live Supabase, and
  deployed multi-role browser sessions remain untested in this environment.

Production release remains blocked until every item above is closed and the
machine-readable release gate includes the PostgreSQL and cross-tenant jobs.
