'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, apiBlob, getOrCreateIdempotencyKey, clearIdempotencyKey } from '@/lib/api/client';
import type {
  AssuranceRead,
  CommandCenterSummary,
  DomainEvent,
  Farmer,
  FulfilmentSummary,
  MeResponse,
  PaginatedResponse,
  ProductionLot,
  Programme,
  ProgrammeSummary,
  RecoveryCase,
  Requirement,
  Allocation,
  Shipment,
  ReceivedSublot,
} from '@/domain/types';

// ─── Query keys ───────────────────────────────────────────────────────────────

export const qk = {
  me: ['me'] as const,
  commandCenter: ['command-center'] as const,
  requirements: (filters?: object) => ['requirements', filters] as const,
  requirement: (id: string) => ['requirements', id] as const,
  assurance: (id: string) => ['assurance', id] as const,
  risk: (id: string) => ['risk', id] as const,
  events: (id: string) => ['events', id] as const,
  fulfilment: (id: string) => ['fulfilment', id] as const,
  compliance: (id: string) => ['compliance', id] as const,
  farmers: (filters?: object) => ['farmers', filters] as const,
  allocations: (filters?: object) => ['allocations', filters] as const,
  productionLots: (filters?: object) => ['production-lots', filters] as const,
  productionLot: (id: string) => ['production-lots', id] as const,
  recoveryCases: ['recovery-cases'] as const,
  recoveryCase: (id: string) => ['recovery-cases', id] as const,
  shipments: (filters?: object) => ['shipments', filters] as const,
  programmes: (filters?: object) => ['programmes', filters] as const,
  programme: (id: string) => ['programmes', id] as const,
  activity: ['activity'] as const,
  complianceRules: ['compliance-rules'] as const,
  farmerPassport: (id: string) => ['farmer-passport', id] as const,
};

// ─── Identity ─────────────────────────────────────────────────────────────────

export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async () => {
      const raw = await api.get<Omit<MeResponse, 'user_id' | 'organization_id' | 'role' | 'farmer_id' | 'display_name'>>('/me');
      return {
        ...raw,
        user_id: raw.id,
        organization_id: raw.active_organization_id,
        role: raw.active_role,
        farmer_id: null,
        display_name: raw.name,
      } satisfies MeResponse;
    },
    staleTime: 5 * 60_000,
  });
}

// ─── Command Center ───────────────────────────────────────────────────────────

export function useCommandCenter() {
  return useQuery({
    queryKey: qk.commandCenter,
    queryFn: () => api.get<CommandCenterSummary>('/command-center/summary'),
    refetchInterval: 30_000,
  });
}

// ─── Requirements ─────────────────────────────────────────────────────────────

interface RequirementsFilters {
  supply_health?: string;
  lifecycle_status?: string;
  buyer_id?: string;
  programme_id?: string;
  offset?: number;
  limit?: number;
}

export function useRequirements(filters: RequirementsFilters = {}) {
  return useQuery({
    queryKey: qk.requirements(filters),
    queryFn: async () => {
      const items = await api.get<Requirement[]>('/requirements', {
        ...filters,
        limit: filters.limit ?? 50,
      });
      return { items, total: items.length, offset: filters.offset ?? 0, limit: filters.limit ?? 50 } satisfies PaginatedResponse<Requirement>;
    },
  });
}

export function useRequirement(id: string) {
  return useQuery({
    queryKey: qk.requirement(id),
    queryFn: () => api.get<Requirement>(`/requirements/${id}`),
    enabled: !!id,
  });
}

export function useAssurance(id: string) {
  return useQuery({
    queryKey: qk.assurance(id),
    queryFn: () => api.get<AssuranceRead>(`/requirements/${id}/assurance`),
    enabled: !!id,
    refetchInterval: 15_000,
  });
}

export function useRisk(id: string) {
  return useQuery({
    queryKey: qk.risk(id),
    queryFn: () => api.get<import('@/domain/types').RiskSnapshot>(`/requirements/${id}/risk`),
    enabled: !!id,
  });
}

export function useRequirementEvents(id: string) {
  return useQuery({
    queryKey: qk.events(id),
    queryFn: () => api.get<DomainEvent[]>(`/requirements/${id}/events`),
    enabled: !!id,
  });
}

