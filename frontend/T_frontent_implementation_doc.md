KoroFarm Frontend & Product Specification

Document status: Canonical target specification
Version: 1.0
Date: 26 August 2026
Audience: Product, frontend, backend, design, QA, demo operators
Repository target: docs/product-frontend-spec.md

1. Purpose and Document Authority

This document is the canonical frontend and product specification for KoroFarm. It consolidates the existing buyer-focused build guide, the implemented frontend state, and the expanded buyer/farmer/operations architecture into one source of truth.

It distinguishes between CURRENT STATE (already implemented and demonstrable) and TARGET STATE (the architecture and product behavior the frontend should converge toward). Where older documents conflict with this specification, this document takes precedence.

1.1 Superseded decisions

The earlier restriction that prohibited authentication, role management, onboarding, and farmer-facing interfaces is superseded. Those surfaces are now part of the target product scope, but implementation should remain incremental and preserve the working buyer demo.

1.2 Source-of-truth hierarchy

This specification defines target product behavior, route structure, state models, terminology, and acceptance criteria.

docs/frontend-api-gap.md records missing or unresolved frontend/backend contracts only.

Typed domain contracts and event schemas in the codebase must conform to this specification.

Demo fixtures must conform to the domain contracts and event schemas rather than invent page-specific data.

2. Product Definition

KoroFarm is a supply coordination and assurance system for institutional agricultural procurement in Jamaica. It is not an open marketplace, storefront, farmer directory, or public listings platform.

The system allows an institutional buyer to declare a produce requirement, coordinate committed and standby supply across multiple agricultural producers, monitor coverage and disruption risk, recover from shortfalls, understand the cost impact of recovery, and later reconcile physical fulfilment using receipt and grading evidence.

The farmer experience is an operational task queue. Farmers receive targeted procurement requests, accept fully or partially, hold standby capacity when applicable, manage commitments, and report emerging shortfalls early.

The operations surface is a deliberately thin escalation layer for cases that cannot be resolved automatically or require coordinator action.

2.1 Core product promise

KoroFarm should help a buyer answer:

What do I need?

How much of that requirement is currently committed?

How much standby capacity exists?

Where is the remaining shortfall?

Which producers and production lots make up the plan?

What changed when a disruption occurred?

What action restored coverage?

What did recovery cost?

What has actually been received and graded versus merely planned?

KoroFarm should help a farmer answer:

What requires my attention now?

What quantity, grade, price, destination, and delivery window am I being asked to support?

Am I committed or on standby?

When does my response expire?

What will I be paid and under what terms?

What should I do if I can no longer supply the full commitment?

3. Product Principles

3.1 Not a marketplace

Demand is routed to qualified producers. Farmers do not browse public buyer listings and buyers do not browse a public farmer catalogue.

3.2 Epistemic discipline

The interface must distinguish what is planned, committed, reserved, reported, verified, and physically received. Planning data must never be presented as physical delivery evidence.

The UI must not display fabricated probabilities, arbitrary credit scores, star ratings, or unsupported reliability indices.

3.3 Commitment recovery is not fulfilment

Restoring a requirement from 420 kg back to 500 kg of committed coverage means the plan has recovered. It does not mean 500 kg has been delivered. Physical fulfilment begins only when receipt and grading evidence exists.

3.4 Symmetric commercial transparency

Farmers must be able to see the quantity, grade, delivery window, location, price, and payment terms relevant to a request. Buyers may see supplier identity, parish, allocated volume, role, status, and traceability identifiers without exposing private contact information unnecessarily.

3.5 One domain model, multiple personas

Buyer, farmer, operations, notifications, and demo controls must be projections of the same underlying domain state and event history.

3.6 Demo mode must be deterministic

Demo mode is a first-class runtime mode, not a collection of disconnected page mocks. The same event sequence must drive all affected views.

3.7 Mobile-first where the work happens

The buyer experience may be desktop-dense. The farmer experience must be mobile-first, touch-friendly, resilient on limited bandwidth, and usable with minimal navigation depth.

4. Current State vs Target State

4.1 Current state

The current frontend already includes:

Next.js App Router application structure.

Shared provider layer and reusable component architecture.

