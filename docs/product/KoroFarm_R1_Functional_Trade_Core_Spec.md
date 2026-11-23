# KoroFarm — Release 1: Functional Trade Coordination Core

> Source: specification supplied by the founder in the Claude Code session of 28 October 2026, saved verbatim here so that work can cite it. The execution brief that accompanies it is summarised at the end.

**Status:** proposed implementation baseline, 28 October 2026
**Sponsor:** Arryst Systems / KoroFarm team (ownership and licensing to be confirmed)
**Purpose:** replace dependence on a seeded 500 kg demonstration with a functioning, multi-user, evidence-preserving agricultural trade workflow; establish the first genuine event-driven agentic coordination capability.

**Not in R1:** live cross-border regulatory filing, authoritative export clearance, real freight booking, financial lending/scoring, public produce marketplace, production-scale forecasting. Export trade feasibility is Release 2. R1 should store origin/destination and trade terms without claiming export readiness.

## 1. Product contract

- **User:** supply/export coordinator working with existing producer networks and institutional buyers.
- **Job:** receive a buyer's requirement, assemble and confirm multi-farm supply, monitor and resolve shortages, record physical receipt/quality/delivery and reconcile supported evidence.
- **Result:** a buyer order has traceable, correct, current states and a reviewable transaction history.
- **Success criterion:** a user creates and completes an unfamiliar order, independently of demo fixtures, with data persisting through refresh and across authorized sessions.

### Principles that may never be weakened

1. Required, available, solicited, reserved, committed, standby, received, quality-accepted, rejected, dispatched, delivered and buyer-confirmed amounts are distinct.
2. Supplier commitment requires explicit acceptance. Standby authorization is separate and does not count toward committed coverage until valid activation/acceptance.
3. Allocation is bounded by eligible available capacity across all concurrent orders; state changes are transactionally safe and idempotent.
4. Unknowns are unknown; no fabricated supply, regulatory approval, price, sensor reading, delivery or AI reasoning.
5. Material actions carry an accountable identity and approval. An LLM cannot create binding trade commitments, mutate inventory totals directly, or substitute for deterministic eligibility or arithmetic.
6. A successful recovery means committed coverage restored; physical fulfillment is a separate set of events.
7. Immutable historical events and original economics/risk snapshots; corrections occur via new events, not retroactive mutation.
8. Existing schema, API logic and PostgreSQL concurrency tests should be reused or migrated deliberately, not replaced blindly.

## 2. Users and authority

- **Org Admin:** invite users, manage policies and inspect audit; cannot alter immutable history.
- **Coordinator/Exporter:** manage orders, solicit producers, propose/approve within policy, document fulfilment.
- **Buyer:** review own orders; confirm actual deliveries; no visibility into unrelated tenants.
- **Supplier/Farmer:** view and accept/decline only their solicitations; update their supply declarations within permissions.
- **Receiver/QC:** record quantity, quality results and evidence; cannot rewrite commitments.
- **System Agent:** event-driven tool-using service with no blanket admin permission; its actions are attributed, constrained and independently authorized.

For the first pilot, supply updates may be entered by a coordinator on behalf of a farmer only with source, attestation method, timestamp and provenance; this does not count as independent farmer confirmation unless documented.

## 3. Functional requirements (R1)

**R1-F01 — Organization and permission boundary**
- Organization-scoped storage, role-based authorization, authentication and least privilege on every command/read.
- Never use demo auth bypass in real tenant environments.
- Users in Organization A cannot see, modify or infer records of Organization B.

**R1-F02 — Buyer demand and order lifecycle**
- Create/modify/cancel buyer orders with crop, product form, grade/spec, required quantity and unit, target window, buyer, origin, destination, delivery terms, currency, status and provenance.
- Recurring programme optional within R1; one-off orders fully supported.
- Persist and reload orders, validation failures and change history.
- New order entry must not depend on known ginger fixture IDs.

**R1-F03 — Supplier and lot management**
- Create and manage producers and production lots with quantities, time windows, location, quality declarations, provenance and validation status.
- Capacity and quality states explicitly distinguish declared from verified.
- Capture changes and attributable evidence; stock becomes unavailable when expired or withdrawn.

**R1-F04 — Planning, solicitations and commitments**
- Compute eligible candidate supply based on grade, crop, dates, location, capacity and policies.
- Produce explainable primary/standby allocation proposals and cost/risk estimates from deterministic services.
- Solicit offers; explicitly record accepted, declined, timed-out and withdrawn responses.
- Enforce reservation rules with PostgreSQL transactions and concurrency controls.

**R1-F05 — Event-driven exception detection**
- On capacity changes, missed acceptance/deadline, supplier dropout or quality rejection, detect a requirement exposure and open an exception record automatically.
- Record shortfall, cause, affected order and event origin; avoid duplicate exceptions from retry/replay.
- No user-facing "Simulate dropout" control is part of normal live workflow. Simulation remains a labelled test/demo environment.

