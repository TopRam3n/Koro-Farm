import type { AuthAdapter } from './types';
import { DemoAuthAdapter } from './DemoAuthAdapter';
import { SupabaseAuthAdapter } from './SupabaseAuthAdapter';

export type { AppMembership, AppRole, AuthAdapter, AuthSnapshot, Persona } from './types';
export { DemoAuthAdapter, SupabaseAuthAdapter };

export function createAuthAdapter(): AuthAdapter {
    if (process.env.NEXT_PUBLIC_DEMO_BUILD === 'true' && process.env.NODE_ENV !== 'production') return new DemoAuthAdapter();
    return new SupabaseAuthAdapter();
}