Supabase authentication, session restoration, login, signup, profile, and protected dashboard routing.

Light/dark theme switching.

Buyer Supply Assurance Dashboard backed primarily by typed deterministic mock data.

A 500 kg Grade A ginger requirement with farmer allocations, standby supply, an 80 kg disruption, recovery, economics, and fulfilment separation.

Notifications and profile views.

Introductory dashboard animation.

Supabase-backed room/sensor and AI hooks that are not connected to the KoroFarm agricultural workflow.

4.2 Target state

The target frontend adds:

Buyer, Farmer, and Operations application contexts.

Role-aware routing and layouts.

Role-aware onboarding.

Buyer requirement portfolio and requirement creation.

Farmer request evaluation, partial acceptance, commitment management, standby management, and shortfall reporting.

Shared event-driven demo state.

Requirement, request, allocation, verification, and fulfilment state machines.

Deterministic risk explanation and recovery economics.

Centralized domain adapters and view-models.

4.3 Technical stack note

The package manifest is authoritative for framework versions. If the project is on Next.js 16, the React dependency must be aligned with the supported React generation used by the project rather than retaining an outdated documentation label. Do not hard-code “React 18” in project documentation without verifying package.json.

4.4 Non-domain code cleanup

Room/sensor occupancy, energy prediction, and unrelated AI hooks must be removed from the active KoroFarm feature architecture or isolated as archived/template code unless a concrete agricultural workflow adopts them.

5. Personas, Roles, and Authorization

KoroFarm has three application personas.

5.1 Buyer

Typical users include procurement officers, purchasing directors, executive chefs, F&B directors, finance managers, and organizational administrators.

Buyer users can:

Create and monitor procurement requirements.

Review supply coverage and participating allocations.

Inspect recovery episodes and audit events.

Review landed-cost impact.

Review fulfilment evidence when available.

Manage organization sites and team settings where authorized.

5.2 Farmer

Farmer users can:

Receive targeted fill or standby requests.

Accept, partially accept, or decline requests.

Review active commitments.

Report shortfalls or issues.

Review standby reservations and release conditions.

Maintain crop capability and production-lot data.

Review objective historical activity metrics and payout information.

5.3 Operations

Operations users manage escalations and exceptional cases. The initial /ops implementation may remain a thin triage surface, but escalation events must not dead-end in the UI.

5.4 Authorization model

Authentication proves account identity; authorization controls application access.

Authorization must not rely on user-editable profile metadata alone. Application roles, organization membership, admin status, and operator privileges must be represented in protected application data and enforced by backend authorization/RLS policies.

Recommended conceptual structure:

Account
  -> memberships[]
       -> organization_id
       -> persona: BUYER | FARMER | OPS
       -> role: MEMBER | ADMIN | COORDINATOR | ...
       -> status: ACTIVE | PENDING | SUSPENDED

The first person registering with an organization email domain must not automatically become a trusted organization administrator solely because of domain ownership. Organization creation, invitation, verification, and approval policies are backend concerns and must be modeled explicitly.

6. Information Architecture and Routes

PUBLIC
/                              Entry / persona-aware landing
/login                         Authentication identifier / credentials
/login/verify                  Verification when required
/signup                        Role selection router
/signup/farmer                 Farmer registration
/signup/buyer                  Buyer registration
/onboarding/:step              Role-aware onboarding engine
/r/:token                      Lightweight signed request response
/methodology                   Coverage, risk, confidence methodology
/legal/terms
/legal/privacy
/legal/assurance-terms

BUYER (/b)
/b                             Requirement portfolio
/b/requirements/new/:step      Requirement intake wizard
/b/requirements/:id            Supply Assurance Dashboard
/b/requirements/:id/plan       Coverage composition
/b/requirements/:id/participants
/b/requirements/:id/assurance/:episodeId
/b/requirements/:id/cost
/b/requirements/:id/events
/b/requirements/:id/fulfilment
/b/requirements/:id/compliance
/b/org/profile
/b/org/sites
/b/org/team
/b/org/approvals

