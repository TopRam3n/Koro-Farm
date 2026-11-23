'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { apiFetch } from '@/lib/api';

export interface Buyer { id: string; name: string; buyer_type: string; destination: string; notes: string | null; active: boolean; version: number; created_at: string }
export interface Farmer { id: string; name: string; parish: string; active: boolean; production_lot_count?: number; available_quantity_kg?: string; committed_quantity_kg?: string }
export interface Crop { id: string; code: string; name: string; active: boolean; shared: boolean }
export interface Lot {
  id: string; farmer_id: string; farmer_name: string | null; crop: string; harvest_start: string; harvest_end: string;
  expected_quantity_kg: string; available_quantity_kg: string; reserved_quantity_kg: string; quality_grade_estimate: string;
  availability_confidence: string; parish: string; status: string; capacity_verification: 'DECLARED' | 'VERIFIED' | 'UNSPECIFIED';
  provenance_source: string | null; attestation_method: string | null; evidence_reference: string | null; declared_at: string | null;
  farmgate_price_per_kg_jmd: string | null; reported_capacity_kg: string | null; capacity_reported_at: string | null;
  delivered_kg: string; free_kg: string | null; version: number;
}
export interface Order {
  id: string; buyer_id: string; buyer_name: string | null; crop: string; grade: string; required_quantity_kg: string; quantity_unit: string;
  delivery_window_start: string; delivery_window_end: string; product_form: string | null; origin: string | null; destination: string | null;
  delivery_terms: string | null; currency: string | null; notes: string | null; lifecycle_status: string; supply_health: string;
  plan_version: number; version: number; cancelled_at: string | null; cancellation_reason: string | null; created_at: string; updated_at: string;
}
export interface HistoryEvent { id: string; event_type: string; actor_type: string; actor_id: string | null; payload: Record<string, unknown>; occurred_at: string }
export interface Allocation {
  id: string; production_lot_id: string; farmer_id: string; farmer_name: string; parish: string; role: 'COMMITTED' | 'STANDBY';
  status: string; quantity_kg: string; consent_status: 'RECORDED' | 'UNSUPPORTED_LEGACY' | 'NONE'; consent_id: string | null;
  holds_reservation: boolean; activation_conditions: string | null; authorization_valid_until: string | null;
  solicited_at: string | null; responded_at: string | null; response_due_at: string | null; reminder_sent_at: string | null;
  covered_kg: string | null; exposed_kg: string | null;
}
export interface OrderSupply {
  supply_health: string; committed_quantity_kg: string; standby_quantity_kg: string; unfilled_quantity_kg: string;
  proposed_quantity_kg: string; solicited_quantity_kg: string; proposed_standby_kg: string; unsupported_legacy_kg: string;
  currently_covered_kg: string; exposed_kg: string; standby_uncovered_kg: string; expired_standby_kg: string;
  open_exceptions: Array<{ id: string; kind: SupplyException['kind']; shortfall_kg: string; summary: string; opened_at: string | null; acknowledged: boolean }>;
  allocations: Allocation[];
}
export interface SupplyException {
  id: string; requirement_id: string; requirement_label: string | null; kind: 'CAPACITY_SHORTFALL' | 'RESPONSE_OVERDUE' | 'STANDBY_EXPIRED';
  status: 'OPEN' | 'RESOLVED'; shortfall_kg: string; summary: string; details: Record<string, unknown>; opened_at: string; updated_at: string;
  acknowledged_at: string | null; resolved_at: string | null; resolved_by: string | null; resolution: string | null;
}
export interface CapacityReport {
  id: string; reported_capacity_kg: string; delivered_at_report_kg: string; previous_reported_kg: string | null; committed_at_report_kg: string; effective_at: string;
  recorded_at: string; channel: 'FARMER_PORTAL' | 'COORDINATOR_RELAYED'; original_source: string | null; attestation_method: string | null;
  evidence_reference: string | null; verification_status: string; applied: boolean; recorded_by_user_id: string | null;
}

/** Supply changes arrive from the background worker, so live views poll instead of waiting for a manual refresh. */
export const LIVE_REFRESH_MS = 5_000;

/** One idempotency key per logical command; retried submissions reuse it, success clears it. */
function useCommandKey(prefix: string) {
  const key = useRef<string | null>(null);
  return { current: () => key.current ??= `${prefix}-${crypto.randomUUID()}`, clear: () => { key.current = null; } };
}

const post = <T,>(path: string, body: unknown, key?: string) =>
  apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body), headers: key ? { 'Idempotency-Key': key } : {} });
const patch = <T,>(path: string, body: unknown) => apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) });