export function useFulfilment(id: string) {
  return useQuery({
    queryKey: qk.fulfilment(id),
    queryFn: async () => {
      const raw = await api.get<{ required_kg: string; committed_kg: string; received_kg: string; accepted_kg: string; rejected_kg: string; accepted_shortfall_kg: string }>(`/requirements/${id}/fulfilment`);
      return {
        requirement_id: id,
        ...raw,
        received_quantity_kg: raw.received_kg,
        accepted_quantity_kg: raw.accepted_kg,
        rejected_quantity_kg: raw.rejected_kg,
      } satisfies FulfilmentSummary;
    },
    enabled: !!id,
  });
}

export function useRequirementCompliance(id: string) {
  return useQuery({
    queryKey: qk.compliance(id),
    queryFn: () => api.get<unknown[]>(`/requirements/${id}/compliance`),
    enabled: !!id,
  });
}

// ─── Mutations: Requirements ──────────────────────────────────────────────────

interface CreateRequirementPayload {
  buyer_id: string;
  crop: string;
  grade: string;
  required_quantity_kg: number;
  delivery_window_start: string;
  delivery_window_end: string;
  programme_id?: string;
  trade_corridor_id?: string;
}

export function useCreateRequirement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateRequirementPayload) => {
      const intent = `requirement:create:${payload.buyer_id}:${payload.crop}:${payload.grade}:${payload.delivery_window_start}:${payload.delivery_window_end}`;
      return api.post<Requirement>('/requirements', payload, getOrCreateIdempotencyKey(intent));
    },
    onSuccess: (_data, payload) => {
      clearIdempotencyKey(`requirement:create:${payload.buyer_id}:${payload.crop}:${payload.grade}:${payload.delivery_window_start}:${payload.delivery_window_end}`);
      void qc.invalidateQueries({ queryKey: ['requirements'] });
    },
  });
}

export function useGeneratePlan(requirementId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => {
      const key = getOrCreateIdempotencyKey(`plan:${requirementId}`);
      return api.post<unknown>(`/requirements/${requirementId}/plan`, undefined, key);
    },
    onSuccess: () => {
      clearIdempotencyKey(`plan:${requirementId}`);
      void qc.invalidateQueries({ queryKey: qk.assurance(requirementId) });
      void qc.invalidateQueries({ queryKey: qk.requirement(requirementId) });
    },
  });
}

export function useAdvanceRecovery(requirementId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => {
      const key = getOrCreateIdempotencyKey(`recovery:${requirementId}`);
      return api.post<unknown>(`/requirements/${requirementId}/recovery`, payload, key);
    },
    onSuccess: () => {
      clearIdempotencyKey(`recovery:${requirementId}`);
      void qc.invalidateQueries({ queryKey: qk.assurance(requirementId) });
      void qc.invalidateQueries({ queryKey: ['recovery-cases'] });
    },
  });
}

export function useBuyerChange(requirementId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { new_quantity_kg: number; reason: string }) => {
      const key = getOrCreateIdempotencyKey(`buyer-change:${requirementId}`);
      return api.post<unknown>(`/requirements/${requirementId}/buyer-change`, payload, key);
    },
    onSuccess: () => {
      clearIdempotencyKey(`buyer-change:${requirementId}`);
      void qc.invalidateQueries({ queryKey: qk.requirement(requirementId) });
      void qc.invalidateQueries({ queryKey: qk.assurance(requirementId) });
    },
  });
}

// ─── Allocations ──────────────────────────────────────────────────────────────

interface AllocationsFilters {
  requirement_id?: string;
  role?: string;
  status?: string;
  offset?: number;
  limit?: number;
}

export function useAllocations(filters: AllocationsFilters = {}) {
  return useQuery({
    queryKey: qk.allocations(filters),
    queryFn: () => api.get<PaginatedResponse<Allocation>>('/allocations', { ...filters }),
  });
}

export function useAcceptAllocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      const key = getOrCreateIdempotencyKey(`accept:${id}`);
      return api.post<unknown>(`/allocations/${id}/accept`, undefined, key);
    },
    onSuccess: (_data, id) => {
      clearIdempotencyKey(`accept:${id}`);
      void qc.invalidateQueries({ queryKey: ['allocations'] });
    },
  });
}

export function useDeclineAllocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      const key = getOrCreateIdempotencyKey(`decline:${id}`);
      return api.post<unknown>(`/allocations/${id}/decline`, undefined, key);
    },
    onSuccess: (_data, id) => {
      clearIdempotencyKey(`decline:${id}`);
      void qc.invalidateQueries({ queryKey: ['allocations'] });
    },
  });
}

