# KoroFarm Product Architecture Baseline

Assessment date: 2026-09-20  
Git baseline: `19148bb47ac84a040a4ff3d10733b007a1ece4e2` plus uncommitted frontend redesign work present in the shared workspace.

## Current frontend

App Router routes before this transformation:

- `/` — authenticated single-requirement assurance control room
- `/login`, `/signup` — Supabase authentication
- `/notifications` — requirement event stream
- `/profile` — account identity and sign-out

Legacy `src/pages` components remain as implementation modules and also generate duplicate Pages Router build entries. They are retained to avoid destabilizing the current application before Demo Day.

The Overview currently consolidates assurance, recovery, economics, fulfilment summary, allocation ledger, geographic exposure, traceability state, compliance unknown-state, trade evidence state, and event activity.

## Backend capability inventory

Read APIs:

- health
- requirement by ID
- production-lot list and detail
- assurance, immutable risk snapshot, and requirement events
- requirement fulfilment summary
- received-sublot, shipment, and production-lot traceability
- requirement compliance lookup
- farmer trade-performance passport
- trade-corridor list and detail

State-changing APIs:

- create requirement and record buyer change
- create initial plan
- record allocation dropout; accept or decline solicitation
- run recovery
- receive and grade sublots
- create shipment; add accepted sublots; dispatch; record delivery
- reconcile a requirement

All material frontend commands use idempotency keys. The current browser UI exposes plan creation, one deterministic dropout, recovery, and solicitation acceptance. No delete endpoint exists.

## Domain entities

Buyer, Requirement, BuyerOrderChange, Farmer, ProductionLot, SupplyPlan, SupplyAllocation, RecoveryRun, DomainEvent, CommandDeduplication, OutboxMessage, CostSnapshot, LotCostInput, RiskSnapshot, FulfilmentNode, ReceivedSublot, ComplianceRule, Shipment, ShipmentSublot, Delivery, RequirementReconciliation, and TradeCorridor.

Core value types include quantity in kilograms, JMD money, date window, crop, grade, and availability confidence.

## Authentication and authorization

Supabase owns browser sessions. The frontend attaches the access token to API requests. FastAPI validates it through Supabase `/auth/v1/user`. A demo bypass is permitted only when `ALLOW_INSECURE_DEMO_AUTH=true` and `APP_ENV` is `test` or `demo`. There is no implemented role-based authorization; procurement, warehouse, coordinator, and administrator experiences remain future RBAC work.

## Data and demo behavior

The PostgreSQL seed contains one deterministic synthetic competition requirement, eight synthetic farmers, and eight lots. The explicit offline frontend demo mirrors the canonical 500 kg requirement, 100 kg standby, 80 kg dropout, and successful recovery. Demo mode is visible and never activated automatically after a live API failure.

## Important platform gaps

- No requirement-list or programme aggregate API; a true multi-programme Command Center cannot yet be authoritative.
- Programme and recovery-case identifiers are not first-class persisted entities.
- No global farmer list API; farmers are visible through lots and allocations.
- No global event, shipment, compliance, or evidence registry API.
- No safe dry-run recovery-planning endpoint. Scenario Lab must remain a clearly labelled local simulation and cannot claim backend-authoritative candidate selection.
- No RBAC model beyond authenticated versus demo access.
- No configured external integrations registry.

## Proposed route map

| Route | Workspace | Data posture |
|---|---|---|
| `/` | Command Center | One configured authoritative requirement; fleet aggregation unavailable |
| `/programmes` | Programmes | Configured requirement grouped as one programme |
| `/programmes/[id]` | Programme workspace | Summary links to requirement workspaces |
| `/demand` | Demand | Configured requirement table |
| `/requirements/[id]` | Requirement workspace | Authoritative assurance object with tab-like deep links |
| `/supply` | Supply Network | Allocation-backed farmers and production lots |
| `/farmers/[id]` | Farmer workspace | Allocation-derived view; no scores or financing claims |
| `/assurance` | Assurance Center | Exception-oriented requirement view |
| `/scenario-lab` | Scenario Lab | Non-persistent simulation, visibly labelled |
| `/fulfilment` | Fulfilment Center | Authoritative requirement fulfilment summary |
| `/network` | Network Intelligence | Allocation-derived parish distribution |
| `/compliance` | Compliance Registry | Honest no-rule state unless API returns a verified record |
| `/traceability` | Traceability Explorer | Existing relationship stages; missing links remain missing |
| `/trade-evidence` | Trade Evidence | Building-history state until verified reconciliation exists |
| `/analytics` | Analytics | Ratios derived from authoritative current quantities only |
| `/agent-operations` | Agent Operations | Structured recovery/event evidence; no chain-of-thought |
| `/activity` | Activity & Audit | Requirement event stream |
| `/integrations` | Integrations | Actual identity/API configuration state only |
| `/settings` | Administration | Environment and account posture; RBAC explicitly unavailable |

## Design and implementation rule

Every workspace must distinguish authoritative API state, system-derived display values, unavailable data, and client-only simulations. No route may invent additional programmes, customers, farmers, compliance rules, historical outcomes, or integrations to appear more complete.
