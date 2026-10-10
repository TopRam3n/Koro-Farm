'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { createAuthAdapter, type AuthAdapter, type AuthSnapshot } from '@/features/identity/auth';
import { hasActiveMembership } from '@/features/identity/auth/authorization';

export { hasActiveMembership } from '@/features/identity/auth/authorization';

interface AuthContextType extends AuthSnapshot {
    isLoading: boolean;
    signIn: (email: string, password: string) => Promise<AuthSnapshot>;
    signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const defaultAdapter = createAuthAdapter();

export function AuthProvider({ children, adapter = defaultAdapter }: { children: ReactNode; adapter?: AuthAdapter }) {
    const [state, setState] = useState<AuthSnapshot>({ user: null, session: null, memberships: [] });
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        let active = true;
        const unsubscribe = adapter.subscribe(next => { if (active) { setState(next); setIsLoading(false); } });
        adapter.getSnapshot().then(next => { if (active) setState(next); }).finally(() => { if (active) setIsLoading(false); });
        return () => { active = false; unsubscribe(); };
    }, [adapter]);

    const signIn = async (email: string, password: string) => { const next = await adapter.signIn(email, password); setState(next); return next; };
    const signOut = async () => { await adapter.signOut(); setState({ user: null, session: null, memberships: [] }); };

    return <AuthContext.Provider value={{ ...state, isLoading, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) throw new Error('useAuth must be used within an AuthProvider');
    return context;
}