export function useFarmerDropout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => {
      const key = getOrCreateIdempotencyKey(`dropout:${id}`);
      return api.post<unknown>(`/allocations/${id}/dropout`, payload, key);
    },
    onSuccess: (_data, { id }) => {
      clearIdempotencyKey(`dropout:${id}`);
      void qc.invalidateQueries({ queryKey: ['allocations'] });
    },
  });
}

// ─── Farmers ──────────────────────────────────────────────────────────────────

interface FarmersFilters {
  parish?: string;
  active?: boolean;
  offset?: number;
  limit?: number;
}

export function useFarmers(filters: FarmersFilters = {}) {
  return useQuery({
    queryKey: qk.farmers(filters),
    queryFn: () => api.get<PaginatedResponse<Farmer>>('/farmers', { ...filters }),
  });
}

export function useFarmerPassport(farmerId: string) {
  return useQuery({
    queryKey: qk.farmerPassport(farmerId),
    queryFn: () => api.get<unknown>(`/farmers/${farmerId}/trade-performance-passport`),
    enabled: !!farmerId,
  });
}

export function useLotShipments(lotId: string) {
  return useQuery({ queryKey: ['production-lots', lotId, 'shipments'], queryFn: () => api.get<Shipment[]>(`/production-lots/${lotId}/shipments`), enabled: !!lotId });
}

export function useSublotTraceability(sublotId: string) {
  return useQuery({ queryKey: ['sublots', sublotId, 'traceability'], queryFn: () => api.get<unknown>(`/sublots/${sublotId}/traceability`), enabled: !!sublotId });
}

// ─── Production Lots ──────────────────────────────────────────────────────────

export function useProductionLots(filters: Record<string, string | number | boolean | undefined | null> = {}) {
  return useQuery({
    queryKey: qk.productionLots(filters),
    queryFn: async () => {
      // The backend production-lot registry currently returns an unpaginated array.
      const items = await api.get<ProductionLot[]>('/production-lots');
      return { items, total: items.length, offset: 0, limit: items.length } satisfies PaginatedResponse<ProductionLot>;
    },
  });
}

export function useProductionLot(id: string) {
  return useQuery({
    queryKey: qk.productionLot(id),
    queryFn: () => api.get<ProductionLot>(`/production-lots/${id}`),
    enabled: !!id,
  });
}

// ─── Fulfilment / Warehouse ───────────────────────────────────────────────────

export function useReceiveSublot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      allocation_id: string;
      fulfilment_node_id: string;
      received_quantity_kg: number;
      received_at: string;
      receipt_evidence_reference?: string;
    }) => {
      const key = getOrCreateIdempotencyKey(`receive:${payload.allocation_id}:${payload.fulfilment_node_id}`);
      return api.post<unknown>('/sublots/receive', payload, key);
    },
    onSuccess: (_data, variables) => {
      clearIdempotencyKey(`receive:${variables.allocation_id}:${variables.fulfilment_node_id}`);
      void qc.invalidateQueries({ queryKey: ['fulfilment'] });
      void qc.invalidateQueries({ queryKey: ['received-sublots'] });
    },
  });
}

export function useGradeSublot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sublotId,
      payload,
    }: {
      sublotId: string;
      payload: { accepted_quantity_kg: number; rejected_quantity_kg: number; assigned_grade?: string; rejection_reason?: string; inspection_evidence_reference?: string };
    }) => {
      const key = getOrCreateIdempotencyKey(`grade:${sublotId}`);
      return api.post<unknown>(`/sublots/${sublotId}/grade`, payload, key);
    },
    onSuccess: (_data, { sublotId }) => {
      clearIdempotencyKey(`grade:${sublotId}`);
      void qc.invalidateQueries({ queryKey: ['fulfilment'] });
    },
  });
}

export function useReceivedSublots(filters: { inspection_status?: string; requirement_id?: string; offset?: number; limit?: number } = {}) {
  return useQuery({ queryKey: ['received-sublots', filters], queryFn: () => api.get<PaginatedResponse<ReceivedSublot>>('/received-sublots', { ...filters }) });
}

// ─── Shipments ────────────────────────────────────────────────────────────────

interface ShipmentsFilters {
  requirement_id?: string;
  offset?: number;
  limit?: number;
}

