# KoroFarm — Frontend Design Brief

> Caribbean Agricultural Supply Assurance Platform  
> Backend: FastAPI · SQLAlchemy · PostgreSQL  
> Currency: **JMD (Jamaican Dollar)**  
> Currently single crop: **GINGER** · Grades: **A / B**

---

## 1. What the System Does

KoroFarm connects **buyers** (institutional purchasers) with **farmers** (ginger producers) through an **Assurance** workflow. A procurement manager creates a **Requirement** (how many kg of ginger a buyer needs by when), the system builds a **Supply Plan** that commits and buffers production lots from farmers, monitors **supply health**, triggers **recovery** when farmers drop out, tracks physical **fulfilment** (receiving, grading, shipment, delivery), and generates **reconciliation** records and a **farmer trade-performance passport** for financing eligibility.

---

## 2. User Roles & What They Can Do

| Role | Key Capabilities |
|---|---|
| **PLATFORM_ADMIN** | Everything |
| **ORGANIZATION_ADMIN** | View all, user management, approve recovery, approval policies |
| **PROCUREMENT_MANAGER** | Create/update requirements, view supply & trade evidence, approve recovery |
| **SUPPLY_COORDINATOR** | Manage supply, propose & execute recovery, view receiving |
| **WAREHOUSE_OPERATOR** | Record receiving, grade sublots, create & dispatch shipments, confirm delivery |
| **AUDITOR** | Read-only across requirements, supply, trade evidence, compliance, users |
| **FARMER** | View their own production lots & trade evidence only |

> **Auth mechanism**: JWT-based. Token carries `user_id`, `organization_id`, `role`, and optionally `farmer_id`. All routes except login, invitation accept, and secure-action pages require auth.

---

## 3. API Surface — Modules & Endpoints

### 3.1 Identity & Access  `/` (no prefix for identity)
| Method | Path | Description |
|---|---|---|
| GET | `/me` | Current user profile + organizations + active role |
| GET | `/admin/organization` | Org details (name, slug, active) |
| GET | `/admin/users` | List all members with role + status |
| POST | `/admin/users/invitations` | Invite a new user, returns `invitation_token` |
| POST | `/invitations/accept` | Accept invite with token |
| PATCH | `/admin/users/{membership_id}/role` | Change a member's role |
| POST | `/admin/users/{membership_id}/deactivate` | Deactivate membership |
| GET | `/admin/roles` | List all roles and their permissions |

### 3.2 Requirements (Demand)  `/requirements`
| Method | Path | Description |
|---|---|---|
| POST | `/requirements` | Create a requirement |
| GET | `/requirements` | List (filter: `supply_health`, `lifecycle_status`, `buyer_id`, `programme_id`, pagination) |
| GET | `/requirements/{id}` | Get single requirement |
| POST | `/requirements/{id}/buyer-change` | Record quantity change by buyer |

### 3.3 Assurance (Plans, Recovery, Events)  `/requirements`
| Method | Path | Description |
|---|---|---|
| POST | `/requirements/{id}/plan` | Generate supply plan (idempotent via `Idempotency-Key` header) |
| GET | `/requirements/{id}/assurance` | **Key dashboard endpoint** — full assurance view |
| GET | `/requirements/{id}/risk` | Risk snapshot |
| GET | `/requirements/{id}/events` | Event audit log for requirement |
| POST | `/requirements/{id}/recovery` | Advance the recovery state machine |

### 3.4 Allocations  `/allocations`
| Method | Path | Description |
|---|---|---|
| POST | `/allocations/{id}/accept` | Farmer accepts allocation |
| POST | `/allocations/{id}/decline` | Farmer declines allocation |
| POST | `/allocations/{id}/dropout` | Record farmer dropout (triggers recovery) |

### 3.5 Production Lots (Supply)  `/production-lots`
| Method | Path | Description |
|---|---|---|
| GET | `/production-lots` | List lots (farmers only see their own) |
| GET | `/production-lots/{id}` | Single lot |

