# R1 delta plan

**Based on:** [R1_REALITY_AUDIT.md](R1_REALITY_AUDIT.md) and [KoroFarm_R1_Functional_Trade_Core_Spec.md](KoroFarm_R1_Functional_Trade_Core_Spec.md)
**Branch:** `feat/r1-trade-core` (from `main` @ `731c459`)
**Rule throughout:** additive migrations; existing tables, constraints, locks and tests are kept. Nothing below drops a column or table, or rewrites history.

## Decisions needed from the founder before or during WP1

| # | Decision | Recommendation |
|---|---|---|
| D1 | **PostgreSQL test URL.** The local service on port 55432 rejects the CI credentials, and spec §7 makes PostgreSQL verification a gate | Provide a `POSTGRES_TEST_DATABASE_URL` for a throwaway database. Until then, WP1 can be built and tested on SQLite but **cannot be called verified** |
| D2 | **Crop catalogue.** The `crop` enum is a fixed list, and the column is `VARCHAR(6)` in migrated databases (audit C6) | WP1 migration `0015` widens `crop` to `VARCHAR(40)` on the three tables and adds `SCOTCH_BONNET`. This is safe and additive: widening a VARCHAR keeps existing data. A tenant-managed crop catalogue can wait until a real customer asks |
| D3 | **Supplier capacity reductions** are currently refused with a 409 when they would go below reserved stock (audit C3) | In WP3, a supplier's reduction is *recorded* as a fact (`lot.capacity_changed`), and any commitment it breaks becomes an `allocation.lost` and an exception. Rejecting reality hides exposure. **This changes an existing guard, so it needs your approval before WP3.** The reservation invariant itself (`reserved ≤ available` for *active* reservations) stays enforced |
| D4 | **Planner semantics.** `finalize_plan` commits supply and fabricates consent (audit C2) | In WP2 the planner produces a *proposal* (`PROPOSED` allocations, no committed coverage); quantities become `COMMITTED` only on supplier acceptance, and `STANDBY` only on a recorded standby authorization with evidence. The 500 kg demo fixture keeps working through the seed, which will write real acceptance and authorization records instead of `uuid4()` |
| D5 | **Film and judges' materials** claim recorded farmer consent | Correct `02-TECHNICAL-TRUTH.md` and `10-JUDGES-TECHNICAL-EVIDENCE-WALKTHROUGH.md` now, before they are shared, regardless of R1 timing |
| D6 | **Merging `19d6b82`** (Intelligence Lab, on the feature branch only) | Leave it out of R1; merge separately when you choose |

## WP0 follow-ups: fixes needed to have a trustworthy baseline (part of WP1)

1. **Build is red on `main`:** `src/pages/Profile.tsx:17` uses `replaceAll` against `lib: ES2017` (`tsconfig.json`). Fix by raising `lib` to include `ES2021`. Run `tsc` and `next build`.
2. **Tenant scoping (audit C1)** on every endpoint WP1 touches or exposes: requirement assurance read, events, risk; the registry's farmers, allocations, activity and command-center summary. Each gets an organization filter through the existing `AuthorizationContext` pattern, plus **cross-tenant negative tests** that use two real organizations rather than the conftest override. The remaining routers (allocations, fulfilment, reconciliation, programmes, corridors) are scoped in WP2 and WP4 as those packages touch them. Any route still unscoped stays listed as a release blocker.

## WP1: order, buyer, supplier and lot creation without fixtures

**User journey:** a coordinator signs in, picks their organization, then:
1. creates a buyer;
2. creates an order for an unfamiliar crop with full terms;
3. creates two suppliers and their lots, entered on their behalf with provenance and marked *declared*;
4. edits the order within policy, with every change visible in history;
5. refreshes the page, or opens a second authorized session, and sees the same persisted state;
6. confirms that a user in another organization sees none of it.

### Backend (additive)

