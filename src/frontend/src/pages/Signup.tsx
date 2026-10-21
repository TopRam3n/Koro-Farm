'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, MailCheck, ShieldCheck } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { useAuth } from '@/hooks/useAuth';
import { apiFetch } from '@/lib/api';

type AccessRequest = { id: string; name: string; email: string; requested_role: 'FARMER' | 'BUYER'; status: 'PENDING' | 'APPROVED' | 'REJECTED'; created_at: string };

const requestableRoles = [
  { value: 'FARMER', label: 'Farmer', detail: 'Report harvests and ready produce.' },
  { value: 'BUYER', label: 'Customer', detail: 'Browse available produce and place orders.' },
] as const;

export default function Signup() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [requestedRole, setRequestedRole] = useState<'FARMER' | 'BUYER'>('FARMER');
  const [signupMessage, setSignupMessage] = useState('');
  const [error, setError] = useState('');
  const [isCreatingAccount, setIsCreatingAccount] = useState(false);
  const [invitationToken, setInvitationToken] = useState('');

  const demoMode = process.env.NEXT_PUBLIC_APP_MODE === 'demo' || process.env.NEXT_PUBLIC_AUTH_MODE === 'demo';
  const requests = useQuery({
    queryKey: ['access-requests', 'mine'],
    queryFn: () => apiFetch<{ items: AccessRequest[] }>('/access-requests/mine'),
    enabled: Boolean(user) && !demoMode,
  });
  const submitRequest = useMutation({
    mutationFn: (role: 'FARMER' | 'BUYER') => apiFetch('/access-requests', {
      method: 'POST',
      body: JSON.stringify({
        display_name: user?.user_metadata?.display_name || user?.email?.split('@')[0] || name,
        requested_role: role,
      }),
    }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['access-requests', 'mine'] }),
  });
  const acceptInvitation = useMutation({
    mutationFn: () => apiFetch('/invitations/accept', {
      method: 'POST', body: JSON.stringify({ token: invitationToken }),
    }),
    onSuccess: () => router.replace('/'),
  });

  useEffect(() => {
    const metadataRole = user?.user_metadata?.requested_access_role;
    if (metadataRole === 'FARMER' || metadataRole === 'BUYER') setRequestedRole(metadataRole);
    if (user?.user_metadata?.display_name) setName(user.user_metadata.display_name);
  }, [user]);

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSignupMessage('');
    setIsCreatingAccount(true);
    try {
      const { data, error: signupError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { display_name: name.trim(), requested_access_role: requestedRole },
          emailRedirectTo: `${window.location.origin}/signup`,
        },
      });
      if (signupError) throw signupError;
      if (data.session) {
        await submitRequest.mutateAsync(requestedRole);
        setSignupMessage('Email verified and request submitted for review.');
      } else {
        setSignupMessage('Check your email to verify your account. After verification, sign in to submit your access request.');
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Account creation failed.');
    } finally {
      setIsCreatingAccount(false);
    }
  }

  if (demoMode) {
    return <SignupFrame><div className="text-center"><ShieldCheck className="mx-auto h-6 w-6 text-primary" /><h1 className="mt-4 text-2xl font-bold">Live account registration</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">Sign-up and approval require a configured Supabase project. Offline demo roles are previews only and cannot create authenticated accounts.</p><Link href="/login" className="mt-6 inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground">Back to sign in</Link></div></SignupFrame>;
  }

  const latestRequest = requests.data?.items[0];
  const hasPendingRequest = latestRequest?.status === 'PENDING';

  return <SignupFrame>
    {isLoading ? <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Checking account…</div> : user ? <div>
      <div className="text-center"><MailCheck className="mx-auto h-6 w-6 text-primary" /><h1 className="mt-4 text-2xl font-bold">Request account access</h1><p className="mt-2 text-sm text-muted-foreground">Signed in as {user.email}</p></div>
      {requests.isLoading ? <p className="py-8 text-center text-sm text-muted-foreground">Checking your request…</p> : hasPendingRequest ? <div className="mt-6 rounded-md border border-primary/20 p-4"><p className="text-sm font-semibold">Request pending review</p><p className="mt-1 text-sm text-muted-foreground">Your request for {latestRequest.requested_role === 'BUYER' ? 'Customer' : 'Farmer'} access is awaiting approval from the designated reviewer.</p></div> : latestRequest?.status === 'APPROVED' ? <div className="mt-6 rounded-md border border-success/20 p-4"><p className="text-sm font-semibold text-success">Access approved</p><p className="mt-1 text-sm text-muted-foreground">Your account now has {latestRequest.requested_role === 'BUYER' ? 'Customer' : 'Farmer'} access.</p><button type="button" onClick={() => router.replace('/')} className="mt-4 min-h-10 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground">Open my workspace</button></div> : <>
        <p className="mt-4 text-center text-sm leading-6 text-muted-foreground">Choose the position you’re requesting. Access is activated only after email verification and reviewer approval.</p>
        <RoleChoices selected={requestedRole} onChange={setRequestedRole} />
        {requests.error && <p role="alert" className="mt-4 text-sm text-destructive">{requests.error.message}</p>}
        {submitRequest.error && <p role="alert" className="mt-4 text-sm text-destructive">{submitRequest.error.message}</p>}
        <button type="button" disabled={submitRequest.isPending} onClick={() => submitRequest.mutate(requestedRole)} className="mt-5 min-h-11 w-full rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-60">{submitRequest.isPending ? 'Submitting request…' : 'Submit access request'}</button>
      </>}
      <div className="mt-8 border-t border-white/[0.08] pt-6"><h2 className="text-sm font-semibold">Have an invitation token?</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Use the token provided by your organization administrator.</p><form onSubmit={event => { event.preventDefault(); acceptInvitation.mutate(); }} className="mt-3 flex gap-2"><input value={invitationToken} onChange={event => setInvitationToken(event.target.value)} minLength={32} maxLength={200} required autoComplete="off" className="h-11 min-w-0 flex-1 rounded-md border border-white/10 bg-background px-3 font-mono text-xs text-foreground" placeholder="One-time invitation token" /><button type="submit" disabled={acceptInvitation.isPending} className="min-h-11 rounded-md border border-white/10 px-3 text-xs font-semibold disabled:opacity-60">{acceptInvitation.isPending ? 'Accepting…' : 'Accept'}</button></form>{acceptInvitation.error && <p role="alert" className="mt-2 text-xs text-destructive">{acceptInvitation.error.message}</p>}</div>
    </div> : <>
      <div className="text-center"><MailCheck className="mx-auto h-6 w-6 text-primary" /><h1 className="mt-4 text-2xl font-bold">Create your account</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">Verify your email, then request Farmer or Customer access. A reviewer approves role and account linkage.</p></div>
      <form onSubmit={createAccount} className="mt-6 space-y-4">
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">Full name<input value={name} onChange={event => setName(event.target.value)} minLength={2} maxLength={200} required autoComplete="name" className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">Email address<input value={email} onChange={event => setEmail(event.target.value)} type="email" required autoComplete="email" className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
        <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">Password<input value={password} onChange={event => setPassword(event.target.value)} type="password" minLength={8} required autoComplete="new-password" className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
        <fieldset><legend className="mb-2 text-xs font-medium text-muted-foreground">Position requested</legend><RoleChoices selected={requestedRole} onChange={setRequestedRole} /></fieldset>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {signupMessage && <p role="status" className="flex gap-2 text-sm text-success"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{signupMessage}</p>}
        <button type="submit" disabled={isCreatingAccount} className="min-h-11 w-full rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-60">{isCreatingAccount ? 'Creating account…' : 'Create account'}</button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">Already have an account? <Link href="/login?next=/signup" className="font-semibold text-primary hover:underline">Sign in</Link></p>
    </>}
    <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-[11px] leading-5 text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5 shrink-0" />Developer access is internally managed and cannot be requested here.</p>
  </SignupFrame>;
}

function RoleChoices({ selected, onChange }: { selected: 'FARMER' | 'BUYER'; onChange: (role: 'FARMER' | 'BUYER') => void }) {
  return <div className="mt-3 grid gap-2 sm:grid-cols-2">{requestableRoles.map(role => <label key={role.value} className={`flex cursor-pointer gap-3 rounded-md border p-3 ${selected === role.value ? 'border-primary/50 bg-primary/[0.06]' : 'border-white/[0.08]'}`}><input type="radio" name="requested-role" value={role.value} checked={selected === role.value} onChange={() => onChange(role.value)} className="mt-0.5 accent-primary" /><span><span className="block text-sm font-semibold text-foreground">{role.label}</span><span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{role.detail}</span></span></label>)}</div>;
}

function SignupFrame({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8"><section className="w-full max-w-lg rounded-[10px] border border-white/[0.08] bg-card p-6 sm:p-9"><Link href="/" aria-label="KoroFarm home"><Image src="/brand/korofarm-wordmark.png" alt="KoroFarm — Supply Assurance OS" width={190} height={63} className="mx-auto h-auto w-[170px] object-contain" priority /></Link>{children}</section></main>;
}
