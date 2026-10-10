# KoroFarm Buyer Frontend Design

Status: proposed product and interaction design  
Audience: product, design, frontend, backend, QA  
Primary persona: institutional procurement manager / buyer-side operations team  
Backend baseline: repository state reviewed 2026-09-29

## 1. Purpose

The buyer frontend is the procurement and supply-assurance workspace for an institution that needs agricultural produce delivered to specification. It should answer five questions quickly:

1. What have we asked KoroFarm to supply?
2. Will each requirement be fulfilled on time and to specification?
3. Which requirements need buyer attention now?
4. What has physically arrived, passed inspection, and been delivered?
5. What evidence exists for the completed trade?

The buyer experience is not a farmer marketplace and should not expose the platform as a collection of internal technical modules. The backend already models a progression from buyer demand to planning, assurance, physical fulfilment, reconciliation, and trade evidence. The frontend should organize itself around that progression.

## 2. Product principles

### 2.1 Buyer outcome first

The top-level experience should use procurement language: Requirements, Supply, Deliveries, Quality, Evidence, and Exceptions. Internal concepts such as agents, allocations, recovery runs, ingestion, and reconciliation should appear only where they help explain or operate a buyer outcome.

### 2.2 Exception-led operation

Healthy supply should require little attention. AT_RISK, RECOVERING, ESCALATION_REQUIRED, rejected product, overdue delivery, and explicit approval requests should rise above informational activity.

### 2.3 Physical states stay distinct

Committed, received, accepted, rejected, dispatched, and delivered are not interchangeable. The UI must preserve those distinctions. In particular, receipt must never visually imply acceptance.

### 2.4 Evidence over inferred certainty

The UI should distinguish API-authoritative state, deterministic values derived from authoritative data, self-reported information, and unavailable evidence. Missing compliance, traceability, or delivery evidence remains visibly missing.

### 2.5 Buyer actions are attributable

Changes initiated by the buyer must remain buyer-attributed. A buyer quantity amendment must never appear as a farmer reliability failure. The existing buyer-change API explicitly preserves this invariant.

### 2.6 Permission-aware, not merely hidden

Navigation and controls may adapt to the current user's role, but authorization remains a backend responsibility. The frontend must treat 403 responses as authoritative and never use hidden controls as its security boundary.

## 3. Primary buyer persona

### Procurement manager

Goals:

- create demand with an exact commodity, grade, quantity, destination context, and delivery window;
- monitor coverage without manually coordinating every supplier;
- identify shortages early;
- understand supply concentration and replacement depth;
- approve or review recovery when policy requires it;
- see whether expected product was received and accepted;
- preserve an auditable record of buyer-originated changes;
- obtain trade evidence after verified completion.

The backend role closest to this persona is `PROCUREMENT_MANAGER`. Its permissions cover requirement create/update/view, supply view, recovery view/approval, trade-evidence view, compliance view, audit view, and approval-policy view.

Related buyer-side roles have narrower jobs. A warehouse operator records receiving, grading, shipments, dispatch, and delivery; a supply coordinator operates supply and recovery; an auditor receives read-heavy assurance, receiving, compliance, evidence, and audit access. The UI should support the same buyer organization with role-sensitive actions rather than creating entirely separate products for each staff role.

## 4. Buyer journey model

The core buyer journey is:

`Requirement → Plan → Assure → Recover if needed → Receive & inspect → Ship/deliver → Reconcile → Evidence`

The requirement is the primary buyer work object. Programmes group requirements over a broader buying relationship or period. Farmers, lots, allocations, sublots, shipments, risk snapshots, and recovery cases are supporting objects.

### Requirement lifecycle

The backend supports DRAFT, PLANNING, ACTIVE, IN_FULFILMENT, RECONCILED, CLOSED, and CANCELLED. The frontend should show lifecycle separately from supply health.

### Supply health

The backend supports UNPLANNED, COVERED, AT_RISK, RECOVERING, and ESCALATION_REQUIRED. This is the primary exception state and should receive stronger visual emphasis than lifecycle status while procurement is active.

### Inspection state

Physical receipts support RECEIVED, PENDING_INSPECTION, ACCEPTED, PARTIALLY_ACCEPTED, and REJECTED. These states belong to Quality / Receiving and must not be collapsed into supply health.

## 5. Information architecture

The current frontend exposes many internal workspaces equally. The buyer navigation should be reduced and regrouped around buyer jobs.

### Primary navigation

**Overview** — portfolio health, attention queue, physical flow, upcoming work, recent significant activity.

**Requirements** — all buyer requirements, create requirement, filters, requirement details and amendments.

