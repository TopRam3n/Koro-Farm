# R1 — WP3 proposed architecture: event-driven agent orchestration with human approval

**Status:** proposal for your review. Nothing here is implemented. No autonomous supplier activation will be built without your explicit authorization.
**Builds on:** WP1 (tenancy, consent, reservations) and WP2 (capacity reports, exposure, deterministic exceptions, outbox worker, monitoring).
**Spec references:** R1-F06 (recovery and escalation), R1-F09 (agent task lifecycle), section 4 (architectural boundaries), section 5 (agentic proof), section 6 (adversarial story).

## 1. Principles

1. **Detection stays deterministic.** WP2's worker opens exceptions. The agent never decides whether something is wrong; it starts from an exception that already exists.
2. **The agent proposes; deterministic services decide what is possible; a person approves; the gateway executes.** A language model may interpret, plan within offered options, and draft messages. It never computes quantities, eligibility or permissions, and it never calls a domain service directly.
3. **Every effect crosses one gateway.** The tool gateway is the only path from an agent task to a domain change. It enforces tenant scope, permission, idempotency, policy, and a fresh feasibility check at execution time.
4. **Approval binds to an exact proposal.** A reviewer approves a proposal hash. If anything material changes before execution (stock, consent, order terms), the approval no longer applies and the task re-plans.
5. **Truthful terminal states.** No alternative, supplier refusal, stale stock, expired authorization, duplicate event, partial failure: each ends in a recorded, recoverable state, never invented coverage.

## 2. Components

| Component | Responsibility | Where |
|---|---|---|
| Exception events (exists) | `exception.opened` / `exception.updated` / `exception.resolved` written with the outbox by WP2 | `assurance/application/exceptions.py` |
| **Task orchestrator** (new) | Subscribes to exception events through the existing worker; creates or resumes one agent task per open exception; drives the task state machine step by step, persisting after every step | New `agents/application/orchestrator.py`, run by `app/worker.py` |
| **Read tools** (new) | Scoped, read-only queries: order and terms, assurance figures, exposure by lot, eligible standby, eligible unreserved lots, supplier history | `agents/tools/read.py` |
| **Planner tool** (exists, wrapped) | Deterministic bounded options: activate authorized standby, solicit new supply, partial cover plus escalation. Returns quantities, cost and risk; the agent cannot alter them | Wraps `supply/application/planner.py`, `risk`, `economics` |
| **Proposal store** (new) | Immutable proposals: options considered, chosen option, evidence references, exact actions, approval requirement, canonical hash | `agents/domain/proposals.py` |
| **Approval service** (new) | Records reviewer, decision, reason and the hash approved; enforces who may approve what (policy) | `agents/application/approvals.py`; reuses `APPROVAL_POLICY_*` permissions |
| **Tool gateway** (new) | Executes an approved action list: re-checks tenancy, permission, policy, idempotency and current feasibility under row locks, then calls the existing domain commands in one transaction per action | `agents/application/gateway.py` |
| **Model adapter** (new, optional) | Interpretation, choice among planner options, draft supplier and buyer messages. Behind an interface with a deterministic fallback, so tasks still complete with the model off | `agents/infrastructure/model.py` |
| **Agent timeline read model** (new) | Attributable history per order and per task for the UI | `agents/api/router.py` |

## 3. Task state machine (R1-F09)

```
queued -> running -> awaiting_approval -> running -> completed
                 \-> awaiting_external_input (e.g. a solicited supplier's reply) -> running
                 \-> escalated   (no feasible option, or residual shortfall after applied steps)
                 \-> failed      (bounded retries exhausted; reason recorded)
any non-terminal -> cancelled   (exception resolved by other means, order cancelled, or coordinator cancels)
```

- **One active task per exception.** This is enforced like WP2's dedupe: a partial unique index on `(exception_id) WHERE status not in terminal`.
- **Each step is persisted before the next starts:** its inputs, its tool calls and results, and a decision summary. After a restart the orchestrator resumes from the last completed step. A replayed event finds the active task and does nothing.
- **Bounded:** a maximum number of steps per task, a maximum number of re-plans, retries with backoff, and dead-lettering into the same monitoring that WP2 added.
- **Reconciles with the exception.** If the exception resolves while a task is waiting, for example because the supplier restored capacity, the task is cancelled with that reason.

## 4. Data model (additive migrations)

| Table | Key fields |
|---|---|
| `agent_tasks` | id, organization_id, exception_id, requirement_id, goal, status, step, attempts, model_used, created/updated, terminal_reason |
| `agent_steps` | task_id, sequence, kind (read / plan / propose / execute / wait), input, output, started/finished, error |
| `agent_proposals` | task_id, version, options (planner output), chosen_option, actions (exact list), evidence_refs, requires_approval, policy_reason, canonical_hash |
| `agent_approvals` | proposal_id, hash, decision (approved / rejected), reason, reviewer_user_id, decided_at |
| `agent_executions` | proposal_id, action_index, idempotency_key, outcome (applied / refused_stale / refused_policy / failed), detail |

