# R1 — WP5 handoff

**Branch:** `feat/r1-wp5`, built on `feat/r1-staging-infrastructure` (`07400f0`). Not merged, not deployed.

**Authorization:** "Revised Authorization: Complete WP5 and Prepare Integrations Offline" (5 November 2026).

**Status labels:**
- **Implementation complete:** built and tested locally and in CI.
- **Deployment ready:** needs the steps in `AFTER_WP5_INTEGRATION_CHECKLIST.md`.
- **Externally verified:** against a real service. **Nothing in WP5 is externally verified**; no external service
  was contacted.

## 1. WP5 functionality completed

| Milestone | What a user can now do | Status |
|---|---|---|
| **M1:** role-aware order and fulfilment workspace | Each role sees only the actions it may take on the order page.<br>• Warehouse: receive, grade, ship, dispatch, deliver.<br>• Coordinator: everything except accepting a variance.<br>• Procurement manager: approvals and variance.<br>• Auditor: reads everything, changes nothing, can flag for audit.<br>Sections a role cannot read are not shown, instead of showing a refusal. The Fulfilment Center lists work across all open orders in queues: today's receipts, grading, shipments not dispatched, in transit, deliveries awaiting the buyer, event times to review, disputes, corrections awaiting review, reconciled but not closed. Each queue is marked actionable or for information | Implementation complete |
| **M2:** buyer portal | A buyer opens `/buyer` (their home page now). They see their own orders with ordered, delivered, confirmed-by-them, relayed-by-staff, awaiting-confirmation, disputed and still-to-deliver quantities, all kept apart. Per delivery they see the statement history, with staff relays labelled. They can confirm, report a difference or raise a problem, follow a dispute to its outcome, and download the delivery record (CSV or JSON) | Implementation complete |
| **M3:** internal notification foundation | Staff record a supplier's or buyer's consent to be contacted (append-only, with purposes, wording version and how it was given). Supply requests, reminders, reply-date changes, release agreements and recorded deliveries create notifications from the outbox, only for consented recipients. Staff see every message and its status, including "not sent: no consent" and failures | Implementation complete. **No provider: nothing is sent** |
| M4–M7 | Deferred, unchanged | Not started (by decision) |

## 2. Existing components reused or extended

| Area | Reused or extended |
|---|---|
| Authorization | `ROLE_PERMISSIONS` and the authorization context (now returned by `/me`); `require_permission`; `enforce_path_scope` (new `notification` resolver) |
| Fulfilment data | `reconciliation/application/services.py` helpers: `order_figures`, `delivered_kg`, `current_confirmation`, `open_disputes`, `sequence_findings`, `completion_check`, `effective_receipt`. These feed the overview and the buyer portal |
| Buyer actions | Existing buyer confirm and dispute endpoints and the `/deliveries` page (kept) |
| Notifications | Transactional outbox (`DomainEvent`, `OutboxMessage`); the worker loop (one savepointed hook and one dispatch step); existing domain events (`solicitation.*`, `supplier.release_agreed`, `delivery.recorded`) |
| Models | The model-provider architecture (`ProviderClient.complete`, `model_enabled`); the evidence layer uses it, adding no new provider code |
| Infrastructure | `with_env`, `check_staging`, the Data API audit (extended to keep `agri` closed); the E2E seed (an auditor added) |

## 3. New files and migrations

**Migrations:**
- `0028_notifications_consent`: `contact_consents`, `notifications`, `notification_status_events`, with RLS on
  Supabase.
- `0029_agricultural_intelligence`: the `agri` schema, 20 tables, PostgreSQL only.

**Backend:**
- `reconciliation/application/overview.py` and `buyer_portal.py`.
- `notifications/` (domain, templates, providers, service, API).
- `agriculture/` (domain models, `ingestion.py`, `forecasting.py`, `evidence.py`).
- `scripts/agri_import.py`.

**Data:** `src/backend/data/agriculture/`, reference definitions and empty templates. No statistics.

**Frontend:**
- `components/trade/FulfilmentOverview.tsx`, `BuyerPortal.tsx`, `ContactConsentPanel.tsx`.
- `components/OutboundNotifications.tsx`.
- `hooks/useNotifications.ts`.
- `app/buyer/page.tsx`.

**Deployment:** `deploy/sql/` (reviewed upgrade SQL, verified with `psql`; opt-in read-only role; README).

