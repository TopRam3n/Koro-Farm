# R1 — WP3 report: recovery agent, human approval and the execution gateway

**Scope:** your WP3 product-owner decisions and technical review of 31 October 2026, built on the verified WP2 branch.
**Status:** built and tested; not merged; not deployed. Verification and CI: [R1_WP3_HANDOFF.md](R1_WP3_HANDOFF.md). Deferred items: [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md).

## What happens now when supply fails

1. **Detection is deterministic and durable.** The incident and an actionable exception are recorded together in one transaction, with the exception's outbox event. The exception kinds:
   - capacity shortfall (WP2);
   - supplier dropout (new): recorded at once;
   - quality rejection (new): recorded with the grade, and grading never waits;
   - overdue reply;
   - standby expiry.
2. **The worker opens a recovery task**, or adds the incident to the order's existing one. There is one active task per order.
3. **The deterministic tools compute the position and the options:** the shortfall, what can be released or activated, eligible supply, and the costs. The decider chooses one offered option and explains it. The decider is either the optional model or the deterministic rules.
4. **The proposal is stored immutably with its SHA-256 hash** and waits for approval on Needs attention and on the order page.
5. **A person approves the exact hash.** An elevated proposal needs a second, different person with elevated authority.
6. **The gateway, in the worker, re-verifies everything under row locks and applies the actions.** If anything has changed, it refuses the approval as stale and the task re-plans.
7. **The task moves on:**
   - it waits for supplier answers, because a request is never supply;
   - it completes when the order is covered;
   - or it escalates the remainder to a coordinator.

## Product-owner decisions, as built

### 1. Unapproved activation removed from the domain, not just the UI

| Former path | Now |
|---|---|
| `recover_quality_shortfall()`, called from grading | Removed. `record_quality_shortfall()` records the incident, the at-risk state, the recovery run and a `QUALITY_REJECTION` exception. It never activates or asks |
| `dropout(auto_recover=True)` / `defer_recovery=false` | The `auto_recover` parameter is gone. `defer_recovery=false` is refused with 422. Dropout records a `SUPPLIER_DROPOUT` exception |
| `POST /requirements/{id}/recovery` → `continue_recovery()` | `continue_recovery()` is removed. The endpoint now only asks the agent to plan (202) and needs `recovery.propose` |
| Automatic solicitation in the old recovery code (reserved stock, no deadline) | Removed. New supplier requests are issued only by the gateway from an approved proposal, through the normal in-app solicitation with a deadline |

Enforcement:
- `gateway.py` is the only module that sets `ACTIVATED`. A static test parses every module to check this (`test_only_the_gateway_can_activate_standby`).
- The gateway's action functions refuse to run without a verified `Authority` for an approved proposal containing that exact action.
- Dropout and grading also gained the permission checks they lacked: `supply.manage` for dropout; `receiving.record` and `grading.record` for receiving and grading. Before this, any staff role, auditors included, could call them.

### 2. Role policy

| Role | Propose / ask the agent to plan | Approve ordinary | Approve elevated | Execute |
|---|---|---|---|---|
| Supply coordinator | yes | yes | — | — |
| Procurement manager | yes | yes | yes | — |
| Organization administrator | — | yes | yes | — |
| Platform administrator | yes | yes | yes | — |
| Warehouse operator, auditor, farmer, buyer | — | — | — | — |

- **Ordinary proposals** need one approver. The cost must be known, and the landed-cost increase over the order's current cost per kg must be zero or within the organization's tolerance.
- **Elevated proposals** need two different approvers, at least one holding `recovery.approve_elevated`. A proposal is elevated when:
  - the cost is unknown (a lot has no cost inputs, or the order has no cost baseline);
  - it exceeds a tolerance;
  - or no tolerance is set and the cost rises at all.
- **The tolerance:** organization administrators set it as versioned rows (`POST /recovery-approval-policy`). Each proposal binds the version it was evaluated under. At execution the gateway re-evaluates under the current version, so a tightened tolerance refuses an approval that is no longer sufficient (tested).
- **Separation of duties:** the agent proposes, people approve, and the gateway executes. No user role holds `recovery.execute`, platform administrators included, and no API endpoint executes. The gateway's authority comes only from approvals it re-verifies:
  - each approver must still be an active member;
  - each approver's current role must still grant what was counted for them;
  - the remaining valid approvals must still satisfy the tier.
- **The matrix is tested explicitly** in `test_recovery_role_policy_is_explicit`.

### 3. Language model with controlled autonomy

- **The adapter** (`agents/infrastructure/model.py`):
  - uses Claude (`claude-opus-5-5` by default) through the official SDK;
  - constrains the response to a JSON schema;
  - is optional: `pip install ".[model]"`, with `AGENT_MODEL_PROVIDER=anthropic`.
- **What the model may do:**
  - choose one offered option id;
  - explain the choice;
  - recommend escalation or more information;
  - draft supplier requests and a buyer update.
- **What it cannot do:** add, change or resize an action. It never sees a tool that writes.
- **Validation** (`decision.validated`) runs on every answer:
  - an option that was not offered is replaced by the deterministic choice;
  - a rationale or draft citing a number that is not in the evidence is withheld;
  - drafts are limited in length and kept as drafts.
- **What is sent:** pseudonymous supplier labels (S1, S2), parishes, quantities, costs and dates. No names, identifiers or contact details. Incident notes are passed as untrusted data, and the prompt says so.
- **Fallback:** any failure (no credentials, timeout, refusal, truncation, invalid JSON) falls back to the deterministic decision, and the reason is recorded in the proposal.
- **Production is disabled twice:**
  - the API and worker refuse to start with `AGENT_MODEL_PROVIDER` set in production;
  - the adapter returns the deterministic decider there regardless.