FARMER (/f)
/f                             Mobile action queue
/f/requests/:id                Request evaluation
/f/commitments                 Active commitments
/f/commitments/:id             Commitment detail / shortfall reporting
/f/standby                     Reserved capacity
/f/lots                        Production lots
/f/lots/new                    Declare production lot
/f/record                      Objective activity history
/f/profile                     Farmer profile
/f/profile/disclosure          Disclosure and privacy controls

OPERATIONS
/ops                           Escalation triage queue

DEVELOPER / DEMO
/dev/demo                      Demo scenario controller, build-flagged

6.1 Routing rules

Unauthenticated access to protected persona routes redirects to /login.

Authenticated users with one active persona route directly into that persona.

Users with multiple permitted personas may choose context from an account switcher.

Role selection during signup determines onboarding flow but does not bypass backend authorization.

/r/:token must use a signed, expiring, narrowly scoped token and may only expose the specific response action encoded by the backend.

7. Cross-Persona Core Workflow

The primary product loop is:

Buyer submits requirement
        -> requirement.SUBMITTED
Planning starts
        -> requirement.PLANNING
Requests sent to farmers
        -> requirement.AWAITING_RESPONSES
Farmers accept / partially accept / decline
        -> allocations created or updated
Committed + standby capacity assembled
        -> requirement.COVERED
Farmer reports shortfall
        -> allocation.LOST or reduced
        -> requirement.AT_RISK
Standby allocation activated
        -> allocation.STANDBY_ACTIVATED
Coverage restored
        -> requirement.COVERED or REPLACEMENT_UNDERWAY -> COVERED
Physical collection occurs
        -> receipt evidence recorded
        -> grading / acceptance recorded
Requirement reconciled
        -> fulfilment state updated independently of planning coverage

7.1 Partial acceptance

If a farmer is asked for 200 kg and accepts 120 kg, the system must record the accepted 120 kg as an allocation and leave the remaining 80 kg uncovered or available for additional planning. The UI must never visually imply the original 200 kg is fully committed.

7.2 Shortfall reporting

A farmer may report a full or partial shortfall against an active commitment. The report creates a domain event and triggers buyer-side recalculation. It must not directly mutate unrelated pages using local UI state.

7.3 Standby activation

Standby capacity is visibly distinct from committed capacity. Activation converts a specific quantity of standby supply into active committed coverage and records the commercial and cost implications.

8. Buyer Product Surface

8.1 /b - Requirement Portfolio

Purpose: give procurement users a prioritized view of all active requirements.

Each requirement card or row displays:

Crop and grade.

Required quantity.

Delivery window.

Destination site.

Committed quantity.

Standby quantity.

Uncovered quantity.

Health state.

Target delivery date.

Last meaningful event.

Default sort priority:

Uncovered or at-risk requirements.

Nearest target delivery date.

Recently changed requirements.

Coverage visualization:

[ Committed | Standby | Uncovered ]

Committed and standby must never share the same visual treatment.

8.2 /b/requirements/new/:step - Requirement Intake

Wizard sequence:

Crop
-> Grade / specification
-> Volume
-> Delivery window
-> Destination site
-> Commercial constraints
-> Review
-> Submit for Planning

Required data:

Crop taxonomy ID.

Grade/specification ID and version.

Required quantity in canonical kilograms.

Buyer-entered unit where applicable.

Earliest and latest acceptable delivery timestamps.

Destination site ID.

Receiving constraints.

Documentation/compliance requirements.

Optional commercial ceiling or price constraints where supported.

Primary action copy: Submit for Planning.

Unfillable requirements must return useful trade-offs rather than generic failure copy, for example: available volume, grade relaxation, alternate delivery window, or split-delivery options if those are supported by the planning engine.

8.3 /b/requirements/:id - Supply Assurance Dashboard

This remains the flagship buyer interface.

Requirement overview

Display prominently:

Required quantity.

Crop and grade.

Delivery window.

Destination.

Current coverage state.

Committed quantity.

Standby quantity.

Uncovered quantity.

Supply coverage bar

Segmented horizontal bar:

Committed: solid treatment.

Standby: hatched/striped or otherwise distinctly patterned.

Uncovered: muted treatment.

Allocation ledger

Each row includes:

Farmer display identity.

Farmer ID.

Parish.

Production lot ID where available.

