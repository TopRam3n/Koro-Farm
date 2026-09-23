# Real-world ingestion sprint report

Assessment date: 2026-09-22

| Area | Status | Evidence / limitation |
|---|---|---|
| Provenance model | IMPLEMENTED | Ingestion record, observation source, actor, channel, effective/recorded time, independent verification and freshness, evidence reference, command and resulting event |
| Farmer secure links | IMPLEMENTED | Opaque hashed tokens, expiry, single purpose, organization/farmer/lot scope, constraints, single use, audit record, mobile response route |
| Coordinator entry | IMPLEMENTED | Phone, WhatsApp-source, and coordinator-entry observations; recorder and farmer source remain distinct |
| CSV import | IMPLEMENTED | Farmers, production lots, and buyer requirements; templates, preview, row errors/warnings, confirmation, linked domain events, import ID, file and in-file row duplicate protection |
| Stable ingestion API | IMPLEMENTED (v1 scope) | Versioned routes, membership/permission boundary, organization scope, idempotency on commands, correlation and audit fields |
| Messaging adapter | DEVELOPMENT ONLY | Provider interface and console provider; no external message is claimed delivered; WhatsApp/SMS credentials are not configured |
| Farmer portal | PARTIAL | Secure mobile response works; complete farmer navigation, commitments, standby, deliveries, and trade history remain outstanding |
| Warehouse ingestion | PARTIAL | Existing receipt/grading invariants and evidence fields remain operational; standardized ingestion records are not yet emitted for every warehouse command |
| Farmer onboarding | NOT IMPLEMENTED | Staged onboarding persistence and consent workflow remain outstanding |
| Exception taxonomy | NOT IMPLEMENTED | Existing recovery/quality/buyer-change events exist, but the unified agricultural exception model is outstanding |
| Decision Inbox | NOT IMPLEMENTED | Approval-governance persistence and human-decision workflow remain outstanding |
| Pilot configuration | DOCUMENTED ONLY | Controlled operating model and honest KPI definitions exist; no pilot outcome is manufactured |
| Value measurement | DOCUMENTED ONLY | Existing events can support future measures; savings and counterfactuals remain `NOT MEASURED` |
| Demo-day multi-channel sequence | PARTIAL | Secure farmer update and recovery primitives exist; the complete governed approval-to-evidence browser sequence is outstanding |

## Validation

- Backend functional tests: 64 passed.
- PostgreSQL-only tests: 9 skipped because a configured credentialed test URL
  was unavailable.
- Ingestion tests: 8 passed, covering secure success, expiry, reuse, tampering,
  scope, reservation safety, coordinator attribution, CSV errors, duplicate
  import, confirmation idempotency, scoped parents, and templates.
- Structured red-team evaluation: 18/18 passed; unsafe actions,
  authorization violations, inventory invariant violations, unsupported
  compliance claims, and premature evidence counts remain zero in the current
  corpus.
- Frontend lint, TypeScript, and 7 component tests passed.
- Configured demo production build passed with 32 routes.
- Existing Playwright browser suite: 9/9 passed; a secure-link-specific browser
  flow is still outstanding.

## Release position

This is a working first ingestion increment, not completion of the entire
pilot-operations sprint. Production release remains blocked on the outstanding
areas above, fresh PostgreSQL migration/concurrency/reset evidence, complete
legacy endpoint authorization, deployed Supabase sessions, external provider
delivery tests, and expanded browser coverage for the secure-link workflow.