**Documents:**
- `docs/integrations/` README, `AGRICULTURAL_DATA.md`, `MESSAGING.md`, `ML_AND_LLM.md`, `LEGACY_DATABASE.md`.
- `docs/product/AFTER_WP5_INTEGRATION_CHECKLIST.md` and this handoff.

**Tests:**
- `test_wp5.py`, `test_agriculture_postgres.py`, `test_agri_intelligence.py`.
- `src/frontend/src/test/consentPanel.test.tsx`.

## 4. Existing files materially modified

| File | Change |
|---|---|
| `assurance/api/router.py` | `POST /requirements/{id}/plan` now requires `supply.manage` (security fix, §7) |
| `reconciliation/application/services.py` | `current_confirmation` follows the supersedes chain (§7) |
| `identity/api/router.py` | `/me` adds `permissions` (additive) |
| `core/config.py` | `NOTIFICATION_PROVIDER` validation |
| `worker.py` | Notification hook in a savepoint; dispatch step |
| `main.py`, `identity/application/tenancy.py` | Notifications router; `notification` resolver |
| `infrastructure/database/data_api.py`, `scripts/check_staging.py` | `agri` covered by the Data API audit |
| `FulfilmentSection.tsx`, `OrderDetail.tsx` | Permission gating; auditor flag; variance close only for roles that may accept it |
| `AppShell.tsx`, `RoleHome.tsx` | Buyer navigation and home page now `/buyer`; the marketplace and `/deliveries` stay reachable |
| `app/fulfilment/page.tsx` | Fulfilment Center shows the new overview. The old single-order summary component is kept: other workspace views use it |
| `SuppliersWorkspace.tsx`, `pages/Notifications.tsx` | Consent panel; outbound messages list |
| `useIdentity.ts`, `useFulfilment.ts`, `lib/api.ts` | `useCan`, portal and overview hooks, authenticated file download |
| `e2e/r1/fulfilment-reconciliation.spec.ts` and README; `scripts/seed_e2e.py` | WP5 role, portal and messages checks; auditor account |
| `test_fulfilment.test.tsx`, `test_tenant_isolation.py`, `test_migrations_postgres.py` | See §5 |
| `deploy/*`, env templates, README, readiness register, debt register, WP5 proposal | Configuration and documentation |

## 5. Files removed

**None.**

Three existing tests changed, each because behaviour changed on purpose, not to hide a defect:
- **WP4 browser spec, coordinator close:** it used to submit "close with variance" and expect the server's refusal.
  The form is no longer offered to coordinators (the M1 acceptance criterion). The spec now asserts the form is
  absent and that the page explains who can close. The server refusal itself is still tested in
  `test_fulfilment_accounting.py`.
- **`fulfilment.test.tsx`:** the test server now serves `/me` with a coordinator's permissions, because actions
  depend on permissions.
- **`test_migrations_postgres.py`:** the head revision is compared with the script directory's head instead of a
  hard-coded id.

The tenant-isolation sweep gained a fixture for the new `notification_id` route.

## 6. Database and integration artifacts prepared

- **Alembic migrations 0028 and 0029** (authoritative). Reviewed SQL in `deploy/sql/`, applied with `psql` to a
  disposable database at 0027: identical end state, `data_api_grants` PASS.
- **Agricultural schema:**
  - source registry with licence review;
  - publications and revisions;
  - raw rows;
  - validation issues;
  - crops, places, units, measures and aliases;
  - validated observations (one current revision each);
  - FAOSTAT rows;
  - indicators, features, model runs, forecasts and evaluations.

  The schema is closed to `PUBLIC` and the Supabase roles.
- **Offline importer:**
  - dry run by default;
  - licence-gated;
  - idempotent per file hash;
  - provenance, validation, unit normalisation without FX, revisions;
  - FAOSTAT verified-only mapping.
- **Source catalogue:**
  - Ministry (11 datasets listed, 7 prepared): PDF only, **"All Rights Reserved"**, so permission is needed.
  - FAOSTAT (QCL, PP): CC BY 4.0, awaiting the product owner's confirmation.
- **Templates and mappings:** CSV templates, alias templates, and a FAOSTAT element map (unverified).
- **Forecasting and evidence:** interfaces, four baselines, backtesting, evidence retrieval with privacy, licence,
  model and cost gates and answer verification.
- **Configuration:** placeholder settings for notifications, agricultural LLM use, future messaging and monitoring.
  Secret files stay gitignored.
- **Tristan's database:** untouched; a read-only assessment plan is documented.

## 7. Security improvements

1. **Planning permission (fixed):** any staff role, including auditors and warehouse operators, could start supply
   planning, which fixes an order's terms. It now needs `supply.manage`, with a regression test.
