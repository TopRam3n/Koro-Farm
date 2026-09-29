# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is an institutional buyer-side supply operator — typically a supply coordinator, procurement/purchasing professional, or equivalent operations role — responsible for keeping agricultural buyer commitments reliable. They coordinate available supply, farmer responses, disruptions, approvals, receipt and inspection, and fulfilment exceptions.

## Product Purpose

KoroFarm is a web-based, coordinator-led supply-assurance product, initially grounded in Jamaica with Caribbean expansion intended. Its defining promise is to turn fragmented agricultural production into dependable institutional supply through continuous coverage monitoring, governed disruption recovery, physical fulfilment verification, and auditable reconciliation.

## Positioning

Authorized reserve/standby supply is a primary recovery mechanism, but the system must escalate rather than invent coverage when sufficient supply does not exist. Committed and standby supply remain distinct, and solicited supply is not committed until a farmer explicitly accepts. KoroFarm is not a marketplace. Its role begins once demand and potential supply exist: it coordinates, monitors, recovers, verifies and reconciles the fulfilment process.

## Operating Context

- Jamaica is the initial market, with Caribbean expansion intended. Current domain workflows use quantities in kilograms, JMD money, and Jamaican parish-level supply information.
- Coordinators review stale and expiring observations. Farmers respond through governed channels; procurement reviews cases requiring commercial authority; warehouse staff record receipt and inspection separately; buyers confirm reconciliation.
- The product is a web application with a Next.js frontend, a FastAPI domain API, and Supabase sign-in. Live API access requires an authenticated session and organization context.

## Capabilities and Constraints

- Demand requirements can be planned against production lots with separate committed and standby allocations. Plans and cost and structural-risk snapshots are immutable.
- Recovery and fulfilment record explicit events. Planned, committed, received, accepted, rejected, shipped, and delivered quantities are distinct states.
- Risk snapshots are deterministic structural assessments, not predictions or farmer scores. Compliance and trade evidence are only reported from verified records; missing evidence remains explicitly unavailable.
- Organization ownership and role-based authorization are implemented in the application model, but production tenant isolation is not yet certified against the deployed stack. Until that verification is complete, real customer or farmer data must not be used.
- Pilot targets and monetary savings are not measured unless supported by recorded events and an approved baseline and counterfactual.

## Brand Commitments

The product name KoroFarm is fixed. No additional voice or personality commitment has been established.

## Evidence on Hand

Available demonstrations use synthetic organizations, farmers, supply, events, and evidence references. They cover planning, disruption recovery, quality rejection, fulfilment, and reconciliation, but do not establish real customer outcomes. There are no verified testimonials, measured savings, or production-readiness claims; future work must not invent these.

## Product Principles

1. Keep planned and committed supply distinct from physical receipt, acceptance, shipment, and delivery.
2. Count solicited supply only after explicit farmer acceptance. Use authorized standby according to the applicable recovery policy before broader supply discovery or escalation; never manufacture coverage when sufficient eligible supply does not exist.
3. Keep planning, risk, and cost decisions deterministic and auditable, and require authorization for consequential actions.
4. Make unknown, stale, missing, or unverified information explicit instead of filling gaps with assumptions.
5. Make outcome and compliance claims only when backed by verified evidence and measured baselines.

## Accessibility & Inclusion

Target WCAG 2.2 AA where practical, with strong contrast, keyboard access, visible focus, semantic labels, and status communication that does not rely on color alone. Field and farmer workflows must be mobile-first and usable on small phones outdoors, with limited connectivity and no training: use large tap targets, plain language, readable text, minimal steps, and low-bandwidth behavior. Clearly label every supply quantity state and critical status so users never have to infer its meaning from color or layout.