Quantity.

Allocation role.

Allocation status.

Verification state where relevant.

Private contact details do not appear in the buyer ledger by default.

Recovery episode

The recovery panel must render domain events chronologically and distinguish:

What was lost.

Why the requirement became at risk.

Which standby capacity was activated.

When coverage returned.

What the recovery changed economically.

Risk panel

Risk is shown using qualitative bands only: LOW, MEDIUM, HIGH.

Every band must include plain-language drivers such as geographic concentration, limited standby coverage, compressed delivery window, or unresolved response status. The methodology must be documented at /methodology.

Economics panel

Display:

Original planned landed cost.

Recovered planned landed cost.

Absolute recovery delta.

Percentage delta.

Cost components when available.

Currency uses JMD consistently.

Fulfilment panel

Display required, received, accepted, rejected, and pending quantities separately. Before physical evidence exists, received/accepted/rejected values remain zero or unknown; the UI must not infer them from commitment data.

8.4 Participants

/b/requirements/:id/participants exposes the parties contributing to the plan using appropriate privacy controls. It may show legal identity when commercial commitment rules require disclosure, but it must not expose phone numbers or personal contact channels unnecessarily.

8.5 Events

/b/requirements/:id/events is the audit-oriented view of domain events and should support timestamps, actor, event type, affected quantity, and correlation/recovery episode identifiers.

9. Farmer Product Surface

9.1 /f - Mobile Action Queue

The farmer home is not an analytics dashboard. It is an ordered operational queue.

Sections:

Action Required - requests ordered by earliest response expiration.

Upcoming Commitments - scheduled obligations over the next 14 days.

Reserved Capacity - active standby commitments and release dates.

Financial Summary - settled and pending receivables when supported.

Profile Completion - only the most relevant missing setup action.

Request cards should show:

Quantity and grade.

Price per unit and total commercial value when available.

Destination / collection location.

Collection or delivery date.

Response expiration as absolute Jamaica time plus relative countdown.

Full accept, partial accept, decline, and coordinator help actions.

9.2 /f/requests/:id - Request Evaluation

The farmer can:

Accept full quantity.

Accept a partial quantity.

Decline with an optional structured reason.

Request coordinator assistance.

The page must show all material terms before acceptance.

Expired requests transition to an explicit terminal state. The interface must not allow a stale request to appear actionable simply because the client clock has not refreshed.

9.3 /f/commitments/:id - Commitment Management

Display:

Accepted quantity.

Grade/specification.

Scheduled date and location.

Current status.

Production lot association.

Commercial terms.

Standby/committed role where relevant.

Primary exception action: Report Issue / Shortfall.

Shortfall form:

Quantity still expected to be supplied.

Quantity at risk or lost.

Reason category.

Optional note.

Expected resolution if known.

Submitting the report records an event and triggers recalculation.

9.4 /f/standby - Reserved Capacity

Each standby item shows:

Reserved quantity.

Reservation validity window.

Activation conditions.

Release date.

Holding compensation if applicable.

Current status.

9.5 /f/record - Objective History

Do not display star ratings, credit-style grades, or hidden composite scoring.

Permitted metrics include:

Requests Answered: 12 of 14
Commitments Fulfilled: 9 of 10
Early Shortfall Notifications: 2
Partial Acceptances: 3

If the backend later computes planning confidence using historical behavior, the methodology must remain explainable and must not be presented to farmers as an arbitrary “reliability score.”

10. Operations Surface

10.1 /ops - Escalation Triage

The first implementation may be intentionally small.

Queue items may include:

Farmer requested coordinator assistance.

Requirement cannot be automatically recovered.

Organization approval pending.

Token-response issue.

Compliance or identity review required.

Each item needs:

Type.

Related entity IDs.

Created time.

Priority.

Current owner if assigned.

Status.

Link to relevant buyer/farmer context.

The route must be clearly marked as incomplete when backend actions are not yet available. Do not create fake “resolved” operations behavior purely for visual completeness.

11. Authentication and Onboarding

11.1 Authentication architecture

Keep real Supabase authentication, but hide provider-specific details behind an adapter.