**Programmes** — longer-running procurement programmes and their requirement rollups.

**Supply** — committed and standby supply, supplier exposure, production lots, concentration, and recovery status.

**Deliveries & Quality** — received sublots, inspection status, accepted/rejected quantity, shipments, and delivery progression.

**Evidence & Compliance** — traceability, applicable verified compliance rules, reconciliation state, and trade evidence.

### Secondary navigation

**Activity** — auditable domain event history.

**Reports** — current-state procurement analytics supported by authoritative backend data. Do not claim historical trend analysis until historical aggregate APIs are defined.

**Administration** — users, organization, approval policies, and integrations for users with relevant permissions.

### Items that should not be primary buyer navigation

- Agent Operations: implementation detail; surface agent outcomes inside exceptions/audit instead.
- Scenario Lab: useful specialist tool, but not a primary procurement job and must remain clearly non-authoritative if retained.
- Network Intelligence: merge buyer-relevant concentration information into Supply.
- separate Assurance Center: merge day-to-day assurance into Overview and Requirement detail; retain a dedicated exception queue only if portfolio scale justifies it.
- Integrations and system settings: administration, not daily procurement.

## 6. Global shell

### Header

The header should contain:

- organization identity;
- active buyer or programme context when applicable;
- global search when backed by registries;
- notifications / attention count;
- current user's name and role;
- environment badge in demo/non-production environments only.

The current header hard-codes a Jamaica institutional-procurement subtitle and configured programme context. Replace this with organization and route context from authenticated/backend state before multi-customer production use.

### Navigation behavior

Render navigation from permissions returned by the identity profile rather than maintaining one universal menu. Examples:

- Procurement Manager: Overview, Requirements, Programmes, Supply, Deliveries read view, Evidence & Compliance, Activity.
- Warehouse Operator: operational receiving and delivery surfaces first; no requirement creation.
- Auditor: read-only requirements, supply, deliveries, evidence, compliance, and audit.
- Organization Admin: administration plus read-oriented operating visibility.

Disabled actions should normally be omitted when the user lacks permission. If an action is visible to explain a workflow but unavailable, state the required permission rather than presenting a control that only fails after click.

## 7. Overview / buyer command center

### Goal

Give the buyer a portfolio-level answer to “Are we covered and what needs my attention?” within a few seconds.

### First viewport

Use a compact KPI strip:

- active requirements;
- covered requirements;
- needs attention;
- committed kg;
- received kg;
- accepted kg;
- rejected kg.

The backend command-center summary already supports portfolio requirement counts, physical-flow quantities, committed parish concentration, and recent activity.

### Attention queue

This is the dominant component beneath the KPIs. Priority order:

1. ESCALATION_REQUIRED;
2. AT_RISK;
3. RECOVERING where buyer approval/action is required;
4. rejected or partially accepted receipt creating a material assurance impact;
5. unplanned active requirements;
6. informational items.

Each item should show commodity/grade, requirement reference, delivery window, required kg, assured/committed kg, shortfall, status, and the next legitimate action. Clicking opens the Requirement workspace at the relevant tab.

The command-center summary currently provides counts but not complete exception rows. Populate the queue from the requirement list endpoint filtered by supply health; load assurance detail only where needed. Do not fabricate portfolio exception records from the configured demo requirement.

### Physical flow

Show committed → received → accepted/rejected as a flow rather than independent unrelated cards. This reinforces that accepted quantity is a subset of inspected receipts and that rejected quantity is an operational exception.

### Supply concentration

Show committed quantity by parish and explicitly label it as concentration, not geospatial coverage. No map should be shown unless actual coordinates become authoritative.

### Recent activity

Display human-readable significant events with timestamp and actor type. Raw event IDs may be available through a detail drawer for audit users instead of dominating the buyer dashboard.

## 8. Requirements workspace

### Requirements list

This is the buyer's main registry. The backend now has a true requirement list endpoint, so the frontend should no longer describe multi-requirement listing as unavailable.

Columns:

- reference / ID;
- commodity and grade;
- programme;
- required quantity;
- delivery window;
- lifecycle;
- supply health;
- coverage or shortfall when assurance detail is available;
- next action.

Filters directly supported by the requirements endpoint:

- supply health;
- lifecycle status;
- buyer;
- programme;
- pagination.

Client-side text search should not imply server-wide search unless a backend search parameter is added.

### Create requirement

Primary CTA: **New requirement**.

Form fields supported by the backend:

- buyer;
- programme (optional);
- trade corridor (optional);
- crop;
- grade;
- required quantity in kg;
- delivery start;
- delivery end.