export function useShipments(filters: ShipmentsFilters = {}) {
  return useQuery({
    queryKey: qk.shipments(filters),
    queryFn: () => api.get<PaginatedResponse<Shipment>>('/shipments', { ...filters }),
  });
}

export function useCreateShipment(requirementId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => {
      const key = getOrCreateIdempotencyKey(`shipment:${requirementId}:new`);
      return api.post<Shipment>(`/requirements/${requirementId}/shipments`, payload, key);
    },
    onSuccess: () => {
      clearIdempotencyKey(`shipment:${requirementId}:new`);
      void qc.invalidateQueries({ queryKey: ['shipments'] });
    },
  });
}

export function useAddSublotToShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ shipmentId, sublotId }: { shipmentId: string; sublotId: string }) => {
      const key = getOrCreateIdempotencyKey(`shipment-sublot:${shipmentId}:${sublotId}`);
      return api.post<unknown>(`/shipments/${shipmentId}/sublots`, { sublot_id: sublotId }, key);
    },
    onSuccess: (_data, { shipmentId, sublotId }) => {
      clearIdempotencyKey(`shipment-sublot:${shipmentId}:${sublotId}`);
      void qc.invalidateQueries({ queryKey: ['shipments'] });
    },
  });
}

export function useShipmentTraceability(id: string) {
  return useQuery({ queryKey: ['shipments', id, 'traceability'], queryFn: () => api.get<unknown>(`/shipments/${id}/traceability`), enabled: !!id });
}

export function useDispatchShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => {
      const key = getOrCreateIdempotencyKey(`dispatch:${id}`);
      return api.post<unknown>(`/shipments/${id}/dispatch`, payload, key);
    },
    onSuccess: (_data, { id }) => {
      clearIdempotencyKey(`dispatch:${id}`);
      void qc.invalidateQueries({ queryKey: ['shipments'] });
    },
  });
}

export function useConfirmDelivery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => {
      const key = getOrCreateIdempotencyKey(`delivery:${id}`);
      return api.post<unknown>(`/shipments/${id}/delivery`, payload, key);
    },
    onSuccess: (_data, { id }) => {
      clearIdempotencyKey(`delivery:${id}`);
      void qc.invalidateQueries({ queryKey: ['shipments'] });
    },
  });
}

export function useReconcile(requirementId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => {
      const key = getOrCreateIdempotencyKey(`reconcile:${requirementId}`);
      return api.post<unknown>(`/requirements/${requirementId}/reconcile`, undefined, key);
    },
    onSuccess: () => {
      clearIdempotencyKey(`reconcile:${requirementId}`);
      void qc.invalidateQueries({ queryKey: qk.requirement(requirementId) });
      void qc.invalidateQueries({ queryKey: qk.assurance(requirementId) });
    },
  });
}

// ─── Recovery Cases ───────────────────────────────────────────────────────────

export function useRecoveryCases(filters: { requirement_id?: string; status?: string; offset?: number; limit?: number } = {}) {
  return useQuery({
    queryKey: [...qk.recoveryCases, filters],
    queryFn: () => api.get<PaginatedResponse<RecoveryCase>>('/recovery-cases', { ...filters }),
  });
}

export function useRecoveryCase(id: string) {
  return useQuery({
    queryKey: qk.recoveryCase(id),
    queryFn: () => api.get<RecoveryCase>(`/recovery-cases/${id}`),
    enabled: !!id,
  });
}

export function useRecoveryCaseEvents(id: string) {
  return useQuery({
    queryKey: ['recovery-cases', id, 'events'],
    queryFn: async () => (await api.get<RecoveryCase & { events?: DomainEvent[] }>(`/recovery-cases/${id}`)).events ?? [],
    enabled: !!id,
  });
}

// ─── Programmes ───────────────────────────────────────────────────────────────

export function useProgrammes(filters: Record<string, string | undefined> = {}) {
  return useQuery({
    queryKey: qk.programmes(filters),
    queryFn: async () => {
      const summaries = await api.get<ProgrammeSummary[]>('/programmes', filters);
      const items = summaries.map(x => ({ ...x.programme, requirement_count: x.requirement_count }));
      return { items, total: items.length, offset: 0, limit: items.length } satisfies PaginatedResponse<Programme>;
    },
  });
}