| Change | Where | Notes |
|---|---|---|
| Migration `0015_r1_order_and_lot_fields` | `src/backend/alembic/versions/` | Widen `crop` (D2). `requirements`: add nullable `product_form`, `quantity_unit` (default `kg`; R1 supports kg only and rejects others explicitly), `origin`, `destination`, `delivery_terms`, `currency`, `notes`, `source`, `created_by_user_id`, `cancelled_at`, `cancellation_reason`. `production_lots`: add `declared_quantity_kg`, `capacity_verification` (`DECLARED` / `VERIFIED`), `provenance_source`, `attestation_method`, `recorded_by_user_id`. `domain_events`: add nullable `organization_id`, `actor_id`, `causation_id`, `schema_version`, `idempotency_key`, with an index on `(organization_id, occurred_at)` |
| `POST/GET /buyers`, `GET /buyers/{id}` | new `demand/api/buyers.py` | Tenant-scoped; `buyer.created` event |
| `POST /farmers` (coordinator), `GET /farmers` scoped | `supply/api/router.py` | `farmer.created` event with actor; replaces the unscoped registry list for R1 screens |
| `POST /production-lots` (coordinator on behalf) | `supply/api/router.py` | Requires `provenance_source`, `attestation_method` and timestamp. Lot is `DECLARED` with `availability_confidence` LOW, and is **not** marked independently confirmed. Reuses the ingestion `_record` provenance writer. `lot.created` event |
| `PATCH /requirements/{id}` | `demand/api/router.py` | Field-level edits allowed only before any plan exists. After that, only via `buyer-change` (quantity) or cancel. Optimistic concurrency on `version` (409 on stale). Writes `order.updated` with before/after |
| `POST /requirements/{id}/cancel` | `demand/api/router.py` | Allowed only before commitments exist in R1 (later states escalate). `order.cancelled` event |
| `GET /requirements/{id}/history` | `demand/api/router.py` | Tenant-scoped event list with actor, plus `BuyerOrderChange` rows |
| Event writer helper | `assurance/application/events.py` (new) | One function used by all new commands: fills tenant, actor, correlation and causation ids, schema version and idempotency key; writes `DomainEvent` and `OutboxMessage` in the same transaction |
| `Idempotency-Key` on every new create command | — | Reuses `CommandDeduplication`, scoped by organization |

### Frontend (functional, no redesign)

| Change | Where |
|---|---|
| Organization comes from the signed-in user's memberships (`GET /me`), replacing the build-time `NEXT_PUBLIC_ORGANIZATION_ID` in live mode | `lib/api.ts`, `hooks/useIdentity.ts` |
| `/orders`: list with an empty state, and "New order" | new `app/orders/page.tsx` |
| `/orders/new`: form with server-side validation errors shown inline; no optimistic success, navigation only after a 201 | new |
| `/orders/[id]`: order detail, edit (within policy), cancel, history. Reuses the existing requirement dashboard by passing the route id instead of `NEXT_PUBLIC_REQUIREMENT_ID` | `app/requirements/[id]` → shared component |
| `/suppliers`: farmers and lots, with create forms; lots show **Declared** vs **Verified** | new |
| "Simulate dropout" shown **only** when `NEXT_PUBLIC_APP_MODE=demo` | `components/DemoControls.tsx` |

### WP1 tests and evidence

- **Backend:** create, read, update and cancel for buyers, farmers, lots and orders. Validation failures. Stale-version 409. Idempotent retries. History content. **Cross-tenant negative tests with two organizations** for every new and newly scoped endpoint: list, detail, update and indirect id.
- **PostgreSQL:** run the existing 9 concurrency tests plus WP1 persistence tests against D1's database.
- **Frontend:** `vitest` for forms and error states; `tsc`; `next build`.
- **Browser E2E:** with Playwright, two contexts (coordinator in org A, coordinator in org B): create an unfamiliar order, buyer and lots → reload → second org-A session sees the same state → org-B session sees nothing. Screenshots are attached only if actually captured.

