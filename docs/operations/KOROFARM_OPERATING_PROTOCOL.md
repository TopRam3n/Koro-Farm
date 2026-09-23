# KoroFarm operating protocol

This vocabulary is authoritative across product, operations, analytics, and
evaluations. States are not interchangeable.

| State | Meaning and authorized creator | Evidence/freshness | Does not mean |
|---|---|---|---|
| Expected supply | Forecast production associated with a farmer lot. Farmer or coordinator may report it. | Source, effective date, and freshness expiry required. | Available, committed, received, or accepted supply. |
| Available supply | Quantity currently eligible for allocation under lot status, harvest window, verification, and freshness policy. | Current observation and its verification state must be visible. | Expected harvest or a promise to a buyer. |
| Committed supply | Explicit allocation counted toward a requirement after the applicable consent/acceptance rule. | Allocation, plan version, consent reference, and event. | Standby, received, accepted, or delivered supply. |
| Standby supply | Capacity reserved and previously authorized for possible activation. | Standby allocation and authorization evidence. | Committed coverage until valid activation. |
| Received supply | Physical quantity recorded at a fulfilment node. Warehouse operator creates it. | Receipt time, node, allocation, actor, and receipt evidence when available. | Accepted quality or shippable quantity. |
| Accepted supply | Received quantity accepted by inspection. Warehouse grading authority creates it. | Complete inspection accounting and grade/evidence. | Total received quantity or replacement commitment. |
| Rejected supply | Received quantity rejected during inspection. | Rejection quantity, reason, inspection actor, and evidence. | Shippable supply; it remains traceable and may trigger recovery. |
| Shipped supply | Accepted sublots assigned to a dispatched shipment. | Shipment composition and dispatch event/evidence. | Delivery or buyer acceptance. |
| Delivered supply | Dispatched quantity recorded as delivered. | Delivery timestamp and proof-of-delivery reference. | Buyer confirmation or reconciliation. |
| Buyer confirmed | Buyer explicitly confirms delivery. | Buyer confirmation evidence is mandatory. | Internal delivery assertion. |
| Reconciled | Required, committed, accepted, delivered, and buyer-confirmed quantities are compared and frozen. | Verified delivery and buyer confirmation; unresolved disputes remain visible. | Perfect fulfilment or automatic trade evidence. |
| Trade evidence | Structured history derived only from eligible reconciled records. | Trace chain, reconciliation, confirmation, verification reference, and dispute policy. | Credit score, financing eligibility, or unsupported farmer claim. |

## Provenance

Verification and freshness are independent. `SELF_REPORTED + CURRENT` is valid
and useful but not equivalent to `WAREHOUSE_VERIFIED`. An observation becomes
stale or expired according to the applicable policy even if it was previously
verified. Operators must see the source channel, actor, effective time,
verification status, and freshness status wherever the observation affects a
decision.

## Legal transition principles

- Planning cannot reserve beyond verified availability.
- Standby cannot become committed without a valid activation path.
- Receipt cannot exceed its allocation.
- Accepted plus rejected must account for, and never exceed, received supply.
- Rejected supply cannot enter a shipment.
- Dispatch is not delivery.
- Delivery without buyer evidence cannot be reconciled.
- Trade evidence cannot precede eligible reconciliation.
- Buyer-caused changes remain separate from farmer performance evidence.
- Invalid, stale, ambiguous, unauthorized, or cross-tenant input is blocked or
  routed to verification/decision handling; KoroFarm does not force success.