Use a review step before submission. After successful creation, navigate to the new Requirement workspace. Do not expose lifecycle or supply-health selectors; those are system state, not arbitrary buyer form fields.

### Amend quantity

The backend currently supports one explicit buyer amendment: required quantity plus reason. Expose **Change quantity** from Requirement detail to users with `requirement.update`.

The confirmation UI should show previous quantity, new quantity, delta, reason, and a warning that the change can alter assurance. After submission, identify the resulting record as **Buyer change** and refresh assurance. Do not penalize farmer-facing reliability indicators for this event.

Do not expose edits to grade, crop, delivery dates, buyer, programme, or corridor until matching backend commands and audit semantics exist.

## 9. Requirement detail

This is the primary operating page and should replace the tendency to make users jump between many generic modules.

### Persistent requirement header

Show:

- crop + grade;
- quantity;
- destination;
- delivery window;
- lifecycle status;
- supply health;
- programme link when present;
- requirement reference.

Recommended tabs:

### Overview

Summary of required, assured/committed, standby, shortfall, landed cost when available, risk, physical fulfilment, and the highest-priority next action.

### Supply

Committed and standby allocations with farmer, parish, lot, allocated kg, allocation status, and role. Include concentration and risk snapshot values such as largest farmer/parish share and replacement depth where available.

Buyer framing matters: this is “Supply for this requirement,” not a farmer leaderboard. Avoid unsupported quality/reliability scores.

### Assurance & recovery

Show the disruption cause, lost quantity, standby activation, replacement accepted, remaining shortfall, recovery cost premium, and status. Recovery execution controls must be permission-gated and, where approval policy applies, reflect the policy workflow rather than exposing an unconditional “Run recovery” button.

### Receiving & quality

Show expected, received, accepted, and rejected quantities plus received sublots and inspection states. Procurement managers are read-oriented here; warehouse roles receive operational forms when their permissions allow them.

### Logistics

Show requirement shipments, reference, dispatch state, dispatch evidence, and delivery state/evidence where APIs provide it.

### Compliance & evidence

Show applicable verified rules and their source/version/verification timestamp. Traceability should visualize only existing links. Reconciliation/trade evidence appears only when the corresponding backend record exists.

### Activity

Requirement-scoped events ordered chronologically, with actor type and audit metadata available on demand.

## 10. Programmes

Programmes group requirements belonging to the same buyer. The backend supports create, list, detail, requirement association, aggregate required/committed/standby quantities, active requirement count, and counts by supply health.

### Programme list

Show name, commodity scope, date range, status, active requirement count, required kg, committed kg, standby kg, and needs-attention count.

### Programme detail

Show programme identity and portfolio metrics followed by its requirements. The current backend programme summary returns aggregate counts but not its requirement rows; populate rows using the requirement list endpoint filtered by programme ID.

Creating programmes and associating requirements should only be exposed after those programme mutations receive the same organization scoping and permission enforcement expected of production buyer commands.

## 11. Supply workspace

The buyer does need visibility into the supply backing its requirements, but not farmer-side task management.

### Supplier registry

Use the farmer registry for supplier name, parish, active state, production-lot count, available kg, and committed kg. Drill-down should focus on buyer-relevant supply facts and verified trade evidence.

### Allocation registry

Support requirement, role, and status filters. Use role/status labels such as Committed, Standby, Activated, Lost, Accepted, or Declined according to backend values instead of inventing generic “supplier health.”

### Network risk

Expose parish concentration, largest supplier share, largest parish share, standby coverage, replacement depth, and availability confidence only where a persisted risk snapshot provides those values.

The buyer should not be shown private farmer workflows, secure response tokens, unrelated records, or internal data that their permission/organization does not authorize.

## 12. Deliveries & Quality

This area should combine the existing fulfilment and shipment concepts into one buyer-understandable operational journey.

### Receiving registry

The received-sublot registry supports inspection filtering and provides requirement ID, node, quantities, inspection status, grade, and received timestamp. Recommended columns:

- received time;
- requirement;
- fulfilment node;
- received kg;
- accepted kg;
- rejected kg;
- inspection state;
- assigned grade.

Procurement users should have read access when authorized. Recording receipt and grading should appear only to roles with `receiving.record` and `grading.record`.

### Shipments

List shipment reference, linked requirement, status, dispatch timestamp, and evidence status. Shipment creation/dispatch/delivery controls belong primarily to warehouse/logistics permissions.

### Quality exceptions

REJECTED and PARTIALLY_ACCEPTED receipts should be visually elevated. Where rejected quantity changes assured coverage, link directly to the affected requirement's Assurance tab rather than implying the receiving screen itself resolves supply risk.

