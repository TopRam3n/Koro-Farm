'use client';

import { Loader2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import type { Persona } from '@/features/identity/auth';
import { hasActiveMembership, useAuth } from '@/hooks/useAuth';
import { activeAlternatePersona, personaHome } from '@/features/identity/auth/routing';

export function PersonaGuard({ persona, children }: { persona: Persona; children: React.ReactNode }) {
    const { user, memberships, isLoading } = useAuth();
    const router = useRouter();
    const allowed = hasActiveMembership(memberships, persona);
    const alternate = activeAlternatePersona(memberships, persona);
    useEffect(() => { if (!isLoading && !user) router.replace('/login'); else if (!isLoading && user && !allowed && alternate) router.replace(personaHome(alternate)); else if (!isLoading && user && !allowed && memberships.length === 0) router.replace('/account/setup'); else if (!isLoading && user && !allowed && memberships.some(m => m.persona === persona && m.status === 'PENDING')) router.replace('/account/pending'); }, [alternate, allowed, isLoading, memberships, persona, router, user]);
    if (isLoading || !user) return <div className="flex min-h-[50vh] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
    if (!allowed) { const pending = memberships.some(m => m.persona === persona && m.status === 'PENDING'), suspended = memberships.some(m => m.persona === persona && m.status === 'SUSPENDED'); return <div className="mx-auto max-w-xl p-8"><h1 className="text-xl font-semibold">{pending ? 'Account awaiting activation' : suspended ? 'Access suspended' : 'Access unavailable'}</h1><p className="mt-2 text-sm text-muted-foreground">{pending ? 'Your membership exists but is not active yet.' : suspended ? 'This membership is currently suspended.' : 'Your account has no active membership for this application context.'}</p></div>; }
    return <>{children}</>;
}
