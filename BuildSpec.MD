# Caribbean Agricultural Supply Assurance Layer

## 1. Product Thesis

We are building an **agentic agricultural supply-assurance and execution layer for the Caribbean**, beginning with Jamaican smallholder agriculture and institutional hotel procurement.

This is **not a marketplace**.

Farmer discovery and buyer matching are not the core product. Existing institutions and systems can already help buyers find farmers.

The harder problem is what happens **after demand exists**:

> How do we turn fragmented, uncertain production from many small farmers into a dependable institutional supply commitment — and preserve that commitment when participants or physical supply fail?

The product takes a buyer requirement, identifies eligible near-term agricultural production, assembles the requirement across multiple smallholder farmers, establishes standby capacity, monitors fulfilment risk, responds to disruptions, coordinates physical aggregation and compliance, reconciles what was promised against what was accepted, and creates auditable trade-performance evidence.

The central product promise is:

> **The institutional buyer experiences one dependable supply programme. Behind it may be dozens of independent smallholder farmers.**

---

# 2. Initial Market Wedge

The MVP is deliberately narrow.

## Geography

Jamaica.

## Buyer

One Jamaican hotel/institutional buyer.

## Product

Fresh ginger.

## Transaction

A recurring or one-off requirement for:

**500 kg Grade A ginger within a defined delivery window.**

## Farmer network

Approximately 10–15 synthetic but realistic Jamaican smallholder farmers.

## Initial operating environment

Domestic Jamaican procurement.

CARICOM/export workflows are architectural extensions, not MVP requirements.

---

# 3. Core Problem

Smallholder agriculture is structurally fragmented.

An institutional buyer may require 500 kg of consistent produce, but individual farmers may only be able to supply:

* 30 kg;
* 50 kg;
* 80 kg;
* 120 kg.

The buyer therefore faces coordination costs and supply risk across many independent producers.

Simply matching the buyer to farmers does not solve:

* uncertain harvest availability;
* farmer dropout;
* partial fulfilment;
* inconsistent quality;
* late delivery;
* correlated geographic risk;
* collection;
* aggregation;
* grading;
* traceability;
* regulatory/compliance requirements;
* buyer changes;
* reconciliation;
* payment evidence;
* long-term supplier performance visibility.

The value of the platform is therefore **supply assurance**, not discovery.

---

# 4. Core Agentic Thesis

There should be **one primary agentic actor**:

# Supply Assurance Agent

Its objective is:

> **Preserve the buyer's confirmed supply SLA under fragmented and uncertain agricultural production.**

Its operating loop is:

```text
OBSERVE
   ↓
ASSESS STATE
   ↓
PLAN
   ↓
ACT
   ↓
MONITOR
   ↓
DETECT EXCEPTION
   ↓
REPLAN
   ↓
VERIFY
   ↓
RECONCILE
   ↓
LEARN
```

The agent should respond to changes in the real operating state rather than merely generate text.

Examples include:

* farmer declines;
* farmer drops out;
* expected harvest quantity decreases;
* production lot becomes unavailable;
* reserve farmer becomes unavailable;
* a received sublot fails grading;
* delivery becomes late;
* buyer modifies confirmed demand;
* compliance requirement cannot be verified.

The agent should use deterministic tools to calculate authoritative quantities, costs and state.

---

# 5. What Is and Is Not an Agent

We should not describe every service as an agent.

## Agent

### Supply Assurance Agent

Persistent goal-driven orchestration.

May:

* inspect requirement state;
* inspect available supply;
* request a supply plan;
* activate standby capacity;
* solicit replacement supply;
* inspect risk;
* respond to fulfilment events;
* escalate to a human;
* explain its decisions.

---

## LLM-Assisted Services

### Demand Interpreter

Converts messy buyer demand such as:

> "Need 500kg Grade A ginger for Friday at the Montego Bay property."

into structured requirements.

The LLM may extract language into structured JSON.

The LLM must not make authoritative quantity calculations.

---

### Farmer Communication Service

May create:

* solicitation messages;
* acceptance confirmations;
* replacement requests;
* coordinator summaries.

---

### Compliance Document Drafting

May transform verified rules into:

* checklists;
* instructions;
* procurement reports;
* draft documentation.

It must never invent regulatory requirements.

---

## Deterministic Services

### Supply Planner

Calculates:

* eligible production;
* committed quantities;
* standby quantities;
* remaining shortfall;
* concentration;
* landed cost;
* replacement plans.

### Risk Engine

Calculates explainable supply-risk indicators.

### Unit Economics Engine

Calculates landed cost and recovery cost.

### Compliance Rules Engine