## 13. Evidence & Compliance

### Compliance

Display only persisted compliance rules. Important provenance fields—issuing body, source citation, source version, effective dates, last verified time, and verifier—should be visible from rule detail.

Do not present general guidance as a verified legal requirement.

### Traceability

Use progressive relationship chains from production lot / allocation through received sublot, shipment, delivery, buyer confirmation, and evidence. Missing nodes should display **Not yet recorded** rather than synthetic placeholders that look complete.

### Trade evidence

Treat reconciliation as the gate to completed trade evidence. A buyer should be able to inspect what was required, what was accepted/delivered, buyer confirmation, and attributable exceptions before a trade is presented as completed evidence.

## 14. Notifications and attention model

The product should distinguish **attention** from **activity**.

Attention is actionable or materially risky. Examples: requirement escalated, coverage lost, recovery awaiting approval, inspection rejection affecting fulfilment, or a missing action required before delivery.

Activity is an auditable fact that may need no action. Examples: plan created, allocation accepted, receipt recorded, recovery completed, shipment dispatched.

The bell should show unresolved attention count, not merely whether any event exists. The Activity workspace remains the complete event ledger.

The backend currently exposes events and portfolio activity but does not persist a per-user read/unread or resolved-notification model. Until that exists, avoid claiming notification read state or durable personal inbox behavior.

## 15. Data trust presentation

Use a small, consistent vocabulary instead of placing a “system derived” badge on every metric:

- **Authoritative** — direct persisted API state.
- **Calculated** — deterministic UI or backend calculation from authoritative state, such as coverage percentage.
- **Self-reported** — farmer response not yet verified.
- **Not recorded** — expected evidence/state does not exist.
- **Simulation** — non-persistent scenario result; never mix with live assurance.

Show provenance at section/detail level unless the distinction is material to an individual field.

## 16. Visual and interaction design

### Density

The buyer experience is operational software, so desktop tables may be dense, but the first viewport should remain scannable. Use cards for high-level outcomes and tables for registries, not card grids for every entity.

### Color semantics

- green: covered / accepted / successfully completed;
- amber: at risk / pending inspection / attention;
- red: escalation / rejected / material shortfall;
- blue or neutral accent: standby / informational;
- gray: unavailable, not assessed, closed, or secondary state.

Never rely on color alone. Every state needs text and, where helpful, an icon.

### Progressive disclosure

Keep procurement outcomes prominent and move technical IDs, planner versions, calculation versions, correlation IDs, and raw payloads into expandable detail or audit views.

### Mobile

Buyer mobile is for monitoring, approval, and exception handling rather than dense portfolio administration. On small screens prioritize attention items, requirement summary, status, delivery timing, and legitimate single actions. Complex registries can use compact rows that open detail views.

## 17. Empty, loading, and error states

Empty states should describe reality and the next supported action:

- no requirements: “No requirements yet” + New requirement when permitted;
- unplanned requirement: “Supply plan not created yet,” not 0% failure;
- no recovery: “No recovery case for this requirement”;
- no receipts: “Nothing received yet”;
- no verified compliance rule: “No verified rule on file”;
- no evidence: “Trade evidence is not available until verified reconciliation.”

Never substitute demo data after a live API failure. Errors should preserve the distinction between unavailable data and a legitimate zero/empty result.

## 18. Backend capability map

### Ready to drive buyer UI now

- requirement create/list/detail and buyer quantity change;
- requirement lifecycle and supply-health state;
- requirement assurance, allocations, economics, persisted risk, disruption, and recovery summary;
- programme create/list/detail/association and programme aggregate summary;
- farmer, allocation, recovery-case, received-sublot, shipment, activity, compliance-rule, and command-center registries;
- production-lot list/detail;
- requirement fulfilment summary;
- receiving and grading commands;
- shipment creation, composition, dispatch, delivery, reconciliation, and traceability commands/reads;
- trade corridors;
- authenticated identity profile and role/permission model.

### Needs backend hardening or extension before production UI relies on it

Several newer registries and operational endpoints should be reviewed for organization scoping and permission enforcement before they become production buyer surfaces. The requirement endpoints already demonstrate organization-scoped authorization; the same standard should apply consistently to programme, assurance, registry, fulfilment, reconciliation, corridor, and related queries/commands.

Additional product/API gaps:

- durable notification/read-resolution model;
- server-side free-text search if global search is promised;
- buyer amendment commands beyond quantity (dates/specification/etc.) with explicit audit semantics;
- portfolio endpoints that return exception rows efficiently, if requirement-list + per-item assurance becomes too expensive;
- explicit lifecycle-transition commands if buyers/operators are expected to advance lifecycle manually;
- richer delivery/evidence registries if cross-requirement evidence browsing is required.