AuthProvider
  -> AuthAdapter
       -> SupabaseAuthAdapter
       -> DemoAuthAdapter

DemoAuthAdapter exists for deterministic demos and local development. It must be gated by environment/build flags and visibly indicate DEMO BUILD.

11.2 Login

Buyer login may prioritize work email. Farmer login may prioritize phone-based flows when the backend supports OTP/SMS delivery. Until phone authentication is production-ready, the UI must not pretend that a code was delivered through an external channel.

11.3 Signup role router

Use two primary cards:

I GROW
I have crops to supply. Receive direct procurement requests for your produce.

I BUY
I purchase produce for a hotel, supermarket, restaurant, or institution. Submit requirements and monitor supply coverage.

11.4 Farmer onboarding

Categorical steps should use tappable token selectors where appropriate.

Minimum activation threshold:

Verified contact method.

Parish.

Primary crop.

At least one quantified capability row.

Capability row model:

Crop
-> declared quantity
-> declared unit
-> conversion to canonical kg
-> frequency
-> active harvest months
-> grade/specification
-> logistics context

Never treat packaging conversion as a universal constant. Persist:

crop_id
unit_id
declared_quantity
declared_unit
conversion_factor
conversion_source
conversion_version
converted_kg

11.5 Buyer onboarding

Collect:

Organization type.

User role.

Core produce requirements.

Typical weekly volume scale.

Delivery frequency.

Receiving capabilities.

Required documentation.

Historical supply bottlenecks.

All selectable values persist taxonomy IDs rather than raw UI labels.

12. Domain Model and State Machines

12.1 Requirement state

type RequirementState =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'PLANNING'
  | 'AWAITING_RESPONSES'
  | 'COVERED'
  | 'PARTIALLY_COVERED'
  | 'AT_RISK'
  | 'REPLACEMENT_UNDERWAY'
  | 'UNFILLABLE'
  | 'PAUSED'
  | 'CANCELLED';

12.2 Request state

type RequestState =
  | 'PENDING'
  | 'VIEWED'
  | 'ACCEPTED'
  | 'PARTIALLY_ACCEPTED'
  | 'DECLINED'
  | 'EXPIRED'
  | 'WITHDRAWN'
  | 'SUPERSEDED';

12.3 Allocation state

type AllocationState =
  | 'PROPOSED'
  | 'COMMITTED'
  | 'STANDBY'
  | 'STANDBY_ACTIVATED'
  | 'RELEASE_REQUESTED'
  | 'RELEASED'
  | 'LOST'
  | 'REPLACED';

12.4 Verification state

type VerificationState =
  | 'NOT_PROVIDED'
  | 'SELF_DECLARED'
  | 'EVIDENCE_SUBMITTED'
  | 'UNDER_REVIEW'
  | 'VERIFIED'
  | 'REJECTED'
  | 'EXPIRED';

12.5 Fulfilment state

type FulfilmentState =
  | 'AWAITING_RECEIPT'
  | 'PARTIALLY_RECEIVED'
  | 'RECEIVED'
  | 'GRADING_IN_PROGRESS'
  | 'PARTIALLY_ACCEPTED'
  | 'ACCEPTED'
  | 'RECONCILED'
  | 'CLOSED';

12.6 Required invariants

Committed quantity cannot exceed the sum of active committed allocations.

Standby quantity is not counted as committed coverage until activation.

Received quantity is not inferred from committed quantity.

Accepted + rejected quantity cannot exceed received quantity.

A partial acceptance must preserve the unaccepted remainder for further planning or explicit cancellation.

Expired requests are not actionable.

Every recovery action must be attributable to domain events.

13. Event Model and Deterministic Demo Engine

Pages do not own demo truth. Events own demo truth.

13.1 Minimum event vocabulary

requirement.created
requirement.submitted
requirement.planning_started
request.sent
request.viewed
request.accepted
request.partially_accepted
request.declined
request.expired
allocation.committed
allocation.standby_created
allocation.shortfall_reported
allocation.lost
requirement.at_risk
recovery.started
allocation.standby_activated
requirement.coverage_restored
recovery.cost_changed
receipt.recorded
grade.accepted
grade.rejected
requirement.reconciled
ops.escalation_created