export const useBuyers = () => useQuery({ queryKey: ['buyers'], queryFn: () => apiFetch<Buyer[]>('/buyers') });
export const useCrops = () => useQuery({ queryKey: ['crops'], queryFn: () => apiFetch<Crop[]>('/crops') });
export const useFarmers = () => useQuery({ queryKey: ['farmers'], queryFn: () => apiFetch<{ items: Farmer[] }>('/farmers?limit=200').then(r => r.items) });
export const useLots = () => useQuery({ queryKey: ['lots'], queryFn: () => apiFetch<Lot[]>('/production-lots') });
export const useOrders = () => useQuery({ queryKey: ['orders'], queryFn: () => apiFetch<Order[]>('/requirements?limit=200') });
export const useOrder = (id: string) => useQuery({ queryKey: ['order', id], queryFn: () => apiFetch<Order>(`/requirements/${id}`), enabled: Boolean(id) });
export const useOrderHistory = (id: string) => useQuery({ queryKey: ['order-history', id], queryFn: () => apiFetch<{ events: HistoryEvent[] }>(`/requirements/${id}/history`).then(r => r.events), enabled: Boolean(id), refetchInterval: LIVE_REFRESH_MS });
export const useOrderSupply = (id: string) => useQuery({ queryKey: ['order-supply', id], queryFn: () => apiFetch<OrderSupply>(`/requirements/${id}/assurance`), enabled: Boolean(id), refetchInterval: LIVE_REFRESH_MS });
export const useExceptions = (filter: { requirementId?: string; status?: 'OPEN' | 'RESOLVED'; enabled?: boolean } = {}) => useQuery({
  queryKey: ['exceptions', filter.requirementId ?? 'all', filter.status ?? 'OPEN'],
  queryFn: () => apiFetch<SupplyException[]>(`/exceptions?${new URLSearchParams({ status: filter.status ?? 'OPEN', ...(filter.requirementId ? { requirement_id: filter.requirementId } : {}) })}`),
  refetchInterval: LIVE_REFRESH_MS,
  enabled: filter.enabled ?? true,
});
export const useCapacityReports = (lotId: string | null) => useQuery({
  queryKey: ['capacity-reports', lotId], queryFn: () => apiFetch<CapacityReport[]>(`/production-lots/${lotId}/capacity-reports`), enabled: Boolean(lotId),
});

function useCreate<TBody, TResult>(prefix: string, path: string, invalidate: string[]) {
  const client = useQueryClient();
  const command = useCommandKey(prefix);
  return useMutation({
    mutationFn: (body: TBody) => post<TResult>(path, body, command.current()),
    onSuccess: async () => { command.clear(); await Promise.all(invalidate.map(key => client.invalidateQueries({ queryKey: [key] }))); },
  });
}

export const useCreateBuyer = () => useCreate<Record<string, unknown>, Buyer>('buyer', '/buyers', ['buyers']);
export const useCreateFarmer = () => useCreate<Record<string, unknown>, Farmer>('farmer', '/farmers', ['farmers']);
export const useCreateLot = () => useCreate<Record<string, unknown>, Lot>('lot', '/production-lots', ['lots', 'farmers']);
export const useCreateOrder = () => useCreate<Record<string, unknown>, Order>('order', '/requirements', ['orders']);

function useOrderCommand<TBody>(orderId: string, run: (body: TBody, key: string) => Promise<unknown>, prefix: string) {
  const client = useQueryClient();
  const command = useCommandKey(prefix);
  return useMutation({
    mutationFn: (body: TBody) => run(body, command.current()),
    onSuccess: async () => {
      command.clear();
      await Promise.all(['order', 'order-history', 'order-supply', 'orders', 'lots', 'exceptions'].map(key => client.invalidateQueries({ queryKey: ['orders', 'lots', 'exceptions'].includes(key) ? [key] : [key, orderId] })));
    },
  });
}

export const useUpdateOrder = (id: string) => useOrderCommand<Record<string, unknown>>(id, body => patch(`/requirements/${id}`, body), 'order-update');
export const useCancelOrder = (id: string) => useOrderCommand<{ reason: string }>(id, body => post(`/requirements/${id}/cancel`, body), 'order-cancel');
export const usePlanOrder = (id: string) => useOrderCommand<void>(id, (_, key) => post(`/requirements/${id}/plan`, undefined, key), 'plan');
export const useSolicit = (id: string) => useOrderCommand<{ allocationId: string; message?: string; respondWithinHours?: number }>(id, (b, key) => post(`/allocations/${b.allocationId}/solicit`, { message: b.message ?? null, respond_within_hours: b.respondWithinHours ?? null }, key), 'solicit');
export const useSetDeadline = (id: string) => useOrderCommand<{ allocationId: string; respond_by: string; reason: string }>(id, ({ allocationId, ...body }) => patch(`/allocations/${allocationId}/deadline`, body), 'deadline');
export const useWithdraw = (id: string) => useOrderCommand<{ allocationId: string; reason: string }>(id, (b, key) => post(`/allocations/${b.allocationId}/withdraw`, { reason: b.reason }, key), 'withdraw');
export const useRespond = (id: string) => useOrderCommand<{ allocationId: string } & Record<string, unknown>>(id, ({ allocationId, ...body }, key) => post(`/allocations/${allocationId}/responses`, body, key), 'respond');

function useExceptionCommand<TBody>(run: (body: TBody) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: async () => { await Promise.all(['exceptions', 'order-supply', 'order-history', 'order', 'orders'].map(key => client.invalidateQueries({ queryKey: [key] }))); },
  });
}

export const useAcknowledgeException = () => useExceptionCommand<{ exceptionId: string }>(b => post(`/exceptions/${b.exceptionId}/acknowledge`, {}));
export const useResolveException = () => useExceptionCommand<{ exceptionId: string; resolution: string }>(b => post(`/exceptions/${b.exceptionId}/resolve`, { resolution: b.resolution }));

/** Coordinator relaying a farmer's capacity: original source and attestation are required by the API. */
export function useRelayCapacity() {
  const client = useQueryClient();
  const command = useCommandKey('capacity');
  return useMutation({
    mutationFn: ({ lotId, ...body }: { lotId: string; reported_capacity_kg: string; original_source: string; attestation_method: string; evidence_reference?: string | null }) =>
      post(`/production-lots/${lotId}/capacity-reports`, body, command.current()),
    onSuccess: async () => { command.clear(); await Promise.all(['lots', 'capacity-reports', 'farmers'].map(key => client.invalidateQueries({ queryKey: [key] }))); },
  });
}
