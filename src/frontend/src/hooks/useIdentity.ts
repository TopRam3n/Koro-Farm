'use client';

import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export interface IdentityProfile {
  id: string;
  email: string;
  name: string;
  active_organization_id: string;
  active_role: string;
  active_farmer_id: string | null;
  active_buyer_id: string | null;
  /** What the active membership may do (R1 WP5, M1). Display only: the server checks every action itself. */
  permissions?: string[];
}

export function useIdentity() {
  return useQuery({
    queryKey: ['identity', 'me'],
    queryFn: () => apiFetch<IdentityProfile>('/me'),
    staleTime: 30_000,
  });
}

/**
 * Whether the signed-in member may take an action, so the workspace shows only what they can do.
 * Fails closed: while the profile is loading, or if it has no permission list, nothing is offered.
 */
export function useCan() {
  const identity = useIdentity();
  const permissions = identity.data?.permissions;
  return useCallback((permission: string) => Boolean(permissions?.includes(permission)), [permissions]);
}