### 3.6 Fulfilment  (no prefix)
| Method | Path | Description |
|---|---|---|
| POST | `/sublots/receive` | Record physical receipt of goods |
| POST | `/sublots/{id}/grade` | Record grading result |
| GET | `/requirements/{id}/fulfilment` | Fulfilment summary (received/accepted/rejected kg) |
| GET | `/sublots/{id}/traceability` | Full farmer→lot→allocation→sublot chain |

### 3.7 Reconciliation & Trade Evidence  (no prefix)
| Method | Path | Description |
|---|---|---|
| POST | `/requirements/{id}/shipments` | Create a shipment |
| POST | `/shipments/{id}/sublots` | Add a graded sublot to shipment |
| POST | `/shipments/{id}/dispatch` | Mark shipment dispatched |
| POST | `/shipments/{id}/delivery` | Record delivery with buyer confirmation |
| POST | `/requirements/{id}/reconcile` | Close the trade, compute fulfilment rate |
| GET | `/farmers/{id}/trade-performance-passport` | Farmer's institutional trade record |
| GET | `/shipments/{id}/traceability` | Shipment → sublot → farmer chain |
| GET | `/production-lots/{id}/shipments` | All shipments linked to a lot |

### 3.8 Programmes  `/programmes`
| Method | Path | Description |
|---|---|---|
| POST | `/programmes` | Create programme (buyer + date range) |
| GET | `/programmes` | List with supply health rollup |
| GET | `/programmes/{id}` | Programme detail + requirement counts |
| POST | `/programmes/{id}/requirements/{req_id}` | Associate requirement with programme |

### 3.9 Compliance  `/requirements/{id}/compliance`
| Method | Path | Description |
|---|---|---|
| GET | `/requirements/{id}/compliance` | List applicable export compliance rules |

### 3.10 Registry (Operational Read)  (no prefix)
| Method | Path | Description |
|---|---|---|
| GET | `/farmers` | Farmer list with production & committed kg |
| GET | `/allocations` | All allocations (filterable by req, role, status) |
| GET | `/recovery-cases` | All recovery runs |
| GET | `/recovery-cases/{id}` | Recovery detail + events |
| GET | `/received-sublots` | Received sublots (filterable by inspection status) |
| GET | `/shipments` | Shipments list |
| GET | `/activity` | Domain event log |
| GET | `/compliance-rules` | All compliance rules |
| GET | `/command-center/summary` | **KPI dashboard aggregate** |

### 3.11 Ingestion  `/v1/ingestion`, `/v1/secure-actions`
| Method | Path | Description |
|---|---|---|
| POST | `/v1/ingestion/secure-links` | Create a one-time farmer action link |
| GET | `/v1/secure-actions/{token}` | Inspect link (public) |
| POST | `/v1/secure-actions/{token}` | Execute: farmer updates availability/harvest dates (public) |
| POST | `/v1/ingestion/coordinator-observations` | Coordinator records field observation |
| GET | `/v1/ingestion/imports/templates/{entity_type}` | Download CSV template |
| POST | `/v1/ingestion/imports/preview` | Preview + validate CSV import |
| POST | `/v1/ingestion/imports/{id}/confirm` | Commit validated import |

---

## 4. Core Data Models (for Frontend Shapes)

### Requirement
```ts
{
  id: UUID
  buyer_id: UUID
  programme_id: UUID | null
  trade_corridor_id: UUID | null
  crop: "GINGER"
  grade: "A" | "B"
  required_quantity_kg: Decimal
  delivery_window_start: date   // "YYYY-MM-DD"
  delivery_window_end: date
  lifecycle_status: "DRAFT" | "PLANNING" | "ACTIVE" | "IN_FULFILMENT" | "RECONCILED" | "CLOSED" | "CANCELLED"
  supply_health: "UNPLANNED" | "COVERED" | "AT_RISK" | "RECOVERING" | "ESCALATION_REQUIRED"
  plan_version: int
  version: int
}
```