- **Testing:**
  - CI uses scripted clients only (`test_recovery_model.py`), covering misleading input, prompt injection, invented figures, invalid options and failures.
  - Real model-on evaluation is a separate script (`scripts/evaluate_recovery_model.py`). It runs eight synthetic cases, five of them misleading or injection cases, and reports raw model behaviour and the validated outcome separately.
  - **No real model run has happened yet**: this environment has no Anthropic credentials. See the handoff.
- **Server-side refusal fallback** is deliberately not enabled. A silent switch to another model would blur the evaluation, and a refusal already falls back to the deterministic decision.

### 4. Supplier contact

- An approved `SOLICIT_SUPPLY` action creates a proposed allocation and calls the existing in-app solicitation, with the default reply deadline. The request text the approver saw is bound into the proposal hash.
- The supplier still accepts or declines explicitly, and only acceptance is supply.
- Silence expires the request, as in WP2.
- Nothing is sent by WhatsApp, SMS or email. Model drafts are labelled "Draft only. Not sent to anyone".

## Mandatory engineering requirements

| Requirement | How | Evidence |
|---|---|---|
| Durable triggers for dropout and quality rejection | The exception and outbox event are written in the incident's own transaction. The worker turns `exception.opened` into a task | `test_legacy_recovery_endpoints_record_and_queue_but_never_execute`, `test_grading_is_recorded_at_once_and_opens_an_actionable_incident`, `test_fulfilment.py` |
| Simultaneous exceptions on one order cannot both claim a quantity | One active task per order (partial unique index). Each plan covers the order's whole current shortfall: required − (committed cover − exposed) − requests in flight. The gateway refuses replacements larger than the current need | `test_simultaneous_exceptions_on_one_order_share_one_task_and_one_quantity`; PostgreSQL: three concurrent workers create one task |
| Approvals bound to immutable content; revalidated; stale refused | The canonical-JSON SHA-256 covers actions, quantities, consent ids, authorization dates, costs, request text, policy version and expiry. Approve and reject require the hash. The gateway re-checks the hash, approvers, tier, policy, expiry, order state, and every precondition under locks | `test_approval_is_bound_to_the_reviewed_hash…`, `test_gateway_refuses_when_the_approver_lost_their_membership`, `test_stock_taken_after_approval_is_refused_and_replanned`, `test_a_cost_tolerance…`, `test_an_expired_approval_window…`; PostgreSQL race `test_stock_taken_between_approval_and_execution…` |
| Transaction safety, idempotency, tenancy, immutable records, truthful partial failure | Each task advance is one transaction under `FOR UPDATE SKIP LOCKED`. Executions are unique per proposal action. Each action runs in a savepoint, so a failure is recorded as FAILED and the proposal as PARTIAL. Path scope covers tasks and proposals (isolation sweep). Steps, proposals, approvals and executions are append-only | `test_two_workers_executing_one_approved_proposal_activate_standby_once` (PostgreSQL), tenant isolation sweep |
| Survives worker restarts without duplicate requests or activation | The worker process was killed mid-execution: the transaction rolled back, and the restarted worker applied each action exactly once | `test_a_worker_crash_mid_execution_repeats_nothing`; replay of every outbox event: `test_replayed_events_open_no_second_task_or_incident` |
| Every decision inspectable on the order timeline and Needs attention | Each proposal shows its actions, residual escalation, cost, approval level and reasons, the alternatives offered, the rationale and who decided, validation findings, and drafts marked not sent. The task timeline lists every step with its actor. Order history includes every `recovery.*` event, with people recorded as users and the agent and gateway as agents | E2E `recovery-approval.spec.ts`, screenshots 13 to 15, `recoveryTasks.test.tsx`, `test_people_and_the_agent_are_attributed_separately…` |
| Monitoring | Overdue recovery tasks and failed tasks that no newer task replaced make monitoring DEGRADED (`recovery_overdue`, `recovery_failed`), in the banner and `/health/worker` | `test_a_failed_recovery_task_degrades_monitoring` |

## Shortfall arithmetic and actions

For one order:
- assured = committed cover (accepted commitments, less rejected produce) − exposed commitments (WP2);
- gap = max(0, required − assured);
- net need = max(0, gap − kilograms requested and awaiting answers).

The action types:

| Action | Effect when applied |
|---|---|
| `RELEASE_EXPOSED` | Records that the committed farmer can no longer supply the exposed part, as their own capacity report says. That part becomes a LOST record and its reservation is released. Always paired with replacement in the same proposal, so the order is never counted twice |
| `ACTIVATE_STANDBY` | Activates standby the supplier authorized, under the same consent record, within the capacity their lot still supports |
| `SOLICIT_SUPPLY` | Asks an eligible supplier through the farmer portal, with a deadline. Reserves nothing; counts only once accepted |

Lots whose supplier declined this order, or whose request a coordinator withdrew, are not asked again by the agent.

## Behaviour changes you will notice

- A dropout or quality rejection no longer recovers by itself. The order shows the exception and an approval-pending proposal. The demo seed now shows that state too.
- Coordinators can now approve ordinary recovery. Procurement managers and organization administrators approve dearer or uncertain-cost recovery as the second approver.
- Grading and receiving need warehouse permissions; dropout needs supply management.

## Known limitations

See [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md). Most relevant to WP3:
- **Item 11:** with the model on, a slow model call holds that task's lock. Supply rows are not locked.
- **Item 8:** orders with binding supply still cannot be cancelled through the API.
- **Model-on evaluation:** the harness is built and tested, but no real model run has happened yet, because no credentials are available.