Every row carries organization_id. Events (`recovery.proposed`, `recovery.approval_requested`, `recovery.approved`, `recovery.rejected`, `recovery.applied`, `recovery.escalated`) go through the existing event and outbox path, so they appear in order history and the audit trail.

## 5. Tools and the gateway

| Tool | Kind | Approval |
|---|---|---|
| Read order, figures, exposure, eligible standby and lots | read | none |
| Ask planner for options | read (deterministic) | none |
| Draft message to supplier or buyer | draft only (stored, not sent) | none |
| Solicit an additional supplier (creates a request; nothing reserved) | write | **coordinator approval** (proposed default) |
| Activate authorized standby (reserves stock under existing consent) | write | **coordinator approval required.** No autonomous path unless you authorize one |
| Escalate (mark unresolved shortfall, notify) | write | none: escalation never claims coverage |
| Change order terms, cancel, withdraw commitments | — | **not available to the agent** |

At execution time the gateway:
1. Verifies the approval hash matches the proposal's.
2. Locks the affected rows (lot, allocation, requirement) in a fixed order and re-runs the feasibility checks: free stock, authorization validity, consent state, order status.
3. Applies each action through the existing domain command, with an idempotency key derived from (proposal, action index).
4. Records the outcome per action.

A stale check refuses that action and moves the task back to `running` to re-plan; actions already applied stay applied and are recorded. That is the spec's "partial tool failure resolves truthfully".

## 6. Human approval UX

- Proposals appear on **Needs attention** and on the order page under the exception. Each shows the chosen option, the alternatives the planner offered, quantities and cost, the evidence, and which approval policy applies.
- **Approve** submits the hash that was displayed, so approving a proposal that has since changed is refused.
- **Reject** requires a reason, and the task re-plans with that option excluded or escalates.
- The timeline shows every step, tool call and decision with its actor (agent, worker, or named user).

## 7. Decisions needed from you before implementation

1. **Existing automatic standby activation.** Two pre-R1 paths activate pre-authorized standby without a separate human approval:
   - quality rejection during grading (`recover_quality_shortfall`, called from `fulfilment/application/services.py` `grade`);
   - the dropout API when called with `defer_recovery=false`.

   The supplier's standby authorization is consent to be called on, but no coordinator approves the specific activation. Proposal: route both through WP3 proposals and approval, and remove the immediate path. This changes current behaviour, so it needs your authorization.
2. **Who may approve.**
   - Proposal: `SUPPLY_COORDINATOR` and above for standby activation and new solicitations.
   - Also proposed: a configurable second approver above a quantity or cost threshold.
3. **Language model use.**
   - Proposal: optional, used only for choosing among planner options with written rationale, and for drafting messages. Off by default in tests; deterministic fallback.
   - Also needed: the provider and data-handling terms, since order and supplier data would be sent to the model.
4. **Supplier contact.** Proposal: the agent drafts and a coordinator sends, or the request goes through the existing in-app solicitation. No outbound SMS or WhatsApp in WP3 (a later enhancement).

## 8. Acceptance (maps to spec section 5 and the section 6 story)

- **The section 6 adversarial story end to end through the UI**, with the worker and orchestrator running:
  - 110 kg capacity cut detected;
  - task created automatically;
  - proposal to activate 80 kg of authorized standby; coordinator approves;
  - 30 kg escalation;
  - a new supplier accepts 30 kg;
  - 730 kg committed;
  - then receipt, grading and reconciliation preserve the 25 kg difference.
- **Restart resilience:** kill the worker mid-task; the task resumes from its last step; no duplicate actions.
- **Stale approval:** stock consumed between proposal and approval leads to refusal and a re-plan, never an over-reservation (a PostgreSQL concurrency test).
- **Duplicate and replayed events** create no second task and no second action.
- **Tenant isolation:** tasks, proposals and approvals are added to the isolation sweep. A reviewer in another organization cannot approve.
- **Model off:** every acceptance test passes with the model adapter disabled.
- **Staging Supabase verification** remains a separate, mandatory release gate.

## 9. Proposed sequence

1. Data model, state machine and orchestrator with read and planner tools only; tasks reach `escalated` or `awaiting_approval` (no writes).
2. Proposal store, approval service and gateway with the standby-activation and solicitation actions, behind approval.
3. UI: proposals on Needs attention and the order page, and the agent timeline.
4. Optional model adapter for option choice and message drafting.
5. Adversarial story E2E, restart and stale-approval tests, clean-checkout verification, handoff.