**WP1 does not include:** planning, commitments, recovery, fulfilment or any agent behaviour.

## WP2: commitments and reservations

- The planner returns a proposal: deterministic eligibility and scoring are kept, and output is `PROPOSED` allocations with an explanation (which constraints passed, and why each lot was chosen). **No `reserved_quantity_kg` change at proposal time.** This needs a decision on soft holds: either none (recommended for R1), or explicit, expiring holds.
- `POST /allocations/{id}/solicit` → `solicitation.sent`. The supplier (farmer role, scoped to their own allocations) accepts or declines. Coordinator entry on the farmer's behalf requires attestation and is labelled as such. Acceptance re-checks capacity under a row lock, reserves, sets `COMMITTED` and writes `supplier.accepted`. Timeout (via the WP3 worker) and withdrawal are recorded explicitly.
- **Standby authorization record:** a new table holding supplier, lot, quantity, validity window, evidence reference, recorded-by and attestation. This replaces `consent_evidence_id=uuid4()`. Activation consumes the authorization.
- **Multi-order contention:** the existing PostgreSQL tests, plus requirement-vs-requirement and requirement-vs-marketplace contention for the same lot.
- **Scope** allocations, programmes and corridors to the tenant.

## WP3: durable exception orchestration

**What is deterministic and what would use a language model**

| Step | Implementation | LLM? |
|---|---|---|
| Detect exposure from events (`lot.capacity_changed`, `supplier.declined`, solicitation timeout, `quality.inspected` with rejection) | Deterministic detector in a worker | No |
| Open exception, compute shortfall | Deterministic | No |
| Gather order, capacity and eligibility | Read-only tools that call the domain services | No |
| Generate recovery options (standby first, then eligible unreserved lots) | Existing deterministic planner and recovery arithmetic | No |
| Proposal with evidence and approval requirement | Deterministic policy | No |
| Draft a supplier solicitation message or a human-readable summary for the coordinator | **Optional** LLM, clearly labelled as a draft; never changes quantities, permissions or status. Off by default and not required for the acceptance story | Yes, optional |
| Approval of the exact proposal (proposal hash) and atomic apply with stock re-check | Approval service plus tool gateway | No |
| Re-plan or escalate when data changed | Deterministic | No |

**Mechanics**
- An outbox worker process (`python -m src.backend.app.worker`) claims outbox rows with `SELECT … FOR UPDATE SKIP LOCKED`, with bounded retries and a dead-letter status.
- An `agent_tasks` table with the statuses from spec R1-F09, plus `agent_task_steps` (tool calls and results) and `approvals` (actor, proposal hash, decision, reason).
- Tasks survive restart because state lives in PostgreSQL, not the browser.
- Event-driven, persisted tasks are called a *coordination agent* **only** in the sense of spec §2 ("System Agent: event-driven tool-using service"). Product copy will say it is rule-based unless and until an LLM step exists, and will say exactly which step uses one.

**Prerequisites:** D3 approved; WP1 and WP2 invariants passing on PostgreSQL.

## WP4–WP6

As written in the spec. WP4 reuses the fulfilment and reconciliation modules, adding tenant scoping, buyer-role delivery confirmation, a shipment-composition guard against rejected quantities (to be verified), and the 730 kg acceptance story's reconciliation (725 received / 705 accepted / 20 rejected / 25 kg short of required). WP6 runs the full adversarial story on a cold database across two browsers and two tenants.

## Risks

- **No PostgreSQL verification yet (D1).** Locking and length bugs (C6) are invisible on SQLite.
- **The tenant fix touches many routers.** Every change ships with negative tests; scoping is *added*, never loosened.
- **Changing planner semantics (D4) breaks the current demo assumptions.** Mitigation: the seed writes real acceptance and authorization records, and the demo replay (`lib/demoApi.ts`) is unaffected.
- **Scope creep into redesign.** WP1 adds functional screens using existing components only.