Selects applicable verified rules.

### Reconciliation Engine

Calculates promised versus delivered/accepted performance.

### Trade Performance Engine

Calculates descriptive fulfilment metrics.

---

# 6. Non-Negotiable Engineering Rules

## 6.1 LLMs Never Perform Authoritative Arithmetic

An LLM may explain a calculation.

It must not determine:

* quantities;
* allocation;
* fill percentages;
* cost totals;
* variances;
* farmer scores;
* reserve requirements;
* shipment totals.

These must be deterministic.

---

## 6.2 Never Invent Compliance Rules

Compliance requirements must originate only from verified stored rules.

Every rule must contain an authoritative source.

If a verified rule cannot be found:

```text
no_verified_rule_on_file
```

is the correct result.

The system must not fall back to LLM memory.

---

## 6.3 Never Claim Verification That Did Not Occur

Examples:

Missing sensor run:

```text
cold_chain_verified = null
```

Missing buyer confirmation:

```text
buyer_confirmed = false/unconfirmed
```

Missing inspection:

```text
inspection_status = unverified
```

Unknown information must remain unknown.

---

## 6.4 Human Authority Gates Must Remain Explicit

Humans retain authority over:

* farmer acceptance/decline;
* material buyer substitutions;
* unresolved shortages;
* compliance/document approval;
* disputed deliveries;
* financing decisions.

---

## 6.5 The Platform Does Not Determine Creditworthiness

The system produces:

> **verified trade-performance evidence**

It does NOT determine whether a farmer qualifies for credit.

Financial institutions independently determine financing eligibility.

The UI should explicitly state:

```text
Financing eligibility: Not assessed
```

---

# 7. Supply Model

The system must distinguish between:

## Typical Production Capacity

What a farmer may generally be capable of producing.

This is descriptive.

It is **not inventory**.

---

## Production Lots

Actual expected agricultural production associated with a harvest window.

A production lot should contain at minimum:

```text
farmer
crop

estimated_harvest_start
estimated_harvest_end

expected_quantity_kg
available_quantity_kg

quality_grade_estimate
availability_confidence

parish/location

status
last_verified_at
```

Supply allocation should use production lots rather than theoretical farmer capacity.

---

# 8. Supply Commitment Model

There are three distinct categories of supply.

## 8.1 Committed Supply

Supply formally allocated to the buyer requirement.

For:

```text
500kg requirement
```

the system should initially commit exactly:

```text
500kg
```

---

## 8.2 Standby / Reserve Supply

Additional identified capacity that may be activated if committed supply fails.

Example:

```text
Required             500kg
Committed            500kg
Standby              120kg
```

Standby supply must NOT be presented as already committed buyer supply.

---

## 8.3 Discovery Pool

Remaining eligible supply that is neither committed nor on standby.

It may be queried during severe disruptions.

---

# 9. Central Demo Failure

The central demo event is:

```text
Buyer requirement: 500kg
Committed supply:   500kg

Farmer drops:        80kg
Remaining supply:   420kg
```

The Supply Assurance Agent must detect the failure.

Expected sequence:

```text
500kg committed
      ↓
80kg dropout
      ↓
420kg remaining
      ↓
SLA = AT_RISK
      ↓
inspect standby
      ↓
activate suitable reserve
      ↓
if still short:
query discovery pool
      ↓
create replacement commitments
      ↓
500kg restored
      ↓
SLA = RECOVERED
```

Example:

```text
Lost supply:              80kg
Reserve activated:        50kg
Replacement solicited:    30kg
Recovered supply:         80kg
Final committed supply:  500kg
```

Every number must be deterministically calculated.

---

# 10. Failure Must Be Truthful

If recovery is impossible, the system must not fake fulfilment.

Example:

```text
ESCALATION_REQUIRED

Required:              500kg
Recoverable supply:    473kg
Remaining shortfall:    27kg
```

The agent should escalate to a human coordinator.

---

# 11. Supply Planning

The initial planner may use a deterministic weighted scoring and greedy allocation algorithm.

Do not spend MVP time building mathematically perfect optimization.

The design should permit later replacement with linear/integer optimization.

Candidate supply should consider:

* crop match;
* harvest window;
* available quantity;
* expected quality;
* availability confidence;
* farmer fulfilment history;
* parish/location;
* transport suitability;
* geographic concentration;
* farmer concentration;
* standby availability;
* landed cost.

New farmers with no history must not automatically be treated as bad farmers.

Use a neutral/default prior.

---

# 12. Correlated Supply Risk

The system must recognize that 10 farmers do not necessarily represent 10 independent risks.

Example:

