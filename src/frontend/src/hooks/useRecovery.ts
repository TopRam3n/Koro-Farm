'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { LIVE_REFRESH_MS } from '@/hooks/useTrade';

export type ActionType = 'ACTIVATE_STANDBY' | 'SOLICIT_SUPPLY' | 'RELEASE_EXPOSED';

export interface ProposalAction {
  type: ActionType; farmer_name: string; supplier_label: string; parish: string; quantity_kg: string; production_lot_id: string;
  allocation_id?: string; consent_channel?: string | null; activation_conditions?: string | null; authorization_valid_until?: string | null;
  respond_within_hours?: number; availability_confidence?: string; message?: string | null; reason?: string;
}

export interface ProposalCost {
  known: boolean; replacement_kg: string; total_landed_cost_jmd: string | null; baseline_cost_per_kg_jmd: string | null;
  increase_jmd: string | null; increase_pct: string | null; unknown_cost_lots: string[];
}

export interface ProposalOption {
  id: string; title: string; actions: ProposalAction[]; standby_activated_kg: string; requested_kg: string; escalation_kg: string; cost: ProposalCost;
}

export interface ProposalContent {
  version: number; created_at: string; expires_at: string;
  basis: { required_kg: string; committed_cover_kg: string; exposed_kg: string; assured_kg: string; gap_kg: string; in_flight_kg: string; net_need_kg: string };
  incidents: Array<{ kind: string; quantity_kg: string; note: string | null }>;
  options: ProposalOption[]; chosen_option_id: string; actions: ProposalAction[]; escalation_kg: string; cost: ProposalCost;
  approval: { tier: 'ORDINARY' | 'ELEVATED'; reasons: string[]; required: string; policy: { version: number } };
  decision: { mode: 'deterministic' | 'model'; model: string | null; rationale: string; recommend_escalation: boolean;
    information_requests: string[]; violations: string[]; fallback_reason: string | null };
  drafts: { buyer: string; status: string };
}

export interface Proposal {
  id: string; version: number; status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED' | 'STALE' | 'EXECUTED' | 'PARTIAL';
  tier: 'ORDINARY' | 'ELEVATED'; content_hash: string; content: ProposalContent; expires_at: string; created_at: string;
  decided_at: string | null; status_reason: string | null;
  approvals: Array<{ reviewer_user_id: string; reviewer_name: string | null; reviewer_role: string; decision: 'APPROVED' | 'REJECTED'; elevated: boolean; note: string | null; decided_at: string }>;
  executions: Array<{ action_index: number; action_type: ActionType; outcome: 'APPLIED' | 'FAILED'; detail: Record<string, unknown>; executed_at: string }>;
  viewer: { can_approve: boolean; elevated: boolean; already_decided: boolean };
}

export interface RecoveryStep { sequence: number; kind: string; actor: string; actor_name: string; summary: string; detail: Record<string, unknown>; proposal_id: string | null; created_at: string }

export interface RecoveryTask {
  id: string; requirement_id: string; requirement_label: string | null;
  status: 'QUEUED' | 'AWAITING_APPROVAL' | 'EXECUTING' | 'AWAITING_SUPPLIER' | 'ESCALATED' | 'COMPLETED' | 'CANCELLED' | 'FAILED';
  escalated_kg: string; terminal_reason: string | null; last_error: string | null; created_at: string; updated_at: string; closed_at: string | null;
  current_proposal: Proposal | null;
  incidents?: Array<{ kind: string; quantity_kg: string; summary: string; recorded_at: string }>;
  steps?: RecoveryStep[]; proposals?: Proposal[];
}

/** Active recovery tasks for the organization, or every task (with its timeline) for one order. */
export const useRecoveryTasks = (filter: { requirementId?: string; enabled?: boolean } = {}) => useQuery({
  queryKey: ['recovery-tasks', filter.requirementId ?? 'active'],
  queryFn: () => apiFetch<RecoveryTask[]>(`/recovery-tasks?${new URLSearchParams(filter.requirementId ? { state: 'all', requirement_id: filter.requirementId } : { state: 'active' })}`),
  refetchInterval: LIVE_REFRESH_MS,
  enabled: filter.enabled ?? true,
});

function useRecoveryCommand<TBody>(run: (body: TBody) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: async () => { await Promise.all(['recovery-tasks', 'exceptions', 'order-supply', 'order-history'].map(key => client.invalidateQueries({ queryKey: [key] }))); },
  });
}

const post = (path: string, body: unknown) => apiFetch(path, { method: 'POST', body: JSON.stringify(body) });

/** Approving sends the hash of the proposal that was on screen; a proposal that changed since is refused. */
export const useApproveProposal = () => useRecoveryCommand<{ proposal: Proposal; note?: string }>(
  ({ proposal, note }) => post(`/recovery-proposals/${proposal.id}/approve`, { proposal_hash: proposal.content_hash, note: note || null }));
export const useRejectProposal = () => useRecoveryCommand<{ proposal: Proposal; reason: string }>(
  ({ proposal, reason }) => post(`/recovery-proposals/${proposal.id}/reject`, { proposal_hash: proposal.content_hash, reason }));
export const useRequestRecovery = () => useRecoveryCommand<{ requirementId: string; note?: string }>(
  ({ requirementId, note }) => post(`/requirements/${requirementId}/recovery`, { note: note || null }));

export const taskStatusLabel: Record<RecoveryTask['status'], string> = {
  QUEUED: 'Planning', AWAITING_APPROVAL: 'Awaiting approval', EXECUTING: 'Approved, applying', AWAITING_SUPPLIER: 'Waiting for suppliers',
  ESCALATED: 'Escalated to a coordinator', COMPLETED: 'Completed', CANCELLED: 'Cancelled', FAILED: 'Failed',
};
