'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export interface AssuranceResponse {
  requirement: { id: string; required_quantity_kg: string; lifecycle_status: string; supply_health: string; plan_version: number };
  supply_health: string;
  committed_quantity_kg: string;
  standby_quantity_kg: string;
  unfilled_quantity_kg: string;
  committed_farmer_count: number;
  standby_farmer_count: number;
  total_landed_cost_jmd: string | null;
  allocations: Array<{ id: string; production_lot_id: string; farmer_id: string; farmer_name: string; parish: string; role: 'COMMITTED' | 'STANDBY'; status: string; quantity_kg: string }>;
  latest_recovery: Record<string, string> | null;
  economics: Record<string, string> | null;
}

export interface FulfilmentSummary { required_kg: string; received_kg: string; accepted_kg: string; rejected_kg: string }

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

export function useCreatePlan(requirementId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: () => apiFetch(`/requirements/${requirementId}/plan`, { method: 'POST' }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assurance', requirementId] }) });
}

export function useRunRecovery(requirementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/requirements/${requirementId}/recovery`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assurance', requirementId] }),
  });
}