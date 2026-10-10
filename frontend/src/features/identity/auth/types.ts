import type { Session, User } from '@supabase/supabase-js';

export type Persona = 'BUYER' | 'FARMER' | 'OPS';
export type AppRole = 'MEMBER' | 'PRODUCER' | 'ADMIN' | 'COORDINATOR';

export interface AppMembership {
    id: string;
    userId: string;
    organizationId: string;
    persona: Persona;
    role: AppRole;
    status: 'ACTIVE' | 'PENDING' | 'SUSPENDED';
}

export interface AuthSnapshot {
    user: User | null;
    session: Session | null;
    memberships: AppMembership[];
}

export interface AuthAdapter {
    getSnapshot(): Promise<AuthSnapshot>;
    subscribe(listener: (snapshot: AuthSnapshot) => void): () => void;
    signIn(email: string, password: string): Promise<AuthSnapshot>;
    signOut(): Promise<void>;
}
