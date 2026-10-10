// ─── Enums ────────────────────────────────────────────────────────────────────

export type Crop = 'GINGER';
export type Grade = 'A' | 'B';
export type AvailabilityConfidence = 'LOW' | 'MEDIUM' | 'HIGH';

export type SupplyHealth =
  | 'UNPLANNED'
  | 'COVERED'
  | 'AT_RISK'
  | 'RECOVERING'
  | 'ESCALATION_REQUIRED';

export type RequirementLifecycleStatus =
  | 'DRAFT'
  | 'PLANNING'
  | 'ACTIVE'
  | 'IN_FULFILMENT'
  | 'RECONCILED'
  | 'CLOSED'
  | 'CANCELLED';

export type AllocationRole = 'COMMITTED' | 'STANDBY';

export type AllocationStatus =
  | 'PROPOSED'
  | 'SOLICITED'
  | 'ACCEPTED'
  | 'COMMITTED'
  | 'STANDBY'
  | 'ACTIVATED'
  | 'LOST'
  | 'RELEASED'
  | 'CANCELLED';

export type ProductionLotStatus = 'AVAILABLE' | 'UNAVAILABLE' | 'EXHAUSTED';

export type ShipmentStatus = 'OPEN' | 'DISPATCHED' | 'DELIVERED';

export type RoleCode =
  | 'PLATFORM_ADMIN'
  | 'ORGANIZATION_ADMIN'
  | 'PROCUREMENT_MANAGER'
  | 'SUPPLY_COORDINATOR'
  | 'WAREHOUSE_OPERATOR'
  | 'AUDITOR'
  | 'FARMER';

export type RiskLabel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// Legacy UI shapes used by screens that have not yet moved to API DTOs.
export type AllocationState = 'PROPOSED' | 'SOLICITED' | 'ACCEPTED' | 'COMMITTED' | 'STANDBY' | 'STANDBY_ACTIVATED' | 'LOST' | 'RELEASED' | 'CANCELLED';
export type RequestState = 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'EXPIRED' | 'CANCELLED';
export interface RecoveryStep { label: string; detail: string; state: 'complete' | 'current' | 'pending' }
export interface SupplyMetrics { requiredKg: number; committedKg: number; standbyKg: number; shortfallKg: number; committedFarmerCount: number; standbyFarmerCount: number; health: string }
export interface Economics { currency: 'JMD'; originalCost: number; recoveredCost: number; premium: number; premiumPercent: number }
export interface Fulfilment { node: string; state: string; requiredKg: number; receivedKg: number; acceptedKg: number; rejectedKg: number }
export interface LegacyAllocation { id: string; requirementId: string; farmer: string; farmerId: string; parish: string; lotId: string; quantityKg: number; role: AllocationRole; state: AllocationState; verificationState: string }

// ─── Core models ──────────────────────────────────────────────────────────────

export interface Requirement {
  id: string;
  buyer_id: string;
  programme_id: string | null;
  trade_corridor_id: string | null;
  crop: Crop;
  grade: Grade;
  required_quantity_kg: string; // decimal string
  delivery_window_start: string; // YYYY-MM-DD
  delivery_window_end: string;
  lifecycle_status: RequirementLifecycleStatus;
  supply_health: SupplyHealth;
  plan_version: number;
  version: number;
}

export interface Allocation {
  id: string;
  requirement_id: string;
  supply_plan_id: string;
  production_lot_id: string;
  farmer_id: string;
  farmer_name: string;
  parish: string;
  role: AllocationRole;
  status: AllocationStatus;
  quantity_kg: string; // decimal string
  plan_version: number;
}

export interface RiskSnapshot {
  label: RiskLabel;
  committed_farmer_count: number;
  standby_farmer_count: number;
  committed_parish_count: number;
  standby_parish_count: number;
  largest_farmer_share_pct: string;
  largest_parish_share_pct: string;
  standby_coverage_pct: string;
  replacement_depth_kg: string;
  average_availability_confidence: string;
  rules_triggered: string[];
  calculation_version: string;
}

export interface AssuranceRead {
  requirement: {
    id: string;
    crop: Crop;
    grade: Grade;
    required_quantity_kg: string;
    lifecycle_status: RequirementLifecycleStatus;
    supply_health: SupplyHealth;
    plan_version: number;
    buyer_name: string;
    buyer_type: string;
    destination: string;
    delivery_window_start: string;
    delivery_window_end: string;
  };
  supply_health: SupplyHealth;
  committed_quantity_kg: string;
  assured_coverage_quantity_kg: string;
  standby_quantity_kg: string;
  unfilled_quantity_kg: string;
  committed_farmer_count: number;
  standby_farmer_count: number;
  parish_concentration: Record<string, string>; // fraction 0-1
  total_landed_cost_jmd: string | null;
  landed_cost_per_kg_jmd: string | null;
  allocations: Allocation[];
  latest_disruption: { lost_kg: string; cause: string } | null;
  latest_recovery: {
    status: string;
    standby_activated_kg: string;
    new_supply_accepted_kg: string;
    remaining_shortfall_kg: string;
  } | null;
  economics: {
    original_landed_cost_jmd: string;
    recovered_landed_cost_jmd: string;
    recovery_premium_jmd: string;
    recovery_premium_per_kg_jmd: string;
    recovery_premium_pct: string;
  } | null;
  risk: RiskSnapshot | null;
}

export interface Farmer {
  id: string;
  name: string;
  parish: string;
  active: boolean;
  production_lot_count: number;
  available_quantity_kg: string;
  committed_quantity_kg: string;
}