export function useProgramme(id: string) {
  return useQuery({
    queryKey: qk.programme(id),
    queryFn: async () => {
      const summary = await api.get<ProgrammeSummary>(`/programmes/${id}`);
      return { ...summary.programme, requirement_count: summary.requirement_count } satisfies Programme;
    },
    enabled: !!id,
  });
}

export function useCreateProgramme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { buyer_id: string; name: string; start_date: string; end_date: string }) =>
      api.post<Programme>('/programmes', payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['programmes'] }),
  });
}

export function useAddRequirementToProgramme(programmeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requirementId: string) => api.post<unknown>(`/programmes/${programmeId}/requirements/${requirementId}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.programme(programmeId) }); void qc.invalidateQueries({ queryKey: ['requirements'] }); },
  });
}

// ─── Activity Log ─────────────────────────────────────────────────────────────

export function useActivityLog(filters: { limit?: number } = {}) {
  return useQuery({
    queryKey: [...qk.activity, filters],
    queryFn: async () => (await api.get<{ items: DomainEvent[] }>('/activity', filters)).items,
    refetchInterval: 30_000,
  });
}

// ─── Compliance Rules ─────────────────────────────────────────────────────────

export function useComplianceRules() {
  return useQuery({
    queryKey: qk.complianceRules,
    queryFn: async () => (await api.get<{ items: unknown[] }>('/compliance-rules')).items,
    staleTime: 10 * 60_000,
  });
}

// ─── Admin: Users & Roles ─────────────────────────────────────────────────────

export function useOrgUsers() {
  return useQuery({
    queryKey: ['admin', 'users'],
    queryFn: async () => (await api.get<{ items: unknown[] }>('/admin/users')).items,
  });
}

export function useOrganization() {
  return useQuery({ queryKey: ['admin', 'organization'], queryFn: () => api.get<Record<string, unknown>>('/admin/organization') });
}

export function useOrgRoles() {
  return useQuery({
    queryKey: ['admin', 'roles'],
    queryFn: async () => (await api.get<{ items: unknown[] }>('/admin/roles')).items,
    staleTime: 60 * 60_000,
  });
}

export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { email: string; role: string }) =>
      api.post<{ invitation_token: string }>('/admin/users/invitations', payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useChangeRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ membershipId, role }: { membershipId: string; role: string }) =>
      api.patch<unknown>(`/admin/users/${membershipId}/role`, { role }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (membershipId: string) => api.post<unknown>(`/admin/users/${membershipId}/deactivate`), onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin', 'users'] }) });
}

export function useAcceptInvitation() {
  return useMutation({ mutationFn: (token: string) => api.post<unknown>('/invitations/accept', { token }, getOrCreateIdempotencyKey(`invitation:${token}`)), onSuccess: (_data, token) => clearIdempotencyKey(`invitation:${token}`) });
}

// ─── Secure actions (public, no auth) ────────────────────────────────────────

export function useSecureAction(token: string) {
  return useQuery({
    queryKey: ['secure-action', token],
    queryFn: () => api.get<unknown>(`/v1/secure-actions/${token}`),
    enabled: !!token,
    retry: false,
  });
}

export function useCreateSecureLink() { return useMutation({ mutationFn: (payload: { farmer_id: string; purpose: string; expires_in_hours: number }) => api.post<Record<string, unknown>>('/v1/ingestion/secure-links', payload) }); }
export function useExecuteSecureAction(token: string) { return useMutation({ mutationFn: (payload: Record<string, unknown>) => api.post<unknown>(`/v1/secure-actions/${token}`, payload) }); }
export function useCoordinatorObservation() { const qc = useQueryClient(); return useMutation({ mutationFn: (payload: Record<string, unknown>) => api.post<unknown>('/v1/ingestion/coordinator-observations', payload), onSuccess: () => void qc.invalidateQueries({ queryKey: qk.activity }) }); }
export function useImportPreview() { return useMutation({ mutationFn: (payload: { entity_type: string; csv_content: string }) => api.post<Record<string, unknown>>('/v1/ingestion/imports/preview', payload) }); }
export function useConfirmImport() { return useMutation({ mutationFn: (id: string) => api.post<Record<string, unknown>>(`/v1/ingestion/imports/${id}/confirm`) }); }
export function useImportTemplate() { return useMutation({ mutationFn: (entityType: string) => apiBlob(`/v1/ingestion/imports/templates/${encodeURIComponent(entityType)}`) }); }