If 80% of the entire order comes from one parish, a single weather event may threaten most of the order simultaneously.

Initial risk indicators should include:

```text
number of committed farmers
number of reserve farmers

parish concentration

largest single farmer dependency

average availability confidence

standby coverage

replacement depth

historical fulfilment strength
```

A heuristic `supply_risk_score` may be created.

It must be:

* transparent;
* explainable;
* clearly labelled heuristic;
* not represented as a scientifically calibrated probability unless later validated.

---

# 13. Lightweight Unit Economics / Landed-Cost Layer

The supply planner should not only determine whether an order can be filled.

It should estimate whether the resulting plan is economically sensible.

Initial cost components may include:

```text
farmgate produce cost

farmer pickup cost

collection cost

handling / grading cost

packaging cost

transport cost

expected wastage / rejection cost

compliance cost where applicable
```

The engine should calculate:

```text
estimated_total_landed_cost

landed_cost_per_kg
```

---

## Disruption Economics

When the agent replans after a failure, the system should calculate the cost of recovery.

Example:

```text
Original landed cost:       J$186,800

Recovered landed cost:      J$191,400

Recovery premium:            J$4,600

Recovery premium percent:       2.46%
```

This allows the platform to demonstrate not only:

> "We recovered."

but:

> **"We recovered the buyer SLA at a measurable additional cost."**

Future versions may optimize:

> Lowest risk-adjusted delivered cost subject to buyer quality, quantity and delivery constraints.

This deeper optimization is not required for the MVP.

---

# 14. Physical Fulfilment

Software cannot physically aggregate produce.

The domain must represent where physical consolidation occurs.

## Fulfilment Node

A fulfilment node may represent:

* collection centre;
* cooperative;
* consolidator;
* packhouse;
* logistics hub.

The MVP requires only one.

---

# 15. Sublot Traceability

Farmer identity must survive aggregation.

The system must support:

```text
Farmer
  ↓
Production Lot
  ↓
Commitment
  ↓
Received Sublot
  ↓
Weighed
  ↓
Graded
  ↓
Accepted / Rejected
  ↓
Consolidated Shipment
```

A buyer shipment may contain many farmer sublots.

Example:

```text
Shipment HOTEL-001

Farmer F001    55kg
Farmer F002    72kg
Farmer F003    43kg
Farmer F004    64kg
...
Total         500kg
```

The system must always be able to answer:

> Which farmer lots contributed to this shipment?

---

# 16. Quality Failure

A farmer may commit supply successfully but the physical produce may later fail grading.

Example:

```text
Farmer commits:       50kg Grade A

Arrives:              50kg

Accepted Grade A:     20kg

Rejected / Grade B:   30kg
```

The buyer SLA now has a:

```text
30kg quality shortfall
```

That event should be able to trigger the same supply-recovery process used for farmer dropout.

This proves the agent handles physical supply exceptions rather than only simulated participant dropout.

---

# 17. Compliance Layer

The compliance layer should use a verified rule dataset.

Initial rule dimensions should support:

```text
origin
destination
crop
product_form

rule_name

issuing_body

description

required_before

lead_time

effective_from
effective_until

source_citation

source_version

last_verified_at

verified_by
```

For the MVP:

**Domestic Jamaica only.**

The architecture should support future CARICOM/export corridors.

Do not build regional rule coverage during the three-day sprint.

---

# 18. Reconciliation

Delivery must distinguish between:

```text
committed quantity

delivered quantity

accepted quantity
```

Example:

```text
Committed:  60kg
Delivered:  58kg
Accepted:   55kg
```

The system should record these separately.

Reconciliation should determine:

* quantity variance;
* accepted fulfilment rate;
* quality result;
* on-time status;
* buyer confirmation;
* trade value;
* dispute status;
* verification evidence.

---

# 19. Trade Performance Evidence

Successful trades should create auditable farmer performance evidence.

Do not call this a credit history.

The farmer-facing/partner-facing output should be:

# Trade Performance Passport

Possible fields:

```text
completed institutional trades

verified trade value

quantity fulfilment rate

on-time delivery rate

quality acceptance rate

consecutive successful trades

fulfilment reliability index

history maturity
```

Example:

```text
Completed trades:               8

Verified trade value:      J$840,000

Quantity fulfilment:            96%

On-time rate:                   94%

Quality acceptance:             97%

Fulfilment Reliability Index:   95

Status:         ESTABLISHED_HISTORY

Financing eligibility: NOT ASSESSED
```

---

# 20. Fulfilment Reliability Index

Do not call this a credit score.

It is a descriptive supplier-performance metric.

It may initially be derived from:

* quantity fulfilment;
* timeliness;
* quality acceptance.

