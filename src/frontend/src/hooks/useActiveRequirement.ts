'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

// The synthetic 500 kg ginger fixture exists only in the offline demo replay (lib/demoApi.ts).
const DEMO_REQUIREMENT_ID = '00000000-0000-0000-0000-000000000500';
const ACTIVE_ORDER_KEY = 'korofarm.activeOrderId';
export const isDemoMode = process.env.NEXT_PUBLIC_APP_MODE === 'demo';

export function rememberActiveOrder(id: string) {
  try { window.localStorage.setItem(ACTIVE_ORDER_KEY, id); } catch { /* storage unavailable: fall back to most recent order */ }
}

function storedActiveOrder(): string | null {
  try { return window.localStorage.getItem(ACTIVE_ORDER_KEY); } catch { return null; }
}

/**
 * Which order the overview screens show.
 * Demo mode: the synthetic fixture. Live mode: the explicit id (route), else the order last opened,
 * else the organization's most recent order. Never a hardcoded identifier.
 */
export function useActiveRequirementId(explicitId?: string): { requirementId: string; isResolving: boolean } {
  const [stored, setStored] = useState<string | null>(null);
  useEffect(() => { if (!isDemoMode && !explicitId) setStored(storedActiveOrder()); }, [explicitId]);
  const latest = useQuery({
    queryKey: ['requirements', 'latest'],
    queryFn: () => apiFetch<Array<{ id: string }>>('/requirements?limit=1'),
    enabled: !isDemoMode && !explicitId && stored === null,
  });
  if (isDemoMode) return { requirementId: explicitId ?? DEMO_REQUIREMENT_ID, isResolving: false };
  if (explicitId) return { requirementId: explicitId, isResolving: false };
  if (stored) return { requirementId: stored, isResolving: false };
  return { requirementId: latest.data?.[0]?.id ?? '', isResolving: latest.isLoading };
}