**R1-F06 — Recovery and escalations**
- Compute replacement options from eligible standby and other eligible, unreserved lots; consider authorization, timing, grade, exposure and cost.
- The agent proposes an action with structured evidence and deterministic feasibility checks.
- Any actual reservation, solicitation or material substitution must cross its designated approval/consent boundary.
- Report unresolved shortages with an actionable escalation; never invent coverage.
- Persist approvals, rejection reasons, applied steps, outcome and partial failures.

**R1-F07 — Actual physical fulfilment**
- Record receipt at a known site, with source lot, arrival time, expected vs received and evidence references.
- Record accepted/rejected grade quantities and reasons, and prevent shipment composition using rejected amounts.
- Capture shipment, dispatch, delivery and buyer-confirmation milestones with separate, verifiable data.
- Receipt does not equal acceptance; dispatch does not equal delivery.

**R1-F08 — Reconciliation and trade history**
- Compute variances across requested, committed, received, quality-accepted, delivered and buyer-confirmed quantities.
- Prevent evidence-backed "completed" claims until required delivery/confirmation conditions are present.
- Capture unresolved disputes and correction records without altering prior events.
- Derive auditable trade-history entries only from supported reconciliation, with no claim of creditworthiness.

**R1-F09 — Agent task lifecycle**
- Persist agent triggers, task goals, inputs, permitted tools, planned actions, tool results, decision summary, approval status and terminal state.
- Define explicit statuses: queued, running, awaiting_approval, awaiting_external_input, completed, escalated, failed, cancelled.
- Persist enough state to resume after restart; make retries idempotent and bounded.
- Use language models only for interpretation/draft communication/planning proposals; quantities and permissions stay deterministic.
- Add a real task queue/outbox (or equivalent reliable persisted job mechanism). Avoid frontend-only timers masquerading as background work.

**R1-F10 — Operational UI**
- Task-centric surfaces: Inbox/Orders, Order Detail (demand → commitments → exceptions → physical fulfilment → evidence), Supply Lots, Needs Attention / Agent Work Queue, Receiving, Activity & Audit.
- Every primary interaction is a real backend command and has loading/error/empty/conflict states.
- Indicators must show declared/verified and synthetic/live provenance. No ornamental data cards lacking operational utility.

## 4. Architectural boundaries

Existing stack to preserve where applicable: Next.js/React/TypeScript frontend, Python/FastAPI/SQLAlchemy backend, PostgreSQL domain store and Supabase live authentication (based on earlier repository reports; confirm against current repository before changes).

- Domain APIs remain source of truth for all valid state transitions and quantities.
- Transactional outbox/event log records domain events atomically with business mutations.
- Agent orchestrator subscribes/polls durable events, loads scoped evidence and builds constrained action proposals.
- Tool gateway validates permissions, idempotency keys and policy for every external/domain action.
- Approval service records authorized review, actor and exact proposal hash before execution.
- Audit service stores append-only events, including source and correlation IDs.
- Read models support clear current status and history; never infer official certification from an agent draft.

Existing backend entities and API names must be inspected before finalizing schema. Prefer additive migrations to destructive rewrites.

**Suggested domain events:** order.created, order.updated, lot.capacity_changed, allocation.proposed, solicitation.sent, supplier.accepted, supplier.declined, allocation.lost, requirement.at_risk, recovery.proposed, recovery.approval_requested, recovery.approved, standby.activated, recovery.escalated, receipt.recorded, quality.inspected, shipment.dispatched, delivery.confirmed, reconciliation.completed.

Every event: unique ID, tenant ID, aggregate type/ID, actor type/ID, type, timestamp, payload schema version, correlation ID, causation ID, idempotency key and tamper-evident / immutable storage policy as appropriate. Do not claim cryptographic immutability unless implemented and verified.

## 5. Required agentic proof

1. Create new order and real supplied lots via normal UI; no seeded scenario IDs.
2. A supplier commitment changes independently (API/user action), creating a persisted requirement.at_risk event.
3. A background agent task is created automatically and resumes even if the user closes the page.
4. Agent invokes read-only tools to gather order, capacity and eligibility; asks the deterministic planner for bounded options.
5. Agent persists a recommended proposal with evidence and identifies whether approval is required.
6. Coordinator approves or rejects the exact proposal; the tool gateway checks current stock again and applies it atomically if still eligible.
7. Agent records outcome or re-plans/escalates if underlying data has changed.
8. A second session or browser refresh sees consistent state and an attributable agent timeline.

Failure behaviour is first-class: no authorized alternative, a supplier refusal, expired quote, stale stock, unreachable service, duplicated event, or partial tool failure must resolve into a truthful, recoverable state.

## 6. One adversarial acceptance story (must pass)