13.2 Event envelope

Every event should support:

interface DomainEvent<TPayload = unknown> {
  id: string;
  type: string;
  occurredAt: string;
  actorType: 'BUYER' | 'FARMER' | 'OPS' | 'SYSTEM';
  actorId?: string;
  requirementId?: string;
  requestId?: string;
  allocationId?: string;
  recoveryEpisodeId?: string;
  payload: TPayload;
  source: 'LIVE' | 'DEMO';
}

13.3 Projections

The following views must derive from the same event/domain state:

Buyer dashboard.

Farmer queue.

Farmer commitment detail.

Notifications.

Recovery timeline.

Economics.

Ops triage.

Demo controller.

13.4 Demo controls

/dev/demo may expose explicit scenario controls such as:

Reset fixture.

Accept farmer request.

Report 80 kg shortfall.

Activate standby replacement.

Record receipt.

These controls must be hidden from production builds and labeled DEMO BUILD when enabled.

14. Reference Demo Fixture

The canonical demo scenario is:

Field

Value

Buyer

Blue Mountain Lodge

Destination

Montego Bay, Jamaica

Crop

Grade A fresh ginger

Requirement

500 kg

Initial committed coverage

500 kg

Standby reserve

At least 80 kg available within the fixture

Disruption

Nadine Ellis reports/loses 80 kg

Coverage after disruption

420 kg

Health after disruption

AT_RISK

Recovery

80 kg standby activation from Peter Wallace

Recovered committed coverage

500 kg

Original planned landed cost

J$186,800

Recovered planned landed cost

J$191,400

Recovery delta

+J$4,600

Recovery delta percent

2.46%

Fulfilment checkpoint

St. James Collection Hub

Initial receipt state

0 kg received; awaiting evidence

The exact farmer ledger may contain additional committed and standby participants, but any demo reset must return to a deterministic set of IDs, quantities, lots, prices, and timestamps.

15. Adapter, View-Model, and Data Architecture

Required frontend flow:

API / Supabase / Demo Event Store
        -> domain adapters
        -> typed domain model
        -> feature selectors / view-models
        -> React components

Components must not contain provider-specific response parsing.

Recommended structure:

src/
  app/
  components/
  features/
    identity/
    onboarding/
    farmerRequests/
    requirements/
    assurance/
    risk/
    economics/
    events/
    fulfilment/
    operations/
  layouts/
    BuyerLayout.tsx
    FarmerLayout.tsx
    OpsLayout.tsx
  taxonomy/
    crops.ts
    parishes.ts
    units.ts
    grades.ts
  api/
    client.ts
    adapters/
    contracts/
    mocks/
  domain/
    events/
    selectors/
    state-machines/
  types/

15.1 API gap documentation

docs/frontend-api-gap.md should contain only unresolved contracts, for example:

Endpoint/action needed.

Request shape.

Response shape.

Authentication/authorization assumption.

Error states.

Whether mock behavior currently exists.

Do not use the API-gap document as a substitute for product requirements.

16. UX, Visual Language, and Copy Standards

16.1 Design character

KoroFarm should feel like credible procurement infrastructure, not a cartoon farm app and not a generic admin template.

Buyer UI:

Information-dense where useful.

Clear hierarchy.

Strong supply-status visualization.

Desktop-first with responsive collapse.

Farmer UI:

Mobile-first.

Large touch targets (minimum 48 px recommended).

Short pages and clear actions.

Minimal decorative motion.

Avoid heavy external font dependencies where possible.

16.2 Required terminology

Preferred terms:

Submit for Planning

Committed Coverage

Standby Capacity

Uncovered Volume

Coverage Restored

Availability Confidence when a qualitative confidence concept is necessary

Fulfilled 9 of 10 Commitments for objective history

Awaiting Receipt before physical evidence

16.3 Prohibited or restricted terminology

Do not use the following in ways that overstate evidence:

Guarantee / Guaranteed delivery

Probability of fulfilment as an unsupported percentage

Credit Score

Bankability Score

Star Rating

Reliability Index

Delivered / In Transit before physical evidence supports the state

Marketplace

Shop

Browse Listings

Storefront

