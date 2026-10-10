'use client';

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
}

export function useIdentity() {
  return useQuery({
    queryKey: ['identity', 'me'],
    queryFn: () => apiFetch<IdentityProfile>('/me'),
    staleTime: 30_000,
  });
}