Its components should remain visible.

Farmers without enough trade history should display:

```text
BUILDING_HISTORY
```

rather than a misleading numerical score.

---

# 21. Buyer Accountability

Farmer performance is not the only source of failure.

The architecture should be capable of representing buyer-caused events.

Examples:

```text
late order change

quantity reduction

cancellation

late acceptance

disputed delivery

payment delay
```

Important rule:

If a buyer confirms 500kg and later reduces the order to 300kg, farmer oversupply resulting from that change must not be recorded as farmer unreliability.

Full buyer-performance scoring is not necessary during the MVP.

The data model should simply avoid incorrectly attributing buyer-caused variance to farmers.

---

# 22. Auditability

Material actions must be explainable after the fact.

Important events should record:

```text
event type

actor

timestamp

previous state

new state

quantity if relevant

reason

evidence reference

verification status

related requirement/order/commitment
```

Examples:

```text
farmer_solicited

farmer_accepted

farmer_declined

farmer_dropped

production_quantity_changed

reserve_activated

replacement_solicited

replacement_committed

lot_received

lot_graded

lot_rejected

shipment_dispatched

delivery_confirmed

buyer_order_changed

trade_reconciled
```

The event trail should allow reconstruction of why the system made a decision.

---

# 23. Concurrency / Data Integrity Requirements

The architecture must prevent:

## Double Allocation

The same production quantity cannot be actively committed to multiple buyer requirements.

---

## Duplicate Recovery

Two simultaneous replanning processes must not both allocate replacement supply for the same shortfall.

---

## Duplicate Delivery

Repeated delivery events must not create duplicate ledger entries.

---

## Phantom Verification

No sensor, inspection or buyer confirmation may be represented as present unless corresponding evidence exists.

---

## Lost Traceability

Consolidation must never remove farmer-lot identity.

---

# 24. Recommended Core Domain Hierarchy

The architecture should approximately represent:

```text
BUYER
  ↓
ORDER
  ↓
REQUIREMENT

FARMER
  ↓
PRODUCTION LOT

REQUIREMENT
  ↓
COMMITMENTS
  ↓
STANDBY CAPACITY

PRODUCTION LOT
  ↓
SUBLOT
  ↓
FULFILMENT NODE
  ↓
GRADE / ACCEPT
  ↓
CONSOLIDATED SHIPMENT
  ↓
DELIVERY
  ↓
RECONCILIATION
  ↓
TRADE PERFORMANCE EVIDENCE
```

---

# 25. Recommended High-Level Modules

The exact repository design should be challenged before implementation, but anticipated logical boundaries include:

```text
domain/

demand/

supply/
    planner
    availability
    reserves

assurance/
    orchestration
    state
    events

risk/

economics/

fulfilment/

compliance/

reconciliation/

trade_evidence/

messaging/

infrastructure/
    database
    llm
```

Domain logic should not depend directly on FastAPI, Supabase or a particular LLM provider.

---

# 26. Initial Agent Tools

The Supply Assurance Agent may eventually receive tools resembling:

```text
get_requirement()

get_supply_state()

get_eligible_production_lots()

calculate_supply_plan()

calculate_supply_risk()

calculate_landed_cost()

activate_reserve_supply()

solicit_replacement_supply()

inspect_fulfilment_state()

get_verified_compliance_rules()

escalate_to_human()
```

The agent decides which appropriate action to invoke.

The tool calculates authoritative truth.

---

# 27. Initial State Model

A requirement may move through states similar to:

```text
DRAFT

PLANNING

SOLICITING

COMMITTED

AT_RISK

REPLANNING

RECOVERED

ESCALATION_REQUIRED

IN_FULFILMENT

FULFILLED

CLOSED
```

Do not force these exact names into the architecture if a cleaner state/event design exists.

The architecture review should challenge whether state belongs on the requirement itself, is derived from events, or should be represented separately.

---

# 28. Core Demo Scenario

The MVP must demonstrate one complete story.

## Initial State

Hotel requests:

```text
500kg Grade A ginger
```

System identifies sufficient eligible production.

Planner creates:

```text
Committed supply:  500kg

Standby supply:    approximately 100–150kg
```

---

## Disruption

One farmer responsible for:

```text
80kg
```

drops out.

System becomes:

```text
Required:    500kg

Available committed supply: 420kg

Shortfall:    80kg

Status: AT_RISK
```

---

## Agent Recovery

The Supply Assurance Agent:

1. observes the dropout;
2. inspects requirement state;
3. calculates shortfall;
4. inspects standby capacity;
5. activates eligible standby supply;
6. searches remaining production if reserve is insufficient;
7. creates replacement actions;
8. restores 500kg where possible;
9. recalculates supply risk;
10. recalculates landed cost;
11. records the complete decision trail.