The existing “Guarantee Your Supply” intro copy must be replaced. Recommended product-safe alternatives include Supply Assurance, Protect Your Supply Plan, or Maintain Supply Coverage.

16.4 Status semantics

Do not rely on color alone. Every meaningful status requires text/icon/pattern support.

Recommended buyer supply states:

COVERED

PARTIALLY_COVERED

AT_RISK

UNFILLABLE

Recommended visual treatment:

Committed: solid fill.

Standby: patterned or hatched fill.

Uncovered: muted empty remainder.

At risk: warning icon and explicit shortfall.

17. Loading, Empty, Error, and Terminal States

Every product page must define all four.

17.1 Loading

Use skeletons for structural pages and compact spinners only for short inline actions. Authentication session resolution must not flash protected content.

17.2 Empty

Examples:

Buyer has no requirements: explain how to create the first requirement.

Farmer has no active requests: confirm there is nothing requiring action.

No standby items: explain that there is no reserved capacity currently active.

17.3 Error

Errors must identify what failed and what the user can do next. Avoid displaying raw backend error strings.

17.4 Terminal states

Expired, declined, cancelled, released, reconciled, and closed objects remain readable but clearly non-actionable.

18. Security and Privacy Requirements

Protected routes require authenticated sessions and server-enforced authorization.

Role and organization authorization must not depend solely on user-editable metadata.

/r/:token uses signed, expiring, single-purpose tokens.

Buyer views do not expose farmer phone numbers or private contact details by default.

Farmer views expose all material commercial terms relevant to the farmer's decision.

Demo controls are unavailable in production builds.

Public environment variables contain only browser-safe publishable configuration.

Sensitive service credentials never ship to the browser bundle.

Supabase RLS policies must mirror organization/persona access rules when Supabase tables are used directly from the client.

19. Performance, Accessibility, and Responsiveness

19.1 Farmer performance budget

The farmer surface should target a lightweight initial experience. Treat <150 KB of route-specific client JavaScript as an aspirational budget, measured rather than assumed. Heavy animation libraries should not be required on farmer routes.

19.2 Accessibility

Keyboard-accessible controls.

Visible focus states.

Semantic headings.

Form labels and validation messages associated programmatically.

Status information not encoded by color alone.

Tables remain horizontally usable on narrow screens or collapse into accessible card representations.

Countdown timers include an absolute expiration time and do not rely on continuously changing text as the sole source of meaning.

19.3 Time

All operational deadlines display in America/Jamaica time and include an absolute timestamp. Relative phrases such as “2 days remaining” supplement rather than replace the absolute time.

20. Testing Strategy

20.1 Unit tests

Prioritize:

Coverage calculations.

Partial acceptance math.

Allocation/standby transitions.

Cost delta calculations.

Unit conversions and versioning.

Time-expiration logic.

State-machine guards.

Event projection selectors.

20.2 Component tests

Cover:

Supply coverage bar segmentation.

Buyer allocation ledger states.

Farmer request actions.

Shortfall reporting.

Risk explanation rendering.

Fulfilment separation.

20.3 End-to-end tests

Mandatory reference flow:

Buyer has a 500 kg requirement.

Requirement is covered.

Farmer reports an 80 kg shortfall.

Buyer view changes to 420 kg and AT_RISK.

Standby farmer is activated for 80 kg.

Buyer returns to 500 kg committed coverage.

Recovery cost updates by J$4,600.

Fulfilment remains awaiting physical receipt.

Additional E2E scenarios:

Partial farmer acceptance.

Request expiry.

Buyer creates a new requirement.

Unauthorized persona attempts protected route.

Demo reset produces identical fixture state.

21. Definition of Done

A frontend milestone is complete only when the following applicable criteria are satisfied:

Authentication resolves a user session without protected-content flash.

Persona authorization routes the user to the correct application context.

Onboarding persists taxonomy IDs rather than only display strings.

Farmer quantified capability rows retain declared units, converted kilograms, and conversion version metadata.

Farmer action queue prioritizes requests by server-authoritative response expiration.

Partial acceptance updates the uncovered remainder accurately.

Shortfall reporting creates a domain event and buyer-side coverage recalculates from shared state.

