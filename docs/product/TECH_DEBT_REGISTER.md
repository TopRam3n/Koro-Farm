# R1 deferred technical-debt register

**Kept since:** WP3 (31 October 2026); updated for WP4 (1 November 2026). This register is updated at the end of each work package.
**Rule:** an item is fixed inside a work package only when the approved workflow or safety needs it. Everything else waits here with its owner, impact and intended work package.

**Owner** means who decides or carries the work:
- **Product owner:** you, for policy and priority.
- **Engineering:** the delivery team, for implementation.
- **Operations:** whoever runs the deployment.

Line numbers in items 1–16 refer to branch `feat/r1-wp3-agent-orchestration`; WP4 items refer to `feat/r1-wp4-fulfilment-accounting`.

## Items named in the WP3 instruction

| # | Item | Where (source) | Impact today | Owner | Intended work package |
|---|---|---|---|---|---|
| 1 | ~~Legacy ingestion availability endpoint~~ | **Resolved in WP4 (P8):** returns 410 with guidance; secure-link replies and coordinator observations go through `record_capacity_report` (`ingestion/api/router.py: _apply_observation`). Remove the 410 stub after one release (item 19) | — | — | — |
| 2 | Marketplace reservations are not part of exposure | `supply/application/capacity.py` (`lot_exposure`) | **WP4 (P10):** marketplace orders are disabled for the pilot and fail closed at the backend; PLACED orders are included in the stock ledger check and listed by the release audit. Exposure still ignores them. | Product owner (whether marketplace orders get supply assurance) | Marketplace package, before re-enabling marketplace orders |
| 3 | Grade A only | `src/backend/app/supply/application/planner.py:93` (`requirement.grade == Grade.A`); recovery uses the same eligibility (`agents/application/evidence.py`, `gather`) | Orders for other grades cannot be planned or recovered. | Product owner | WP4 |
| 4 | External supplier notifications | Reminders are in-app only: `src/backend/app/assurance/application/exceptions.py:197` (`send_reminder`). Agent-drafted messages are stored drafts: `agents/application/orchestrator.py` (`content["drafts"]`, `SOLICIT_SUPPLY.message`) | A farmer who does not open the portal does not see a request, a reminder or a deadline. WhatsApp, SMS and email are not sent, by WP3 decision 4. | Product owner (channel, consent to contact, provider), then engineering | WP5 (communications) |
| 5 | Organization-wide response policies | `src/backend/app/supply/application/commitments.py:97` (24 h, 4 h and 48 h are code constants) | Coordinators can change single deadlines, with an audit trail. An organization cannot set its own defaults. Recovery requests use the same defaults (`evidence.py`, `default_response_hours`). | Product owner | WP4 |
| 6 | ~~Buyer-side delivery confirmation~~ | **Resolved in WP4 (P5):** buyers confirm, part-confirm or report a difference in their account (`POST /buyer/deliveries/{id}/confirmation`, `/deliveries` page); staff relay is attested and labelled | — | — | Further buyer portal work: WP5 |
| 7 | Real Supabase staging authentication | `src/backend/app/core/auth.py:11`; checklist `docs/product/STAGING_AUTH_VERIFICATION.md` | Every automated run uses the test-only auth stand-in. Real sign-in, refresh, cross-organization access and sign-out are unverified. **Mandatory release gate** before any public deployment. | Operations (staging deployment and accounts), then engineering runs the checks | Before any deployment; not deferrable past the first staging release |

## Items found during WP3

| # | Item | Where (source) | Impact today | Owner | Intended work package |
|---|---|---|---|---|---|
| 8 | ~~An order with binding supply cannot be cancelled through the API~~ | **Resolved in WP4 (P1):** cancellation requests, supplier release agreements and approved FULL or REMAINDER cancellation (`agents/application/releases.py`, gateway `_cancel_order`) | — | — | — |
| 9 | ~~A dropout keeps the lost allocation's lot reservation~~ | **Resolved in WP4 (P3):** `recovery.dropout` releases the undelivered remainder at once through `release.py` (attribution `SUPPLIER_DROPOUT`) and flags the lot for re-verification | — | — | — |
| 10 | Supplier requests reserve nothing | `src/backend/app/supply/application/commitments.py:108` (`solicit`); recovery requests use it | Two orders may ask for the same free stock. The first acceptance wins and the later one is refused as stale (tested since WP1). The agent re-plans when that happens. | Product owner (whether to reserve on request) | Later, if pilots show contention |
| 11 | ~~The orchestrator holds the task's row lock during a model call~~ | **Resolved** on `feat/r1-wp3-model-providers`: `orchestrator.advance_due` and `finish_decision` call the model between two transactions, with a planning lease and an evidence fingerprint | — | — | — |
| 12 | Pre-R1 demo scripts no longer run | `src/backend/scripts/e2e_recovery_demo.py`, `e2e_quality_recovery_demo.py` | None in the product. Misleading if someone runs them. Not needed for the WP4 workflow, so left. | Engineering | WP5: delete or rewrite against the approval flow |
| 13 | Rule-based "agent evaluation" from before R1 | `src/backend/scripts/evaluate_agents.py` | It is not evidence about the recovery agent. The WP3 model evaluation is `scripts/evaluate_recovery_model.py`. Not needed for WP4, so left. | Engineering | WP5: retire or relabel |
| 14 | The first tick after an incident waits for the next poll | `src/backend/app/worker.py` (`on_event` uses wall-clock time for a new task) | Planning starts on the next worker tick (2 s by default), not in the same tick. | Engineering | Low priority |
| 15 | ~~Standby authorization judged by local date in one place~~ | **Resolved** on `feat/r1-wp3-model-providers`: `recovery.authorized_standby` now uses the UTC date, like expiry, response validation and the gateway. Two WP2 tests built dates from the local day and failed between 19:00 local and midnight UTC; they now use the API's UTC day | — | — | — |
| 16 | No live model evaluation yet | `src/backend/scripts/evaluate_recovery_model.py` is built and tested with scripted clients. No MiniMax or Nebius credentials were configured when it was built | Model quality is unknown. Every safety property holds regardless of model quality, enforced by validation, approval and the gateway | Product owner (keys, configured locally), then engineering runs it | Before enabling a model in staging |

