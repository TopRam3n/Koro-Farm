'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { SignupPersona } from './types';
import { ONBOARDING_EMAIL_KEY, SIGNUP_PERSONA_KEY, onboardingDestination } from './registration';

export function SignupAccount({ persona }: { persona: SignupPersona }) {
    const router = useRouter();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault(); setLoading(true); setError('');
        // Supabase signUp() does not replace an already authenticated user in all
        // configurations. Starting registration from a stale session can therefore
        // provision/navigate as the previous account. Registration must always begin
        // from an anonymous auth state.
        const { error: signOutError } = await supabase.auth.signOut();
        if (signOutError) { setLoading(false); setError('Could not start a new registration session. Please try again.'); return; }
        const { error: intentError } = await supabase.rpc('register_signup_intent', { requested_email: email, requested_persona: persona });
        if (intentError) { setLoading(false); setError('Could not initialize account registration. Please try again.'); return; }
        const { data, error: authError } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin, data: { signup_persona: persona } } });
        setLoading(false);
        if (authError) { setError(authError.message); return; }
        sessionStorage.setItem(SIGNUP_PERSONA_KEY, persona);
        sessionStorage.setItem(ONBOARDING_EMAIL_KEY, email);
        if (data.session) {
            if (!data.user || data.session.user.id !== data.user.id || data.user.email?.toLowerCase() !== email.trim().toLowerCase()) {
                await supabase.auth.signOut();
                setError('The new account session could not be verified. Please sign in with the account you just created.');
                return;
            }
            const { error: membershipError } = await supabase.rpc('claim_signup_membership');
            if (membershipError) { setError('Account created, but application access could not be provisioned. Sign in after confirming your account.'); return; }
            const { data: memberships } = await supabase.from('app_memberships').select('id,user_id,organization_id,persona,role,status').eq('user_id', data.user!.id);
            if (!memberships?.length) { setError('Account created, but access provisioning is still pending.'); return; }
        }
        // Signup persona controls onboarding UX only. Protected membership controls product access.
        router.push(onboardingDestination(persona));
    };

    return <main className="mx-auto flex min-h-screen max-w-lg items-center p-5"><form className="w-full space-y-5" onSubmit={submit}><div><p className="font-mono text-xs uppercase text-primary">{persona === 'FARMER' ? 'Farmer' : 'Buyer'} registration</p><h1 className="mt-2 text-3xl font-semibold">Create your account</h1><p className="mt-2 text-sm text-muted-foreground">Create sign-in credentials before completing your KoroFarm profile.</p></div><div className="space-y-2"><Label htmlFor="signup-email">Email</Label><Input id="signup-email" type="email" required value={email} onChange={e => setEmail(e.target.value)} /></div><div className="space-y-2"><Label htmlFor="signup-password">Password</Label><Input id="signup-password" type="password" minLength={6} required value={password} onChange={e => setPassword(e.target.value)} /><p className="text-xs text-muted-foreground">At least 6 characters.</p></div>{error && <p className="rounded border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}<Button className="h-12 w-full" disabled={loading}>{loading ? 'Creating account…' : 'Create account & continue'}</Button></form></main>;
}
