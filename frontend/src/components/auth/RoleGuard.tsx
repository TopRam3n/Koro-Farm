'use client';

import type { AppRole, Persona } from '@/features/identity/auth';
import { hasActiveMembership, useAuth } from '@/hooks/useAuth';

export function RoleGuard({ persona, role, children }: { persona: Persona; role: AppRole; children: React.ReactNode }) {
    const { memberships, isLoading } = useAuth();
    if (isLoading) return null;
    return hasActiveMembership(memberships, persona, role) ? <>{children}</> : null;
}