Create an unfamiliar 730 kg Grade A scotch bonnet buyer requirement with new suppliers, distinct lot capacities and valid dates. Establish exactly 730 kg of confirmed commitments and 80 kg authorized standby. Later, a real supplier update reduces committed coverage by 110 kg: the order becomes 620/730 kg committed and 110 kg short. The system detects it without a button press. Only 80 kg eligible standby can be activated, leaving 700/730 kg and a 30 kg escalation. After another supplier explicitly accepts 30 kg, committed coverage becomes 730 kg.

Physically receive 725 kg, inspect 705 kg accepted + 20 kg rejected, and obtain buyer confirmation for no more than the actually delivered/accepted quantity. The system must not claim 730 kg delivered, and the reconciliation must preserve a remaining 25 kg difference from required to accepted. Evidence belongs to the actual participating lots. Repeat across refresh and separate user sessions.

The 500 kg ginger demo may remain as a separate fixture, but cannot be the only working flow.

## 7. Non-functional acceptance gates

- **Integrity:** zero over-reservations in concurrent multi-order tests; all commands idempotent; transactional rollback.
- **Auth:** tenant isolation, permission denial, action attribution, scoped agent tools; no insecure demo auth in live mode.
- **Resilience:** durable jobs and audit across process restart, bounded retry, dead-letter/escalation and replay protection.
- **Verification:** backend unit/integration, PostgreSQL concurrency, frontend contract and actual browser E2E with two sessions; reproducible test logs.
- **UX:** a non-developer can create and work an unknown order; readable statuses, responsive mobile field interactions, accessible forms/errors.
- **Truth:** separate simulated from real data and planning from physical quantities; verified evidence only; unknown is not converted to zero.
- **Performance:** measure and report p95 reads/writes and slow agent steps; set final SLAs only after pilot baselines.
- **Operations:** documented migrations, seed/test fixtures, backups/restore, logs/traces and local startup.

## 8. Work packages (execute in this order)

- **WP0 — Current-repository reality audit:** inventory route→API→service→DB path; identify reusable domain code, coverage gaps, tests and incompatible docs; run current baseline, flag unexecuted checks. Make an incremental migration plan.
- **WP1 — Order and lot creation without fixtures:** tenant-scoped CRUD/API/UI, validation and persistence for new buyer orders, growers and lots.
- **WP2 — Commitment and reservation flow:** candidate planning, solicitation/acceptance, protected standby, real multi-order contention.
- **WP3 — Durable agentic exception engine:** event capture/outbox, agent task state machine, read/evaluate/propose, policy/approval, bounded recovery/escalation.
- **WP4 — Physical fulfilment and reconciliation:** receipt/grading/shipment/delivery/buyer evidence; accurate trade reconciliation.
- **WP5 — Independent user workflow and operational UI:** consolidate existing pages into a cohesive task-oriented interface grounded in real actions; no redesign until workflows are proven.
- **WP6 — Adversarial verification and pilot-readiness:** cold database, fresh unfamiliar inputs, concurrency, failure/restart, two-tenant and two-browser E2E, docs and demonstration.

Each package produces changes on a reviewable branch, migration/release notes, test evidence and a list of unfinished items. Do not turn passing API tests into a claim of completed user acceptance.

## 9. Out-of-scope dependencies and next release

Release 2 introduces commodity/corridor-specific export feasibility: maintained official rules, phytosanitary and other regulatory prerequisites, packing/inspection gates, shipping quotes/schedules, currency and cost responsibility, landed-cost scenarios and verified export document draft packs. R1 data models must permit origin/destination/currency and references to external artifacts without prematurely claiming export compliance.

## 10. Pilot hypothesis and go/no-go

Candidate initial paying customer: existing exporter, producer aggregator or institutional supply coordinator. Test one real recurring requirement, existing supplier network and known fulfilment partner, using shadow mode before authorized live operations.

- **Go:** independent users complete unfamiliar transactions accurately, agent tasks persist and recover, data stays isolated, no fabricated coverage/physical states, and a prospect confirms a costly coordination problem worth testing.
- **No-go:** only seeded scripts work, missing real approvals, false audit claims, unresolved tenant isolation or inability to distinguish promised from delivered supply.

---

## Execution brief (summary)

- Work on branch `feat/r1-trade-core`; never discard uncommitted work.
- First: inspect, run every available baseline, and record skipped gates; write `docs/product/R1_REALITY_AUDIT.md` and `docs/product/R1_DELTA_PLAN.md`.
- Then implement WP1 as the smallest genuine vertical slice, then WP2, and WP3 only once normal actions and reservation invariants pass.
- Never: produce success without persisted facts; collapse solicitation/acceptance, standby/commitment, commitment/receipt, receipt/acceptance or dispatch/delivery; fabricate rules, delivery proof, finances, capacity or sensor evidence; bypass human approval for consequential trade actions; weaken tenant or reservation guards to make a demo pass; hide failing tests or claim unrun code ran.
- Stop and present a plan and backups before any sensitive or destructive migration.
- Return to the founder after each work package with changed files, the implemented journey, real screenshots only, test commands and results, limitations, risks and the next package.
