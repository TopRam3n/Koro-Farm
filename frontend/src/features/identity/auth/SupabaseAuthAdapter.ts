import type { AuthAdapter, AuthSnapshot } from './types';
import { supabase } from '@/integrations/supabase/client';
import { toMembership, type MembershipRow } from './membership';

async function snapshot(session: AuthSnapshot['session']): Promise<AuthSnapshot> {
    const user = session?.user ?? null;
    if (!user) return { session, user, memberships: [] };
    // This table is protected by RLS. Authorization never comes from auth metadata or browser storage.
    const { data, error } = await supabase.from('app_memberships').select('id,user_id,organization_id,persona,role,status').eq('user_id', user.id);
    // Membership lookup is part of authentication resolution. Treat transport/schema/RLS
    // failures differently from a legitimate empty result so configuration defects are visible.
    if (error) throw new Error(`MEMBERSHIP_LOOKUP_FAILED: ${error.message}`);
    return { session, user, memberships: (data ?? []).map(row => toMembership(row as MembershipRow)) };
}

export class SupabaseAuthAdapter implements AuthAdapter {
    async getSnapshot() {
        try {
            const { data, error } = await supabase.auth.getSession();
            if (error) throw error;
            return await snapshot(data.session);
        } catch (error) {
            // A temporarily unreachable Supabase project must not become an
            // unhandled rejection during application bootstrap. Explicit
            // sign-in still surfaces its error to the login form.
            console.error('Supabase authentication is unavailable', error);
            return { session: null, user: null, memberships: [] };
        }
    }

    subscribe(listener: (value: AuthSnapshot) => void) {
        const { data } = supabase.auth.onAuthStateChange((_event, session) => { void snapshot(session).then(listener).catch(() => listener({ session, user: session?.user ?? null, memberships: [] })); });
        return () => data.subscription.unsubscribe();
    }

    async signIn(email: string, password: string) {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        return snapshot(data.session);
    }

    async signOut() {
        const { error } = await supabase.auth.signOut();
        if (error) throw error;
    }
}
