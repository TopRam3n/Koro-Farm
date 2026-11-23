'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

const ACTIVE_ORDER_KEY = 'korofarm.activeOrderId';

export function rememberActiveOrder(id: string) {
  try { window.localStorage.setItem(ACTIVE_ORDER_KEY, id); } catch { /* storage unavailable: fall back to most recent order */ }
}

function storedActiveOrder(): string | null {
  try { return window.localStorage.getItem(ACTIVE_ORDER_KEY); } catch { return null; }
}

/**
 * Which order the overview screens show.
 * The explicit id (route), else the order last opened, else the organization's most recent order.
 * Never a hardcoded identifier.
 */
export function useActiveRequirementId(explicitId?: string): { requirementId: string; isResolving: boolean } {
  const [stored, setStored] = useState<string | null>(null);
  useEffect(() => { if (!explicitId) setStored(storedActiveOrder()); }, [explicitId]);
  const latest = useQuery({
    queryKey: ['requirements', 'latest'],
    queryFn: () => apiFetch<Array<{ id: string }>>('/requirements?limit=1'),
    enabled: !explicitId && stored === null,
  });
  if (explicitId) return { requirementId: explicitId, isResolving: false };
  if (stored) return { requirementId: stored, isResolving: false };
  return { requirementId: latest.data?.[0]?.id ?? '', isResolving: latest.isLoading };
}