### AssuranceRead (richest response — the main detail view)
```ts
{
  requirement: { id, crop, grade, required_quantity_kg, lifecycle_status, supply_health,
                 plan_version, buyer_name, buyer_type, destination,
                 delivery_window_start, delivery_window_end }
  supply_health: SupplyHealth
  committed_quantity_kg: Decimal
  assured_coverage_quantity_kg: Decimal   // physical receiving coverage
  standby_quantity_kg: Decimal
  unfilled_quantity_kg: Decimal
  committed_farmer_count: int
  standby_farmer_count: int
  parish_concentration: { [parish: string]: Decimal }   // fraction, 0-1
  total_landed_cost_jmd: Decimal | null
  landed_cost_per_kg_jmd: Decimal | null
  allocations: AllocationRead[]
  latest_disruption: { lost_kg: string; cause: string } | null
  latest_recovery: { status: string; standby_activated_kg: string;
                     new_supply_accepted_kg: string; remaining_shortfall_kg: string } | null
  economics: { original_landed_cost_jmd: string; recovered_landed_cost_jmd: string;
               recovery_premium_jmd: string; recovery_premium_per_kg_jmd: string;
               recovery_premium_pct: string } | null
  risk: RiskSnapshot | null
}
```

### RiskSnapshot
```ts
{
  label: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
  committed_farmer_count: int
  standby_farmer_count: int
  committed_parish_count: int
  standby_parish_count: int
  largest_farmer_share_pct: Decimal
  largest_parish_share_pct: Decimal
  standby_coverage_pct: Decimal
  replacement_depth_kg: Decimal
  average_availability_confidence: Decimal
  rules_triggered: string[]
  calculation_version: string
}
```

### Farmer
```ts
{ id: UUID; name: string; parish: string; active: boolean;
  production_lot_count: int; available_quantity_kg: string; committed_quantity_kg: string }
```

### ProductionLot
```ts
{
  id, farmer_id, crop, harvest_start, harvest_end,
  expected_quantity_kg, available_quantity_kg, reserved_quantity_kg,
  quality_grade_estimate: "A"|"B",
  availability_confidence: "LOW"|"MEDIUM"|"HIGH",
  parish, status: "AVAILABLE"|"UNAVAILABLE"|"EXHAUSTED",
  last_verified_at, version
}
```

### CommandCenterSummary
```ts
{
  requirements: { total: int; by_supply_health: Record<SupplyHealth, int>; needs_attention: int }
  physical_flow_kg: { committed: string; received: string; accepted: string; rejected: string }
  committed_concentration_by_parish: { parish: string; quantity_kg: string }[]
  recent_activity: { id, event_type, aggregate_id, actor_type, occurred_at }[]
}
```

### Allocation
```ts
{
  id, requirement_id, supply_plan_id, production_lot_id,
  farmer_id, farmer_name, parish,
  role: "COMMITTED" | "STANDBY",
  status: "PROPOSED"|"SOLICITED"|"ACCEPTED"|"COMMITTED"|"STANDBY"|"ACTIVATED"|"LOST"|"RELEASED"|"CANCELLED",
  quantity_kg, plan_version
}
```

### RecoveryCase
```ts
{
  id, requirement_id,
  status: string,   // e.g. "RESOLVED", "IN_PROGRESS"
  cause: string,
  lost_quantity_kg, standby_activated_kg, new_supply_accepted_kg, remaining_shortfall_kg,
  landed_cost_delta_jmd: string | null,
  created_at, completed_at
}
```

---

## 5. Enumerations