export interface ProductionLot {
  id: string;
  farmer_id: string;
  crop: Crop;
  harvest_start: string;
  harvest_end: string;
  expected_quantity_kg: string;
  available_quantity_kg: string;
  reserved_quantity_kg: string;
  quality_grade_estimate: Grade;
  availability_confidence: AvailabilityConfidence;
  parish: string;
  status: ProductionLotStatus;
  last_verified_at: string | null;
  version: number;
}

export interface CommandCenterSummary {
  requirements: {
    total: number;
    by_supply_health: Record<SupplyHealth, number>;
    needs_attention: number;
  };
  physical_flow_kg: {
    committed: string;
    received: string;
    accepted: string;
    rejected: string;
  };
  committed_concentration_by_parish: { parish: string; quantity_kg: string }[];
  recent_activity: {
    id: string;
    event_type: string;
    aggregate_id: string;
    actor_type: string;
    occurred_at: string;
  }[];
}

export interface RecoveryCase {
  id: string;
  requirement_id: string;
  status: string;
  cause: string;
  lost_quantity_kg: string;
  standby_activated_kg: string;
  new_supply_accepted_kg: string;
  remaining_shortfall_kg: string;
  landed_cost_delta_jmd: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface FulfilmentSummary {
  requirement_id: string;
  required_kg: string;
  committed_kg: string;
  received_quantity_kg: string;
  accepted_quantity_kg: string;
  rejected_quantity_kg: string;
  accepted_shortfall_kg: string;
}

export interface ReceivedSublot { id: string; requirement_id: string; production_lot_id: string; received_quantity_kg: string; accepted_quantity_kg: string | null; rejected_quantity_kg: string | null; assigned_grade: Grade | null; inspection_status: string; received_at: string; }

export interface DomainEvent {
  id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  actor_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface Programme {
  id: string;
  buyer_id: string;
  name: string;
  commodity_scope?: string | null;
  start_date: string;
  end_date: string;
  status: string;
  created_at?: string;
  requirement_count?: number;
}

export interface ProgrammeSummary {
  programme: Programme;
  requirement_count: number;
  active_requirements: number;
  required_quantity_kg: string;
  committed_quantity_kg: string;
  standby_quantity_kg: string;
  requirements_by_supply_health: Record<SupplyHealth, number>;
}

export interface Shipment {
  id: string;
  requirement_id: string;
  reference?: string;
  status: ShipmentStatus;
  dispatched_at: string | null;
  dispatch_evidence_reference?: string | null;
  delivered_at?: string | null;
  buyer_confirmed?: boolean;
}

export interface MeResponse {
  id: string;
  email: string;
  name: string | null;
  active_organization_id: string;
  active_role: RoleCode;
  organizations: { id: string; name: string; role: RoleCode }[];
  // Normalized aliases populated by the frontend hook for existing consumers.
  user_id: string;
  organization_id: string;
  role: RoleCode;
  farmer_id: string | null;
  display_name: string | null;
}

// ─── Pagination wrapper ───────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

// ─── Formatting helpers ───────────────────────────────────────────────────────

/** Format a JMD decimal string as J$1,234,567 */
export function formatJmd(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '—';
  return new Intl.NumberFormat('en-JM', { style: 'currency', currency: 'JMD', currencyDisplay: 'narrowSymbol', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(num);
}

/** Format a kg decimal string with 3dp */
export function formatKg(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '—';
  return `${num.toLocaleString('en-JM', { minimumFractionDigits: 0, maximumFractionDigits: 1 })} kg`;
}

/** Fraction (0-1) → percentage string */
export function formatPct(fraction: string | number | null | undefined): string {
  if (fraction === null || fraction === undefined) return '—';
  const num = typeof fraction === 'string' ? parseFloat(fraction) : fraction;
  if (isNaN(num)) return '—';
  return `${(num * 100).toFixed(1)}%`;
}

// ─── Supply health color tokens ────────────────────────────────────────────────

export const supplyHealthColor: Record<SupplyHealth, string> = {
  UNPLANNED: 'text-muted-foreground',
  COVERED: 'text-emerald-600 dark:text-emerald-400',
  AT_RISK: 'text-amber-600 dark:text-amber-400',
  RECOVERING: 'text-blue-600 dark:text-blue-400',
  ESCALATION_REQUIRED: 'text-destructive',
};

export const supplyHealthBg: Record<SupplyHealth, string> = {
  UNPLANNED: 'bg-muted text-muted-foreground',
  COVERED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  AT_RISK: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  RECOVERING: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  ESCALATION_REQUIRED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

export const riskLabelBg: Record<RiskLabel, string> = {
  LOW: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  MEDIUM: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  HIGH: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  CRITICAL: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

// ─── Role-based access helpers ────────────────────────────────────────────────

export const WRITE_ROLES: RoleCode[] = [
  'PLATFORM_ADMIN',
  'ORGANIZATION_ADMIN',
  'PROCUREMENT_MANAGER',
  'SUPPLY_COORDINATOR',
  'WAREHOUSE_OPERATOR',
];

export const ADMIN_ROLES: RoleCode[] = ['PLATFORM_ADMIN', 'ORGANIZATION_ADMIN'];

export function canWrite(role: RoleCode | undefined): boolean {
  return !!role && WRITE_ROLES.includes(role);
}
export function isAdmin(role: RoleCode | undefined): boolean {
  return !!role && ADMIN_ROLES.includes(role);
}
