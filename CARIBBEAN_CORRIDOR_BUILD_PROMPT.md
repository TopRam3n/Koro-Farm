# KoroFarm Caribbean Corridor Expansion — Build Prompt

## Product intent

Extend KoroFarm from domestic Jamaican supply assurance into a Caribbean agricultural trade-assurance layer. This remains an execution and assurance product, not a farmer discovery marketplace.

The buyer should experience one reliable programme even when supply is fragmented across small farms, collection nodes, islands, compliance requirements, and logistics providers.

## First expansion milestone

Build **Corridor v1**, supporting a controlled inter-island trade lane without claiming that trade is compliant, booked, dispatched, or accepted unless evidence exists.

Use only synthetic data. Start with one configurable corridor such as Jamaica to Barbados. Do not hard-code regulatory requirements or claim regional coverage.

## Domain additions

Create a `TradeCorridor` with:

- origin country and destination country;
- transport mode and named route;
- active status;
- default dispatch lead time;
- named export and import fulfilment nodes;
- verified corridor status and last verification timestamp.

Attach a requirement to an optional corridor. Domestic requirements must continue to work without one.

Add a logistics-planning state that can represent:

- unplanned, planned, booked, dispatched, delayed, delivered, and cancelled;
- carrier/route reference, cut-off time, planned departure and arrival;
- cold-chain verification as `true`, `false`, or `null`;
- evidence references for bookings, handoffs, and temperature logs.

## Compliance rules

Extend rule lookup from domestic country matching to corridor-aware lookup.

- Every returned rule must have source citation, source version, verifier, and verification timestamp.
- If a route/product combination has no matching verified rule, return exactly `no_verified_rule_on_file`.
- Never infer import permits, phytosanitary certificates, tariffs, or labelling obligations from a model.

## Supply and logistics assurance

Keep supply risk and logistics risk distinct.

Supply risk considers production availability, concentration, reserve coverage, replacement depth, quality, and farmer history.

Logistics risk considers route capacity, cut-off exposure, transit time, node capacity, cold-chain evidence, carrier dependency, and disruption status.

The agent may recommend or prepare a recovery plan but must not book transport, alter buyer substitutions, or accept farmer commitments without explicit authority.

## Exports and trade evidence

Preserve the full chain:

`farmer → production lot → commitment → received sublot → accepted sublot → shipment → corridor movement → delivery → reconciliation`

Trade Performance Passports remain descriptive supplier evidence. Display `Financing eligibility: NOT_ASSESSED` at all times.

## Human authority gates

Require explicit human approval for:

- farmer acceptance or decline;
- buyer substitutions or material order changes;
- compliance document approval;
- transport booking and shipment dispatch;
- unresolved shortfalls, disputes, and payment/financing decisions.

## Acceptance criteria for Corridor v1

1. A requirement can be domestic or attached to one active corridor.
2. Compliance lookup is corridor-aware and truthful when no rule is on file.
3. Shipment records preserve farmer sublot identity through delivery.
4. Logistics verification fields are nullable until actual evidence is recorded.
5. APIs are idempotent for delivery and prevent duplicate sublot shipment assignment.
6. The UI clearly labels domestic versus corridor programmes and never misstates verification.
7. Tests cover domestic backward compatibility, corridor rule lookup, and missing-evidence behaviour.

## Delivery sequence

1. Corridor model, migration, and requirement attachment.
2. Corridor-aware compliance query and synthetic demo seed.
3. Logistics movement/evidence model.
4. Separate supply and logistics risk summaries.
5. Coordinator dashboard and corridor execution controls.
6. One end-to-end synthetic Jamaica-to-Barbados demonstration.