| Enum | Values |
|---|---|
| **Crop** | `GINGER` |
| **Grade** | `A`, `B` |
| **AvailabilityConfidence** | `LOW`, `MEDIUM`, `HIGH` |
| **SupplyHealth** | `UNPLANNED`, `COVERED`, `AT_RISK`, `RECOVERING`, `ESCALATION_REQUIRED` |
| **RequirementLifecycleStatus** | `DRAFT`, `PLANNING`, `ACTIVE`, `IN_FULFILMENT`, `RECONCILED`, `CLOSED`, `CANCELLED` |
| **AllocationRole** | `COMMITTED`, `STANDBY` |
| **AllocationStatus** | `PROPOSED`, `SOLICITED`, `ACCEPTED`, `COMMITTED`, `STANDBY`, `ACTIVATED`, `LOST`, `RELEASED`, `CANCELLED` |
| **ProductionLotStatus** | `AVAILABLE`, `UNAVAILABLE`, `EXHAUSTED` |
| **ShipmentStatus** | `OPEN`, `DISPATCHED`, `DELIVERED` |
| **InspectionStatus** | (on ReceivedSublot) — used as filter |
| **ProgrammeStatus** | filter on `/programmes` |
| **RoleCode** | `PLATFORM_ADMIN`, `ORGANIZATION_ADMIN`, `PROCUREMENT_MANAGER`, `SUPPLY_COORDINATOR`, `WAREHOUSE_OPERATOR`, `AUDITOR`, `FARMER` |
| **SourceChannel** | `SECURE_LINK`, `PHONE`, `WHATSAPP`, `COORDINATOR_ENTRY`, `CSV_IMPORT` |

---

## 6. Suggested Pages & Navigation

### Shared / Auth
- **Login** — JWT auth entry point
- **Accept Invitation** — public page for token-based invite (`/invitations/accept`)
- **Secure Action** — public page for farmers (`/v1/secure-actions/:token`) — confirm quantity, harvest date, or decline

### Main App (role-gated)
```
├── Dashboard / Command Center          ← GET /command-center/summary
│   ├── KPI cards (total reqs, needs_attention, committed kg, accepted kg)
│   ├── Supply health distribution (donut chart)
│   ├── Parish concentration bar chart
│   └── Recent activity feed
│
├── Requirements
│   ├── List view (filter by health, status, buyer, programme)
│   └── Detail view
│       ├── Summary header (crop, grade, qty, buyer, window)
│       ├── Supply Health badge
│       ├── Assurance panel (committed / standby / unfilled progress bars)
│       ├── Allocations table (farmer, parish, role, status, kg)
│       ├── Parish concentration map / bar chart
│       ├── Risk panel (label badge + farmer/parish counts + share %)
│       ├── Economics panel (cost breakdown, recovery premium)
│       ├── Fulfilment panel (received / accepted / rejected kg)
│       ├── Shipments sub-list
│       ├── Compliance rules
│       └── Event timeline
│
├── Supply
│   ├── Farmers list (parish filter, active toggle)
│   └── Farmer detail → production lots → allocations
│   └── Production Lots list
│
├── Allocations                         ← GET /allocations
│   └── Filter by requirement, role, status
│
├── Fulfilment / Warehouse
│   ├── Receive sublot form
│   ├── Grade sublot form
│   └── Received sublots list (filter by inspection status)
│
├── Shipments
│   ├── List (filter by requirement)
│   ├── Create shipment
│   ├── Add sublots to shipment
│   ├── Dispatch form
│   └── Delivery confirmation form
│
├── Recovery Cases                      ← GET /recovery-cases
│   └── Detail with event log
│
├── Programmes
│   ├── List with rollup (health counts, kg)
│   └── Detail + linked requirements
│
├── Ingestion
│   ├── Secure links manager (create, view status)
│   ├── Coordinator observations form
│   └── CSV import wizard (template download → preview → confirm)
│
├── Compliance Rules                    ← GET /compliance-rules
│
├── Activity Log                        ← GET /activity
│
└── Admin
    ├── Users (list, invite, change role, deactivate)
    ├── Roles & Permissions viewer
    └── Organization info
```

---

