'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { apiFetch } from '@/lib/api';
import { LIVE_REFRESH_MS } from '@/hooks/useTrade';

/** Quantities kept apart on purpose (R1 WP4): received is not accepted, delivered is not confirmed. */
export interface FulfilmentFigures {
  required_kg: string; committed_kg: string; received_kg: string; accepted_kg: string; rejected_kg: string; ungraded_receipts: number;
  dispatched_kg: string; delivered_kg: string; buyer_confirmed_kg: string; legacy_unquantified_confirmation_kg: string;
  unconfirmed_deliveries: number; deliveries_with_discrepancy: number; open_disputes: number; disputed_kg: string; released_kg: string;
  unreviewed_sequence_flags?: number;
}
/** A physical event sequence that cannot have happened as recorded. Flagged for review; the records are never rewritten. */
export interface SequenceFlag {
  key: string; kind: 'DELIVERED_BEFORE_DISPATCH' | 'DISPATCHED_BEFORE_RECEIPT' | 'DELIVERED_BEFORE_RECEIPT'; message: string;
  shipment_id?: string; delivery_id?: string; reviewed: boolean; review_note: string | null; reviewed_by_user_id: string | null;
}
export interface Confirmation {
  id: string; confirmed_quantity_kg: string; outcome: 'CONFIRMED' | 'DISCREPANCY'; channel: 'BUYER_ACCOUNT' | 'STAFF_RELAYED' | 'LEGACY_UNQUANTIFIED';
  buyer_representative: string | null; communication_channel: string | null; attestation: string | null; stated_at: string | null; note: string | null; created_at: string;
}
export interface DeliveryView {
  id: string; shipment_id: string; recorded_quantity_kg: string; delivered_quantity_kg: string; delivered_at: string; evidence_reference: string | null;
  adjustments: Array<{ delta_kg: string; reason: string; created_at: string }>; confirmation: Confirmation | null; confirmation_history: number;
}
export interface Receipt {
  id: string; allocation_id: string; farmer_name: string; fulfilment_node_id: string; received_kg: string; accepted_kg: string; rejected_kg: string;
  graded: boolean; assigned_grade: string | null; rejection_reason: string | null; received_at: string; corrections: number; shipment_id: string | null;
}
export interface Shipment {
  id: string; reference: string; status: 'OPEN' | 'DISPATCHED' | 'DELIVERED' | 'CANCELLED'; dispatched_at: string | null;
  dispatch_time_basis?: 'STATED' | 'RECORDED' | 'LEGACY' | null; dispatch_recorded_at?: string | null;
  cancellation_reason: string | null; delivery: DeliveryView | null;
}
export interface Dispute {
  id: string; delivery_id: string | null; party: 'BUYER' | 'STAFF'; quantity_kg: string | null; description: string; created_at: string;
  status: 'OPEN' | 'RESOLVED' | 'WITHDRAWN'; resolution: string | null;
}
export interface Reconciliation {
  id: string; version: number; status: 'EFFECTIVE' | 'PENDING_REVIEW' | 'REJECTED' | 'SUPERSEDED'; figures: FulfilmentFigures;
  variances: Record<string, string>; reason: string | null; material_change: boolean; legacy: boolean;
  created_by_user_id: string | null; reviewed_by_user_id: string | null; created_at: string;
}
export interface FulfilmentRecord {
  requirement_id: string; lifecycle_status: string; figures: FulfilmentFigures; variances: Record<string, string>;
  completion: { can_complete: boolean; blockers: string[] };
  receivable_allocations: Array<{ allocation_id: string; farmer_name: string; parish: string; obligation_kg: string }>;
  receipts: Receipt[]; shipments: Shipment[]; disputes: Dispute[]; reconciliations: Reconciliation[];
  effective_reconciliation_version: number | null; unconfirmed_deliveries: string[]; sequence_flags?: SequenceFlag[];
}
export interface FulfilmentSite { id: string; name: string; node_type: string; parish: string; active: boolean; created_at: string }
export interface BuyerDelivery extends DeliveryView { order: string; requirement_id: string; shipment_reference: string }

/** One item in a Fulfilment Center queue (R1 WP5, M1); which fields are present depends on the queue. */
export interface OverviewItem {
  requirement_id: string; order: string; supplier?: string; received_kg?: string; received_at?: string; reference?: string;
  dispatched_at?: string | null; delivered_kg?: string; delivered_at?: string; message?: string; party?: string; description?: string;
  quantity_kg?: string | null; version?: number; reason?: string | null; can_complete?: boolean; blockers?: string[];
}
export interface OverviewQueue { items: OverviewItem[]; count: number; action_permission: string }
export interface FulfilmentOverviewData { generated_at: string; day_start: string; open_orders: number; queues: Record<string, OverviewQueue> }

