# KoroFarm capability architecture

KoroFarm uses the word *agent* only for capabilities that observe state,
select bounded actions, and can coordinate more than one service. Deterministic
calculators remain deterministic capabilities even when they participate in an
agentic workflow.

| Capability | Type | Inputs | Outputs | Services/tools | Authority and side effects | Failure and approval behavior |
|---|---|---|---|---|---|---|
| Supply Assurance Orchestrator | HYBRID | requirement, allocations, risk, recovery policy | ordered proposed actions and escalation | planner, recovery coordinator, compliance resolver, event/outbox | may propose; execution is delegated to governed domain commands | stops on missing state, timeout, failed command, or required approval; never exposes private reasoning |
| Demand Interpreter | LLM_ASSISTED | buyer text or structured request | schema-valid requirement draft plus ambiguity/missing-field list | constrained schema validation; optional configured model | draft only; cannot approve, plan, or reserve supply | unsupported information remains unasserted; human review required before approval |
| Supply Planner | DETERMINISTIC | approved requirement, eligible lots, costs, consent, policy | immutable plan, committed and standby allocations | SQLAlchemy/PostgreSQL row locks, landed-cost calculator | reserves eligible capacity in a transaction | rejects double planning; incomplete capacity produces AT_RISK |
| Risk Engine | DETERMINISTIC | immutable plan and allocation structure | LOW/MEDIUM/HIGH snapshot and triggered rules | `risk-v1` policy | writes an immutable snapshot; no predictive or farmer-scoring authority | boundary values are exact and reproducible |
| Recovery Coordinator | DETERMINISTIC | loss/quality event, standby, free lots, approval policy | proposed/approved/executed recovery or escalation | recovery service, planner snapshots, events/outbox | proposes by default; executes only authorized standby or accepted solicitation within policy | insufficient/unauthorized supply escalates; never invents coverage |
| Compliance Resolver | DETERMINISTIC | organization, route, commodity, product form, effective date | matching verified rules or `NO_VERIFIED_RULE_ON_FILE` | stored compliance registry only | read-only resolution; cannot claim compliance | missing, expired, mismatched, or unverified evidence returns the explicit unsupported state |
| Fulfilment Monitor | DETERMINISTIC | allocations, receipts, grades, shipment and delivery states | physical-flow state and exceptions | receiving, grading, shipment, delivery services | records explicit commands; cannot convert commitment into accepted supply | rejects quantities beyond allocation/acceptance and keeps dispatch distinct from delivery |
| Evidence Builder | DETERMINISTIC | trace chain, delivery, buyer confirmation, reconciliation | structured trade evidence/passport state | reconciliation and traceability queries | issues evidence only from verified reconciled data | refuses before reconciliation or with incomplete confirmation/evidence |

## Structured rationale policy

Operator surfaces may show inputs used, policy version, rules triggered, tool or
service activity, resulting state, and evidence references. They must not store
or display private chain-of-thought. LLM prompts, model identifiers, and costs
are evaluation metadata where an LLM-assisted capability is actually enabled.