## 7. Key UX Patterns & Business Rules

### Idempotency Keys
All write operations (`POST /plan`, `POST /recovery`, shipment lifecycle, `POST /sublots/receive`, etc.) require an `Idempotency-Key` header. The frontend must **generate and store a UUID per action intent** and re-use it on retry. Display a "Retry" button rather than re-generating on failure.

### Supply Health — Color Coding (critical for the UI)
| Status | Suggested Color |
|---|---|
| `UNPLANNED` | Neutral grey |
| `COVERED` | Green |
| `AT_RISK` | Amber / orange |
| `RECOVERING` | Blue |
| `ESCALATION_REQUIRED` | Red |

### Requirement Lifecycle — Progression
`DRAFT → PLANNING → ACTIVE → IN_FULFILMENT → RECONCILED` (terminal)  
`CLOSED` / `CANCELLED` are also terminal. Show a stepper or timeline component.

### Allocation Status Flow
```
PROPOSED → SOLICITED → ACCEPTED → COMMITTED / STANDBY
COMMITTED → ACTIVATED (when standby farmer steps in)
Any active status → LOST (dropout) / RELEASED / CANCELLED
```

### Fulfilment Flow (Warehouse Operator)
1. **Receive** → sublot created with `received_quantity_kg`
2. **Grade** → sublot updated with `accepted_quantity_kg` / `rejected_quantity_kg` / `assigned_grade`
3. Only **accepted + graded** sublots can be added to a shipment

### Shipment Lifecycle
`OPEN → DISPATCHED → DELIVERED`  
Reconciliation only possible when all deliveries are `buyer_confirmed = true` with evidence.

### Farmer Passport — Financing Eligibility Logic
- `< 3` completed trades → `BUILDING_HISTORY` → `NOT_ASSESSED`
- `≥ 3` completed trades → `ESTABLISHED_HISTORY` → show `fulfilment_reliability_index`

### Secure Action Links
- Single-use tokens, expire in 1–168 hours
- Purposes: `CONFIRM_QUANTITY`, `CHANGE_AVAILABLE_QUANTITY`, `CONFIRM_HARVEST_DATE`, `DECLINE`
- The `/v1/secure-actions/:token` page is **fully public** (no login required) — intended for WhatsApp/SMS link clicks from farmers

### CSV Bulk Import (3 entity types)
| Entity | Required CSV columns |
|---|---|
| `farmers` | `name`, `parish` |
| `production_lots` | `farmer_id`, `crop`, `harvest_start`, `harvest_end`, `expected_quantity_kg`, `available_quantity_kg`, `grade`, `availability_confidence`, `parish` |
| `buyer_requirements` | `buyer_id`, `crop`, `grade`, `required_quantity_kg`, `delivery_window_start`, `delivery_window_end` |

Flow: **download template → upload CSV → preview (row-level validation) → confirm**

---

## 8. Pagination
Most list endpoints support `offset` + `limit` (default 50, max 200). Use standard offset pagination UI.

---

## 9. Quantities & Currency
- All kg values come back as **decimal strings** (e.g. `"1500.000"`) — parse with a decimal library, never floating point.
- All costs are in **JMD (Jamaican Dollars)** — format with `J$` prefix and comma separators.
- Parish concentration values are **fractions** (0–1), multiply by 100 for percentages.

---

## 10. Trade Corridors
Requirements optionally reference a `TradeCorridor` (origin/destination country pair). The compliance module uses this to pull applicable export rules. Show corridor name when present in requirement detail.

---

## 11. Domain Events (Activity Log)
Each event has: `event_type`, `aggregate_type`, `aggregate_id`, `actor_type`, `payload`, `occurred_at`.

Key event types to display meaningfully:
- `requirement.created`
- `shipment.created`, `shipment.sublot_added`, `shipment.dispatched`
- `delivery.confirmed`
- `trade.reconciled`
- `production.observation_recorded`
- `ingestion.entity_created`