2. **Buyer statement order (fixed):** the current statement could be chosen wrongly when two statements share a
   timestamp (whole seconds on SQLite). It now follows the supersedes chain.
3. **Buyer portal scope:** the membership's own buyer record in its organization only; anything else returns 404.
   Supplier identities and internal records are not exposed. Download cells are formula-safe, and downloads use a
   header token, never a URL token.
4. **Notifications:**
   - no message without consent; withdrawal stops queued messages;
   - addresses masked, kept out of the event stream, and never stored on messages;
   - agent-authored events never message;
   - `synthetic` and unknown providers refused in production.
5. **Agricultural data:**
   - separate schema with no client-role access;
   - licence gate on applying imports;
   - read-only, catalogue-only queries for any model;
   - public statistics only, never operational data, to providers.
6. **Previously identified staging corrections:** completed in `420f544` and tested locally (Data API verification
   and immediate sign-out revocation). Still unverified against a real Supabase project.
7. **Defence-in-depth debt recorded** (item 33): the demo seed's synthetic consent channel is not reachable through
   the API.

## 8. Tests executed and results

All local runs on 5 November 2026.

| Suite | Result |
|---|---|
| Backend, full (SQLite and PostgreSQL 17) | Full run: **566 passed, 1 failed, 3 skipped**. The failure was real: migration 0029 needs CREATE on the database, which the restricted role in `test_alembic_accepts_url_encoded_passwords` lacked. Fixed by an early, explained check in 0029, a documented requirement, and the grant in that test; the two affected files were rerun afterwards: 20 passed. The 3 skips are local copies of PostgreSQL-only cases |
| Frontend unit (Vitest) | 57 passed; lint and typecheck clean |
| R1 browser E2E: production build, real API, worker and PostgreSQL, test-only auth stand-in | **30 passed**: the 27 existing tests plus WP5 auditor, buyer portal and outbound messages, and new role assertions inside the WP4 story |
| Reviewed SQL artifact | Regenerated after the fix and applied with `psql`: revision 0029, row-level security on, 20 `agri` tables, `data_api_grants` PASS |
| CI on GitHub | **Passed, both jobs** on `e1fa5b8` ([run 42068301028](https://github.com/TopRam3n/Koro-Farm/actions/runs/42068301028)):<br>• `verify`: backend on PostgreSQL, frontend checks, browser E2E;<br>• `container-images`: images built and the staging rules checked in them |

These are local and CI runs: **they do not verify any connection to Supabase, a hosting provider, a messaging
provider, a model provider, the Ministry or FAOSTAT.**

## 9. Deferred external connections

Not connected, and not attempted:
- Supabase (database and authentication);
- hosting and domain;
- uptime monitoring;
- SMS, WhatsApp and email;
- MiniMax and Nebius;
- Ministry of Agriculture data;
- FAOSTAT;
- Tristan's database.

## 10. Outstanding product-owner actions

See `AFTER_WP5_INTEGRATION_CHECKLIST.md` for the order.
1. Pilot database: does one with real records exist?
2. Review and merge the branch stack, in order.
3. Supabase project and settings (setup guide §1), then the read-only check.
4. VPS specifications, domain and uptime monitor.
5. **Ministry of Agriculture:** request written permission for the AMID statistics.
6. **FAOSTAT:** confirm the licence and attribution.
7. **Messaging:** decide the channel, provider and consent wording; whether staging may message real numbers.
8. **Models:** keys in local files only, Nebius Zero Data Retention, evaluation budget. Whether agricultural
   answers may use a model in staging.

## 11. Remaining limitations and technical debt

- **The disabled-Data-API response** has not been seen from a real project (setup guide §1.11).
- **Browser suite and session checks:** the browser suite uses the auth stand-in, so the database session check is
  covered by PostgreSQL tests and the staging gate, not by the browser suite (debt item 35).
- **Agricultural data:**
  - FAO codes and the element map are unverified;
  - Ministry tables need manual transcription with a second-person check;
  - yield-consistency and parish-sum rules are planned (item 37).
- **Messaging:** templates are draft wording; there is no provider (item 36).
- **Time zones:** "today" in the Fulfilment Center is Jamaica time (UTC−5 fixed); a multi-country deployment would
  need per-organization time zones.
- **SQLite timestamps:** whole seconds can still tie in other lists (item 34). PostgreSQL is unaffected.
- **Deferred:** M4–M7 and the items in the WP5 proposal §3.