## Items found during WP4

| # | Item | Where (source) | Impact today | Owner | Intended work package |
|---|---|---|---|---|---|
| 17 | Harvest re-verification period is one setting for every crop | `src/backend/app/supply/application/lot_timers.py` (`HARVEST_REVERIFY_DAYS`, default 7) | P9 asks for a per-crop policy eventually. Every crop uses 7 days. | Product owner (periods per crop), then engineering | WP5 |
| 18 | Grade A only, and fixed response windows (items 3 and 5) are still open | `supply/application/planner.py`, `supply/application/commitments.py` | Unchanged by WP4: not needed for the fulfilment workflow. | Product owner | WP5 |
| 19 | The retired availability endpoint still answers 410 | `src/backend/app/ingestion/api/router.py` (`report_farmer_availability`) | Kept for one release so unknown callers get guidance. | Engineering | Remove in the release after R1 |
| 20 | Warehouse operators see refusal notes on parts of the order page | `components/trade/OrderDetail.tsx` (`ExceptionList`, `RecoveryTasks`), whose APIs need `recovery.view` | The fulfilment section works; the recovery and exceptions panels show the server's 403 message instead of hiding. | Engineering | WP5 (role-aware order workspace) |
| 21 | On SQLite the old global shipment-reference unique constraint stays | `alembic/versions/0024_fulfilment_accounting.py` (SQLite cannot drop the unnamed constraint by name) | Development databases only: references stay globally unique there, which is stricter. PostgreSQL drops it and enforces uniqueness per site. | Engineering | None unless SQLite is used for anything shared |
| 22 | Downgrading past 0024 is refused while receipt adjustments exist | `0024_fulfilment_accounting.py` (`downgrade`) | Deliberate: the older schema cannot represent corrections, and deleting physical evidence is not allowed. `lifecycle_status` stays 30 characters wide after downgrade. | Operations | None |
| 23 | A planner concurrency test on a SQLite file is load-sensitive | `src/backend/tests/test_planner.py` (`test_concurrent_planning_attempts_create_only_one_plan`) | Failed once in a full local run (both threads hit "database is locked"); passed 8 of 8 when repeated alone. PostgreSQL concurrency is covered separately and passed. | Engineering | Low priority: make it PostgreSQL-only or retry the lock |
| 24 | The release audit has not been run on any shared database | `src/backend/scripts/release_audit.py` | Pre-WP4 data may still hold reservations on closed or cancelled orders. Needs a backup, the dry-run report and your approval before `--apply`. | Product owner (approval), operations (backup and run) | Before the pilot database is used with WP4 |
| 25 | Close-out releases what was never received but does not re-plan other orders | `reconciliation/application/services.py` (`close_order`) | Released stock waits for re-verification (P2); no order is offered it automatically. | Product owner | Working as authorized; revisit after the pilot |
| 26 | Dispatch time is when staff pressed Dispatch, not when goods left | `reconciliation/application/services.py` (`dispatch` sets `dispatched_at` to now; `record_delivery` takes a stated `delivered_at`) | A delivery entered afterwards can show an earlier time than its dispatch (seen in the WP4 browser run). Quantities are unaffected. Refusing such deliveries would block legitimate back-entry, so it is not enforced. | Engineering | WP5: let dispatch record the physical departure time, then enforce the order |

## Not debt: decisions kept on purpose

- **Production model access is disabled:**
  - `core/config.py` refuses to start with `AGENT_MODEL_PROVIDER` in production;
  - `agents/infrastructure/model.py` falls back to deterministic decisions there.
- **No user role holds `recovery.execute`.** Only the gateway executes, and only an approved proposal.
