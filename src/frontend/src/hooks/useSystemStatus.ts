'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export type MonitoringReason = 'worker_not_running' | 'worker_never_started' | 'processing_overdue' | 'deadlines_overdue' | 'dead_letters'
  | 'recovery_overdue' | 'recovery_failed' | 'stock_ledger_mismatch';

export interface SystemStatus {
  status: 'OPERATIONAL' | 'DEGRADED';
  reasons: MonitoringReason[];
  checked_at: string;
  worker: { state: 'RUNNING' | 'STOPPED' | 'NOT_SEEN'; last_beat_at: string | null; live_workers: number };
  processing: { overdue_messages: number; dead_letters: number; overdue_deadlines: number };
}

export const reasonText: Record<MonitoringReason, string> = {
  worker_not_running: 'The exception worker has stopped.',
  worker_never_started: 'The exception worker has not started.',
  processing_overdue: 'Supplier updates are waiting longer than expected to be checked.',
  deadlines_overdue: 'Supplier reply deadlines or standby expiries are overdue for processing.',
  dead_letters: 'Some supplier updates could not be processed and need investigation.',
  recovery_overdue: 'Recovery planning or approved actions are waiting longer than expected.',
  recovery_failed: 'A recovery task stopped after repeated errors; its incident needs a coordinator.',
  stock_ledger_mismatch: 'Reserved stock on some lots does not match their commitments. Free stock may be wrong until this is investigated.',
};

/** Whether exception detection and deadline enforcement are actually running. Staff only. */
export function useSystemStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['system-status'],
    queryFn: () => apiFetch<SystemStatus>('/system/status'),
    enabled,
    refetchInterval: 15_000,
  });
}
