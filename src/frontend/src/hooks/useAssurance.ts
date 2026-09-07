'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { apiFetch } from '@/lib/api';

export interface AssuranceResponse {
  requirement: { id: string; crop: string; grade: string; required_quantity_kg: string; lifecycle_status: string; supply_health: string; plan_version: number; buyer_name: string; buyer_type: string; destination: string; delivery_window_start: string; delivery_window_end: string };
  supply_health: string;
  committed_quantity_kg: string;
  assured_coverage_quantity_kg: string;
  standby_quantity_kg: string;
  unfilled_quantity_kg: string;
  committed_farmer_count: number;
  standby_farmer_count: number;
  total_landed_cost_jmd: string | null;
  allocations: Array<{ id: string; production_lot_id: string; farmer_id: string; farmer_name: string; parish: string; role: 'COMMITTED' | 'STANDBY'; status: string; quantity_kg: string }>;
  latest_recovery: Record<string, string> | null;
  latest_disruption: Record<string, string> | null;
  economics: Record<string, string> | null;
  risk: { label: 'LOW' | 'MEDIUM' | 'HIGH'; rules_triggered: string[]; calculation_version: string } | null;
}

export interface FulfilmentSummary { required_kg: string; committed_kg: string; received_kg: string; accepted_kg: string; rejected_kg: string; accepted_shortfall_kg: string }
export interface DomainEvent { id: string; event_type: string; actor_type: string; payload: Record<string, string>; occurred_at: string }

export function useAssurance(requirementId: string) {
  return useQuery({
    queryKey: ['assurance', requirementId],
    queryFn: () => apiFetch<AssuranceResponse>(`/requirements/${requirementId}/assurance`),
    enabled: Boolean(requirementId),
  });
}

export function useFulfilment(requirementId: string) {
  return useQuery({
    queryKey: ['fulfilment', requirementId],
    queryFn: () => apiFetch<FulfilmentSummary>(`/requirements/${requirementId}/fulfilment`),
    enabled: Boolean(requirementId),
  });
}

export function useEvents(requirementId: string) {
  return useQuery({ queryKey: ['events', requirementId], queryFn: () => apiFetch<DomainEvent[]>(`/requirements/${requirementId}/events`), enabled: Boolean(requirementId) });
}

function useCommandKey(prefix: string) {
  const key = useRef<string | null>(null);
  return { current: () => key.current ??= `${prefix}-${crypto.randomUUID()}`, clear: () => { key.current = null; } };
}

export function useCreatePlan(requirementId: string) {
  const queryClient = useQueryClient();
  const command = useCommandKey('plan');
  return useMutation({ mutationFn: () => apiFetch(`/requirements/${requirementId}/plan`, { method: 'POST', headers: { 'Idempotency-Key': command.current() } }), onSuccess: async () => { command.clear(); await queryClient.invalidateQueries({ queryKey: ['assurance', requirementId] }); } });
}

export function useRunRecovery(requirementId: string) {
  const queryClient = useQueryClient();
  const command = useCommandKey('recovery');
  return useMutation({
    mutationFn: () => apiFetch(`/requirements/${requirementId}/recovery`, { method: 'POST', headers: { 'Idempotency-Key': command.current() } }),
    onSuccess: async () => { command.clear(); await queryClient.invalidateQueries({ queryKey: ['assurance', requirementId] }); await queryClient.invalidateQueries({ queryKey: ['events', requirementId] }); },
  });
}

export function useDropout(requirementId: string) {
  const queryClient = useQueryClient();
  const command = useCommandKey('dropout');
  return useMutation({
    mutationFn: ({ allocationId, reason }: { allocationId: string; reason: string }) => apiFetch(`/allocations/${allocationId}/dropout`, {
      method: 'POST', headers: { 'Idempotency-Key': command.current() }, body: JSON.stringify({ reason, defer_recovery: true }),
    }),
    onSuccess: async () => { command.clear(); await queryClient.invalidateQueries({ queryKey: ['assurance', requirementId] }); await queryClient.invalidateQueries({ queryKey: ['events', requirementId] }); },
  });
}

export function useAcceptAllocation(requirementId: string) {
  const queryClient = useQueryClient();
  const command = useCommandKey('accept');
  return useMutation({
    mutationFn: (allocationId: string) => apiFetch(`/allocations/${allocationId}/accept`, {
      method: 'POST', headers: { 'Idempotency-Key': command.current() },
    }),
    onSuccess: async () => { command.clear(); await queryClient.invalidateQueries({ queryKey: ['assurance', requirementId] }); await queryClient.invalidateQueries({ queryKey: ['events', requirementId] }); },
  });
}