Standby activation visibly changes allocation role/state and coverage.

Buyer coverage, notifications, farmer state, recovery timeline, and economics remain mutually consistent because they use the same domain scenario.

Fulfilment never claims physical receipt without evidence.

Risk uses qualitative bands with visible explanation.

Objective farmer history is displayed without arbitrary ratings/scores.

Terminal request states are explicit and non-destructive.

Jamaica time is shown for operational deadlines.

Demo controls are build-flagged and visibly labeled.

Role-specific routes meet accessibility and responsive-layout requirements.

Provider-specific responses are adapted before reaching presentation components.

Unrelated room/sensor/energy/AI template code is removed or isolated from active KoroFarm features.

Key state transitions and calculations have automated coverage.

The canonical 500 kg -> 420 kg -> 500 kg recovery scenario passes end-to-end.

22. Recommended Execution Sequence

Phase 0 - Consolidate

Add this document to docs/product-frontend-spec.md.

Mark the old buyer-only scope restriction as superseded.

Verify package versions and remove outdated stack labels.

Isolate unrelated room/sensor/AI template code.

Phase 1 - Shared domain foundation

Define TypeScript domain contracts.

Implement event vocabulary and deterministic fixture.

Implement selectors/view-models for coverage, shortfall, recovery, economics, and notifications.

Ensure the existing dashboard renders from those selectors.

Phase 2 - Identity and layouts

Introduce AuthAdapter.

Preserve SupabaseAuthAdapter.

Add gated DemoAuthAdapter.

Implement role-aware authorization and BuyerLayout, FarmerLayout, OpsLayout.

Phase 3 - Farmer operational loop

Build /f action queue.

Build request detail with full/partial/decline actions.

Build commitment detail.

Implement shortfall reporting.

Wire shortfall events into the buyer dashboard.

Phase 4 - Recovery loop

Implement standby activation through domain actions.

Ensure buyer risk, economics, notifications, and farmer state all update from shared state.

Complete the canonical cross-persona demo flow.

Phase 5 - Buyer creation workflow

Build requirement portfolio.

Build requirement intake wizard.

Add unfillable/trade-off states.

Phase 6 - Onboarding and profile depth

Build role-aware onboarding.

Add taxonomy dictionaries.

Add unit conversion metadata and readback verification.

Phase 7 - Fulfilment and evidence

Implement physical receipt and grading workflows when backend contracts are ready.

Keep compliance and trade-evidence modules as explicit placeholders until supported.

23. Explicitly Out of Scope for the Current Frontend Program

Unless separately approved, the following are not required for the current frontend program:

Open farmer marketplace or public browsing directory.

Live WhatsApp/SMS gateway integration.

Payment processing or settlement escrow.

Lending, credit underwriting, or farmer credit scores.

Full warehouse-management functionality.

Automated GIS route optimization.

IoT hardware integration.

Live regulatory portal submission.

Unsupported predictive fulfilment probabilities.

Production-grade organization verification automation.

These may become separate product programs without changing the core KoroFarm supply-assurance model.

24. Open Decisions Requiring Backend/Product Alignment

These items do not block the domain model but need formal decisions before production launch:

Phone authentication provider and recovery flow for farmers.

Organization verification and invitation/approval policy.

Rules governing legal identity disclosure between buyer and farmer.

Standby holding-fee commercial model.

Authoritative crop/grade taxonomy owner and versioning policy.

Unit conversion governance and approved conversion sources.

How recovery actions are approved when the recovered landed cost exceeds buyer thresholds.

Which fulfilment evidence is sufficient to move from received to accepted/reconciled.

Operations escalation ownership and SLA.

Data retention and audit-log retention policy.

Until resolved, the frontend should represent these as explicit configuration/backend gaps rather than silently inventing permanent behavior.

25. Product Language Summary

KoroFarm coordinates and preserves supply coverage. It does not claim physical delivery before evidence exists.

The canonical mental model is:

Requirement
-> Requests
-> Allocations
-> Committed + Standby Coverage
-> Disruption
-> Recovery
-> Physical Receipt
-> Grading / Acceptance
-> Reconciliation

Every persona view, demo fixture, API contract, event, and frontend component should reinforce that model.