Expected successful result:

```text
Required supply:        500kg

Recovered supply:        80kg

Final committed supply: 500kg

Status: RECOVERED
```

---

# 29. Physical Demo

Committed farmer sublots arrive at one fulfilment node.

The system records:

```text
received

weighed

graded

accepted / rejected
```

At least one quality exception may be demonstrated if time allows.

Accepted sublots are assembled into one buyer shipment.

The shipment retains traceability to all source farmers.

---

# 30. Final Demo Result

The system should ultimately show:

```text
BUYER

Required:                 500kg

Final accepted supply:    500kg

Supply disruption:         80kg

Recovered:                 80kg

Buyer SLA:             PRESERVED
```

And:

```text
ECONOMICS

Original landed cost

Recovered landed cost

Recovery premium
```

And:

```text
FARMERS

New verified institutional trade recorded

Performance passport updated
```

Closing product thesis:

> **The hotel experiences one dependable supplier relationship. Behind it can be dozens of small farmers.**

Secondary thesis:

> **Repeated verified fulfilment generates trade-performance evidence that farmers may choose to share with financial institutions.**

---

# 31. Three-Day MVP Scope

We have approximately three days.

Architecture must therefore distinguish between:

## REQUIRED

* domain model;
* seeded farmers;
* production lots;
* one hotel order;
* deterministic supply planner;
* committed supply;
* standby supply;
* landed-cost calculation;
* 80kg dropout;
* autonomous replanning;
* truthful escalation;
* event/audit trail;
* basic fulfilment node;
* farmer sublot traceability;
* reconciliation;
* trade-performance output;
* minimal verified domestic compliance data;
* simple demo UI/API flow.

---

## OPTIONAL

Only if required functionality is stable:

* quality-rejection replan;
* visual risk indicators;
* LLM demand parsing;
* farmer message generation;
* live event streaming;
* sensor data.

---

## OUT OF SCOPE

Do not build during the three-day MVP:

* marketplace;
* farmer browsing/search UI;
* full farmer onboarding;
* production mobile app;
* authentication/complex permissions;
* live WhatsApp API;
* banking integration;
* lending;
* automated credit decisions;
* payment processing;
* CARICOM-wide compliance coverage;
* multiple export corridors;
* sophisticated ML;
* live weather integration;
* advanced route optimization;
* advanced optimization solver;
* full warehouse-management system;
* live ALEX integration;
* live hotel ERP integration;
* blockchain.

Mock integration boundaries where necessary.

The agent behaviour and deterministic supply logic must be real.

---

# 32. Architecture Review Required Before Production Code

Before writing production code, produce:

1. **Domain model and glossary**
2. **Aggregate boundaries**
3. **State machines and transition rules**
4. **Database schema**
5. **Database ownership**
6. **Audit/event strategy**
7. **Consistency and transaction strategy**
8. **Concurrency-control strategy**
9. **Module boundaries**
10. **Dependency rules**
11. **API design**
12. **Domain event contracts**
13. **Agent/tool contracts**
14. **Failure and retry strategy**
15. **Human escalation model**

Then challenge the proposed architecture against:

* simultaneous farmer dropouts;
* double allocation;
* stale production availability;
* concurrent replanning;
* duplicate events;
* failed replacement solicitation;
* insufficient reserve supply;
* production quality rejection;
* buyer-side changes;
* compliance uncertainty;
* missing verification;
* disputes;
* bad/fraudulent farmer reporting;
* partial fulfilment;
* database/network failure;
* LLM failure;
* reconciliation errors.

Recommend revisions before implementation.

---

# 33. Architecture Principle

The central engineering principle is:

> **Structured, verified and deterministic systems establish truth. The agent observes that truth and decides what action to take next.**

The LLM is not the database.

The LLM is not the calculator.

The LLM is not the compliance authority.

The LLM is not the lender.

The LLM is the reasoning and language layer around a deterministic, auditable supply-assurance system.

---

# 34. Success Criterion

This MVP succeeds if we can reliably demonstrate:

```text
500kg buyer demand
        ↓
fragmented smallholder supply
        ↓
500kg committed
        ↓
reserve capacity established
        ↓
80kg disruption
        ↓
agent detects risk
        ↓
agent replans
        ↓
500kg restored
        ↓
recovery cost quantified
        ↓
produce traced through fulfilment
        ↓
delivery reconciled
        ↓
verified trade evidence created
```

If that works reliably, the MVP is successful.

Everything else is secondary.
