# R1 deferred technical-debt register

**Kept since:** WP3 (31 October 2026). This register is updated at the end of each work package.
**Rule:** an item is fixed inside a work package only when the approved workflow or safety needs it. Everything else waits here with its owner, impact and intended work package.

**Owner** means who decides or carries the work:
- **Product owner:** you, for policy and priority.
- **Engineering:** the delivery team, for implementation.
- **Operations:** whoever runs the deployment.

Line numbers refer to branch `feat/r1-wp3-agent-orchestration`.

## Items named in the WP3 instruction

| # | Item | Where (source) | Impact today | Owner | Intended work package |
|---|---|---|---|---|---|
| 1 | Legacy ingestion availability endpoint | `src/backend/app/ingestion/api/router.py:236` (`POST /v1/ingestion/farmer-production-lots/{lot_id}/availability`) | A second way to change a lot's availability, outside the capacity-report rules in WP2 (`supply/application/capacity.py`). The portal no longer uses it. It still refuses figures below reserved stock, so it cannot over-reserve, but its changes are not shown as capacity reports. | Engineering | WP4: retire it, or route it through `record_capacity_report` |
| 2 | Marketplace reservations are not part of exposure | `src/backend/app/supply/application/capacity.py:128` (`lot_exposure` covers supplier commitments and standby only) | A capacity cut below stock reserved by marketplace orders lowers free stock but opens no exception, and the recovery agent does not see it. | Product owner (whether marketplace orders get supply assurance), then engineering | WP4 or the marketplace package |
| 3 | Grade A only | `src/backend/app/supply/application/planner.py:93` (`requirement.grade == Grade.A`); recovery uses the same eligibility (`agents/application/evidence.py`, `gather`) | Orders for other grades cannot be planned or recovered. | Product owner | WP4 |
| 4 | External supplier notifications | Reminders are in-app only: `src/backend/app/assurance/application/exceptions.py:197` (`send_reminder`). Agent-drafted messages are stored drafts: `agents/application/orchestrator.py` (`content["drafts"]`, `SOLICIT_SUPPLY.message`) | A farmer who does not open the portal does not see a request, a reminder or a deadline. WhatsApp, SMS and email are not sent, by WP3 decision 4. | Product owner (channel, consent to contact, provider), then engineering | WP5 (communications) |
| 5 | Organization-wide response policies | `src/backend/app/supply/application/commitments.py:97` (24 h, 4 h and 48 h are code constants) | Coordinators can change single deadlines, with an audit trail. An organization cannot set its own defaults. Recovery requests use the same defaults (`evidence.py`, `default_response_hours`). | Product owner | WP4 |
| 6 | Buyer-side delivery confirmation | `src/backend/app/reconciliation/api/router.py:102` (`deliver`): staff record `buyer_confirmed` with evidence; the buyer cannot confirm for themselves | Delivery confirmation is relayed by staff, not given by the buyer directly. | Product owner | WP5 (buyer portal) |
| 7 | Real Supabase staging authentication | `src/backend/app/core/auth.py:11`; checklist `docs/product/STAGING_AUTH_VERIFICATION.md` | Every automated run uses the test-only auth stand-in. Real sign-in, refresh, cross-organization access and sign-out are unverified. **Mandatory release gate** before any public deployment. | Operations (staging deployment and accounts), then engineering runs the checks | Before any deployment; not deferrable past the first staging release |

## Items found during WP3

| # | Item | Where (source) | Impact today | Owner | Intended work package |
|---|---|---|---|---|---|
| 8 | An order with binding supply cannot be cancelled through the API | `src/backend/app/demand/api/router.py:280` refuses cancellation while commitments or standby exist | The recovery agent cancels its task when an order is cancelled (tested), but a coordinator must first release supply by other means. | Product owner (cancellation policy toward suppliers) | WP4 |
| 9 | A dropout keeps the lost allocation's lot reservation | `src/backend/app/assurance/application/recovery.py:126` (`dropout` marks the allocation LOST but does not release `reserved_quantity_kg`) | Pre-R1 behaviour, unchanged. Free stock on that lot is understated, which is conservative and cannot over-commit. Releasing exposed commitment through recovery does release the reservation (`gateway._release_exposed`). | Engineering | WP4 |
| 10 | Supplier requests reserve nothing | `src/backend/app/supply/application/commitments.py:108` (`solicit`); recovery requests use it | Two orders may ask for the same free stock. The first acceptance wins and the later one is refused as stale (tested since WP1). The agent re-plans when that happens. | Product owner (whether to reserve on request) | Later, if pilots show contention |
| 11 | ~~The orchestrator holds the task's row lock during a model call~~ | **Resolved** on `feat/r1-wp3-model-providers`: `orchestrator.advance_due` and `finish_decision` call the model between two transactions, with a planning lease and an evidence fingerprint | — | — | — |
| 12 | Pre-R1 demo scripts no longer run | `src/backend/scripts/e2e_recovery_demo.py`, `e2e_quality_recovery_demo.py` (schema creation fails; they also describe the removed automatic recovery) | None in the product. Misleading if someone runs them. | Engineering | WP4: delete or rewrite against the approval flow |
| 13 | Rule-based "agent evaluation" from before R1 | `src/backend/scripts/evaluate_agents.py` (scores hand-written states, not the system) | It is not evidence about the recovery agent. The WP3 model evaluation is `scripts/evaluate_recovery_model.py`. | Engineering | WP4: retire or relabel |
| 14 | The first tick after an incident waits for the next poll | `src/backend/app/worker.py` (`on_event` uses wall-clock time for a new task) | Planning starts on the next worker tick (2 s by default), not in the same tick. | Engineering | Low priority |
| 15 | ~~Standby authorization judged by local date in one place~~ | **Resolved** on `feat/r1-wp3-model-providers`: `recovery.authorized_standby` now uses the UTC date, like expiry, response validation and the gateway. Two WP2 tests built dates from the local day and failed between 19:00 local and midnight UTC; they now use the API's UTC day | — | — | — |
| 16 | No live model evaluation yet | `src/backend/scripts/evaluate_recovery_model.py` is built and tested with scripted clients. No MiniMax or Nebius credentials were configured when it was built | Model quality is unknown. Every safety property holds regardless of model quality, enforced by validation, approval and the gateway | Product owner (keys, configured locally), then engineering runs it | Before enabling a model in staging |

## Not debt: decisions kept on purpose

- **Production model access is disabled:**
  - `core/config.py` refuses to start with `AGENT_MODEL_PROVIDER` in production;
  - `agents/infrastructure/model.py` falls back to deterministic decisions there.
- **No user role holds `recovery.execute`.** Only the gateway executes, and only an approved proposal.
