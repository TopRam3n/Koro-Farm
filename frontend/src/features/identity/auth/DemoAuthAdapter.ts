import type { AuthAdapter, AuthSnapshot, Persona } from './types';

const DEMO_ENABLED = process.env.NEXT_PUBLIC_DEMO_BUILD === 'true' && process.env.NODE_ENV !== 'production';

export class DemoAuthAdapter implements AuthAdapter {
    private listeners = new Set<(snapshot: AuthSnapshot) => void>();
    private current: AuthSnapshot;

    constructor(persona: Persona = 'BUYER') {
        if (!DEMO_ENABLED) throw new Error('DemoAuthAdapter is disabled outside an explicitly enabled non-production demo build.');
        const user = { id: `demo-${persona.toLowerCase()}`, email: `${persona.toLowerCase()}@demo.korofarm.local`, user_metadata: {}, app_metadata: {}, aud: 'authenticated', created_at: '2026-09-01T00:00:00-05:00' } as AuthSnapshot['user'];
        this.current = { user, session: null, memberships: [{ id: `demo-membership-${persona.toLowerCase()}`, userId: user!.id, organizationId: 'demo-org', persona, role: persona === 'OPS' ? 'COORDINATOR' : persona === 'FARMER' ? 'PRODUCER' : 'MEMBER', status: 'ACTIVE' }] };
    }

    async getSnapshot() { return this.current; }
    subscribe(listener: (snapshot: AuthSnapshot) => void) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
    async signIn() { this.listeners.forEach(listener => listener(this.current)); return this.current; }
    async signOut() { this.current = { user: null, session: null, memberships: [] }; this.listeners.forEach(listener => listener(this.current)); }
}