/** The buyer portal's view of one of their orders (R1 WP5, M2). Own confirmations and staff relays are kept apart. */
export interface BuyerQuantities {
  required_kg: string; delivered_kg: string; confirmed_by_you_kg: string; relayed_by_staff_kg: string; disputed_kg: string;
  awaiting_your_confirmation_kg: string; still_to_deliver_kg: string;
}
export interface BuyerOrder {
  requirement_id: string; crop: string; grade: string; delivery_window_start: string; delivery_window_end: string; destination: string;
  status: string; status_label: string; quantities: BuyerQuantities;
}
export interface BuyerStatement {
  id: string; confirmed_quantity_kg: string; outcome: 'CONFIRMED' | 'DISCREPANCY'; source: 'BUYER_ACCOUNT' | 'STAFF_RELAYED' | 'LEGACY_UNQUANTIFIED';
  source_label: string; note: string | null; created_at: string; buyer_representative?: string | null; communication_channel?: string | null; stated_at?: string | null;
}
export interface BuyerOrderDelivery {
  id: string; shipment_reference: string; delivered_at: string; delivered_quantity_kg: string; recorded_quantity_kg: string;
  corrections: Array<{ delta_kg: string; reason: string; created_at: string }>; current_statement: BuyerStatement | null; statement_history: BuyerStatement[];
}
export interface BuyerDispute {
  id: string; delivery_id: string | null; raised_by: string; quantity_kg: string | null; description: string; created_at: string;
  status: 'OPEN' | 'RESOLVED' | 'WITHDRAWN'; resolution: string | null; resolved_at: string | null;
}
export interface BuyerOrderDetail extends BuyerOrder { deliveries: BuyerOrderDelivery[]; disputes: BuyerDispute[] }

function useCommandKey(prefix: string) {
  const key = useRef<string | null>(null);
  return { current: () => key.current ??= `${prefix}-${crypto.randomUUID()}`, clear: () => { key.current = null; } };
}

const post = <T,>(path: string, body: unknown, key?: string) =>
  apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body), headers: key ? { 'Idempotency-Key': key } : {} });

export const useFulfilmentRecord = (orderId: string) => useQuery({
  queryKey: ['fulfilment', orderId], queryFn: () => apiFetch<FulfilmentRecord>(`/requirements/${orderId}/fulfilment-record`),
  enabled: Boolean(orderId), refetchInterval: LIVE_REFRESH_MS,
});
export const useFulfilmentSites = (includeInactive = false) => useQuery({
  queryKey: ['fulfilment-sites', includeInactive], queryFn: () => apiFetch<FulfilmentSite[]>(`/fulfilment-nodes${includeInactive ? '?include_inactive=true' : ''}`),
});
export const useFulfilmentOverview = () => useQuery({
  queryKey: ['fulfilment-overview'], queryFn: () => apiFetch<FulfilmentOverviewData>('/fulfilment-overview'), refetchInterval: LIVE_REFRESH_MS,
});
export const useBuyerOrders = () => useQuery({ queryKey: ['buyer-orders'], queryFn: () => apiFetch<BuyerOrder[]>('/buyer/orders'), refetchInterval: LIVE_REFRESH_MS });
export const useBuyerOrder = (id: string | null) => useQuery({
  queryKey: ['buyer-order', id], queryFn: () => apiFetch<BuyerOrderDetail>(`/buyer/orders/${id}`), enabled: Boolean(id), refetchInterval: LIVE_REFRESH_MS,
});
export const useBuyerDeliveries = () => useQuery({ queryKey: ['buyer-deliveries'], queryFn: () => apiFetch<BuyerDelivery[]>('/buyer/deliveries'), refetchInterval: LIVE_REFRESH_MS });

/** One mutation per command. Keyed commands reuse their idempotency key on retry and clear it on success. */
function useCommand<TBody>(run: (body: TBody, key: string) => Promise<unknown>, prefix: string, invalidate: unknown[][]) {
  const client = useQueryClient();
  const command = useCommandKey(prefix);
  return useMutation({
    mutationFn: (body: TBody) => run(body, command.current()),
    onSuccess: async () => { command.clear(); await Promise.all(invalidate.map(queryKey => client.invalidateQueries({ queryKey }))); },
  });
}