## 19. Existing frontend changes

### Keep and evolve

- the current command-center visual language and exception-led presentation;
- requirement status badges;
- assurance allocation table patterns;
- fulfilment quantity distinctions;
- data-trust discipline and honest missing-data states;
- authenticated API client with organization context.

### Change

- replace the universal module-heavy sidebar with buyer job-oriented and permission-aware navigation;
- make the real requirement list the source for Requirements instead of a single configured requirement;
- make the command center use the portfolio summary plus real requirement exception rows;
- consolidate Assurance into requirement detail and the portfolio attention queue;
- consolidate Network Intelligence into Supply;
- consolidate Fulfilment into Deliveries & Quality;
- consolidate Traceability, Compliance, and Trade Evidence under Evidence & Compliance while preserving distinct data semantics;
- demote Agent Operations, integrations, and scenario tooling from daily procurement navigation.

### Remove outdated frontend assumptions

The existing frontend copy says the backend has no requirement-list, global farmer, global event, shipment, compliance-rule, or portfolio command-center APIs. Those statements are no longer correct against the current backend. The redesign should consume the available registries rather than retaining those limitations in empty-state copy.

## 20. Proposed route map

| Route | Buyer purpose |
|---|---|
| `/` | Buyer portfolio overview and attention queue |
| `/requirements` | Requirement registry |
| `/requirements/new` | Create requirement |
| `/requirements/[id]` | Requirement operating workspace |
| `/programmes` | Programme portfolio |
| `/programmes/[id]` | Programme detail and requirements |
| `/supply` | Supplier/allocation registry and network risk |
| `/supply/farmers/[id]` | Buyer-authorized supplier detail |
| `/deliveries` | Receiving and shipment overview |
| `/deliveries/receipts/[id]` | Receipt, inspection, traceability detail |
| `/deliveries/shipments/[id]` | Shipment/delivery detail |
| `/evidence` | Evidence and reconciliation registry |
| `/compliance` | Verified compliance registry |
| `/activity` | Auditable activity ledger |
| `/admin/*` | Organization administration where permitted |

Old URLs may redirect to the corresponding consolidated workspace during migration.

## 21. MVP implementation sequence

### Phase 1 — Buyer foundation

- permission-aware buyer shell;
- real requirement registry;
- requirement creation;
- redesigned requirement detail with Overview, Supply, Assurance, Receiving, Evidence, Activity;
- buyer quantity amendment flow;
- portfolio overview using the command-center summary.

### Phase 2 — Operational depth

- programme registry/detail using current programme APIs;
- supplier and allocation registries;
- deliveries/receipts/shipments registry;
- compliance and traceability surfaces;
- role-aware warehouse and supply-coordinator controls.

### Phase 3 — Workflow refinement

- durable notifications;
- approval-policy-driven recovery UX;
- global search;
- richer evidence/reconciliation browsing;
- historical buyer reporting only after authoritative historical APIs exist.

## 22. MVP acceptance criteria

The buyer frontend is ready for its first production-oriented usability pass when:

1. a procurement manager can list, create, open, and quantity-amend an authorized requirement;
2. the overview uses real portfolio data and clearly identifies requirements needing attention;
3. lifecycle and supply health are displayed as separate concepts;
4. a requirement shows its committed/standby supply, shortfall, risk, fulfilment quantities, and available evidence without fabricated state;
5. received, accepted, and rejected quantities remain visually and semantically distinct;
6. user permissions determine available navigation/actions, while every sensitive API remains server-authorized;
7. buyer-caused changes are visibly buyer-attributed and never represented as farmer failure;
8. missing compliance, traceability, and evidence is explicitly shown as missing;
9. live API failure never silently falls back to demo content;
10. outdated “single configured requirement / registry unavailable” assumptions are removed where the backend now provides portfolio APIs.

## 23. Design decision summary

The buyer side should evolve from the current “Supply Assurance OS” collection of modules into a procurement operating system centered on Requirements and Exceptions. The backend is now capable of significantly more portfolio behavior than the existing frontend uses: requirement listing, programmes, global operational registries, a command-center summary, identity permissions, and physical-flow registries all exist.

The resulting frontend should feel simpler despite exposing more real capability. Buyers see what they ordered, whether it is covered, what is arriving, what passed inspection, what needs attention, and what evidence closes the trade. Internal platform machinery remains available where it explains or enables those outcomes, rather than defining the navigation itself.