const orderKeys = (orderId: string) => [['fulfilment', orderId], ['order', orderId], ['order-supply', orderId], ['order-history', orderId], ['orders'], ['lots']];

export function useFulfilmentCommands(orderId: string) {
  const keys = orderKeys(orderId);
  return {
    receive: useCommand<Record<string, string>>((b, key) => post('/sublots/receive', b, key), 'receive', keys),
    grade: useCommand<{ sublotId: string } & Record<string, string>>(({ sublotId, ...b }, key) => post(`/sublots/${sublotId}/grade`, b, key), 'grade', keys),
    createShipment: useCommand<{ fulfilment_node_id: string; reference: string }>((b, key) => post(`/requirements/${orderId}/shipments`, b, key), 'shipment', keys),
    addToShipment: useCommand<{ shipmentId: string; received_sublot_id: string }>(({ shipmentId, ...b }, key) => post(`/shipments/${shipmentId}/sublots`, b, key), 'ship-add', keys),
    cancelShipment: useCommand<{ shipmentId: string; reason: string }>(({ shipmentId, ...b }) => post(`/shipments/${shipmentId}/cancel`, b), 'ship-cancel', keys),
    reviewSequence: useCommand<{ finding_key: string; note: string }>(b => post(`/requirements/${orderId}/sequence-reviews`, b), 'sequence-review', keys),
    dispatch: useCommand<{ shipmentId: string; evidence_reference?: string; dispatched_at?: string }>(({ shipmentId, ...b }, key) => post(`/shipments/${shipmentId}/dispatch`, b, key), 'dispatch', keys),
    deliver: useCommand<{ shipmentId: string } & Record<string, string>>(({ shipmentId, ...b }, key) => post(`/shipments/${shipmentId}/delivery`, b, key), 'deliver', keys),
    relayConfirmation: useCommand<{ deliveryId: string } & Record<string, string | boolean>>(({ deliveryId, ...b }, key) => post(`/deliveries/${deliveryId}/confirmations`, b, key), 'relay', keys),
    raiseDispute: useCommand<Record<string, string>>(b => post(`/requirements/${orderId}/disputes`, b), 'dispute', keys),
    resolveDispute: useCommand<{ disputeId: string; outcome: 'RESOLVED' | 'WITHDRAWN'; resolution: string }>(({ disputeId, ...b }) => post(`/disputes/${disputeId}/resolution`, b), 'resolve', keys),
    reconcile: useCommand<{ reason?: string; verification_evidence_reference?: string }>((b, key) => post(`/requirements/${orderId}/reconcile`, b, key), 'reconcile', keys),
    review: useCommand<{ reconciliationId: string; approve: boolean; note: string }>(({ reconciliationId, ...b }) => post(`/reconciliations/${reconciliationId}/review`, b), 'review', keys),
    close: useCommand<{ accept_variance: boolean; reason?: string }>((b, key) => post(`/requirements/${orderId}/close`, b, key), 'close', keys),
    flag: useCommand<{ subject: string; note: string }>(b => post('/audit-flags', { ...b, requirement_id: orderId }), 'audit-flag', [['order-history', orderId]]),
    requestCancellation: useCommand<{ reason: string; buyer_instruction: string; commercial_consequences?: string }>(
      b => post(`/requirements/${orderId}/cancellation-requests`, b), 'cancel-request', [...keys, ['recovery-tasks', orderId]]),
  };
}

export function useSiteCommands() {
  const keys = [['fulfilment-sites']];
  return {
    create: useCommand<{ name: string; node_type: string; parish: string }>(b => post('/fulfilment-nodes', b), 'site', keys),
    deactivate: useCommand<{ siteId: string }>(({ siteId }) => post(`/fulfilment-nodes/${siteId}/deactivate`, {}), 'site-off', keys),
  };
}

export function useBuyerCommands() {
  const keys = [['buyer-deliveries'], ['buyer-orders'], ['buyer-order']];
  return {
    confirm: useCommand<{ deliveryId: string; confirmed_quantity_kg: string; discrepancy: boolean; note?: string }>(
      ({ deliveryId, ...b }, key) => post(`/buyer/deliveries/${deliveryId}/confirmation`, b, key), 'buyer-confirm', keys),
    dispute: useCommand<{ deliveryId: string; description: string; quantity_kg?: string }>(
      ({ deliveryId, ...b }) => post(`/buyer/deliveries/${deliveryId}/disputes`, b), 'buyer-dispute', keys),
  };
}
