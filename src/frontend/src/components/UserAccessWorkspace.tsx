'use client';

import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, MailPlus, ShieldCheck } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

type Membership = { membership_id: string; name: string; email: string; role: string; status: string; farmer_id: string | null; buyer_id: string | null };
type Assignables = { farmers: Array<{ id: string; name: string; parish: string }>; buyers: Array<{ id: string; name: string }> };
type Invitation = { membership_id: string; status: string; invitation_token: string; delivery: string };

const roles = [
  ['ORGANIZATION_ADMIN', 'Organization administrator'],
  ['PROCUREMENT_MANAGER', 'Procurement manager'],
  ['SUPPLY_COORDINATOR', 'Supply coordinator'],
  ['WAREHOUSE_OPERATOR', 'Warehouse operator'],
  ['AUDITOR', 'Auditor'],
  ['FARMER', 'Farmer'],
  ['BUYER', 'Customer / buyer'],
] as const;

export function UserAccessWorkspace() {
  const queryClient = useQueryClient();
  const [role, setRole] = useState<string>('FARMER');
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const users = useQuery({ queryKey: ['admin', 'users'], queryFn: () => apiFetch<{ items: Membership[] }>('/admin/users') });
  const assignables = useQuery({ queryKey: ['admin', 'assignables'], queryFn: () => apiFetch<Assignables>('/admin/users/assignable-entities') });
  const invite = useMutation({
    mutationFn: (payload: Record<string, string>) => apiFetch<Invitation>('/admin/users/invitations', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: async result => {
      setInvitation(result);
      setCopied(false);
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });

  async function submitInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const payload: Record<string, string> = {
      user_id: String(values.get('user_id')),
      email: String(values.get('email')),
      display_name: String(values.get('display_name')),
      role,
    };
    if (role === 'FARMER') payload.farmer_id = String(values.get('farmer_id'));
    if (role === 'BUYER') payload.buyer_id = String(values.get('buyer_id'));
    await invite.mutateAsync(payload);
    form.reset();
  }

  const demoMode = process.env.NEXT_PUBLIC_APP_MODE === 'demo' || process.env.NEXT_PUBLIC_AUTH_MODE === 'demo';
  return <AppShell programme="Users and access"><main className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="mb-7"><p className="section-eyebrow">Administration</p><h1 className="mt-2 text-3xl font-semibold">Users and access</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Invite authenticated accounts into this organization with only the role and farm or buyer link they need.</p></header>
    {demoMode ? <section className="operational-panel max-w-3xl p-6"><ShieldCheck className="h-5 w-5 text-primary" /><h2 className="mt-3 text-lg font-semibold">Live organization session required</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Offline demo mode does not create users or memberships. Demo roles can be previewed with NEXT_PUBLIC_DEMO_ROLE; they are not authenticated accounts.</p></section> : <>
      <section className="operational-panel max-w-3xl p-5 sm:p-6"><div className="flex items-center gap-3"><MailPlus className="h-5 w-5 text-primary" /><div><p className="section-eyebrow">Provision access</p><h2 className="mt-1 text-lg font-semibold">Invite an existing Supabase account</h2></div></div>
        <form onSubmit={submitInvite} className="mt-6 grid gap-4 sm:grid-cols-2">
          <label className="grid gap-2 text-xs font-medium text-muted-foreground sm:col-span-2">Supabase user ID<input name="user_id" type="text" required pattern="[0-9a-fA-F-]{36}" title="Enter the UUID of the existing Supabase Auth user" className="h-11 rounded-md border border-white/10 bg-background px-3 font-mono text-sm text-foreground" placeholder="UUID from Supabase Auth" /></label>
          <label className="grid gap-2 text-xs font-medium text-muted-foreground">Full name<input name="display_name" minLength={2} maxLength={200} required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
          <label className="grid gap-2 text-xs font-medium text-muted-foreground">Email<input name="email" type="email" maxLength={320} required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
          <label className="grid gap-2 text-xs font-medium text-muted-foreground">Role<select value={role} onChange={event => setRole(event.target.value)} className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground">{roles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {role === 'FARMER' && <label className="grid gap-2 text-xs font-medium text-muted-foreground">Linked farm<select name="farmer_id" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground"><option value="">Choose a farm</option>{assignables.data?.farmers.map(farmer => <option key={farmer.id} value={farmer.id}>{farmer.name} · {farmer.parish}</option>)}</select></label>}
          {role === 'BUYER' && <label className="grid gap-2 text-xs font-medium text-muted-foreground">Linked customer<select name="buyer_id" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground"><option value="">Choose a buyer</option>{assignables.data?.buyers.map(buyer => <option key={buyer.id} value={buyer.id}>{buyer.name}</option>)}</select></label>}
          {assignables.error && <p role="alert" className="text-sm text-destructive sm:col-span-2">Farm and buyer records could not be loaded: {assignables.error.message}</p>}
          {invite.error && <p role="alert" className="text-sm text-destructive sm:col-span-2">{invite.error.message}</p>}
          <button type="submit" disabled={invite.isPending || assignables.isLoading} className="min-h-11 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-60 sm:col-span-2">{invite.isPending ? 'Creating invitation…' : 'Create invitation'}</button>
        </form>
        <p className="mt-4 text-xs leading-5 text-muted-foreground">The invitee must sign in and accept the one-time token. Developer/platform-admin access is internally managed and cannot be granted here.</p>
        {invitation && <div role="status" className="mt-5 border-t border-white/[0.08] pt-4"><p className="text-sm font-semibold text-success">Invitation created</p><p className="mt-1 text-xs text-muted-foreground">Copy and deliver this token to the invited account. It is shown only in this response.</p><div className="mt-3 flex gap-2"><code className="min-w-0 flex-1 break-all rounded-md border border-white/10 bg-background p-3 text-xs">{invitation.invitation_token}</code><button type="button" onClick={async () => { await navigator.clipboard.writeText(invitation.invitation_token); setCopied(true); }} aria-label="Copy invitation token" title="Copy invitation token" className="grid h-11 w-11 shrink-0 place-items-center rounded-md border border-white/10 hover:bg-white/[0.05]">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</button></div><a href="/signup" className="mt-3 inline-block text-xs font-semibold text-primary hover:underline">Open invitation acceptance</a></div>}
      </section>
      <section className="mt-8" aria-labelledby="members-title"><div className="mb-4 flex items-end justify-between"><div><p className="section-eyebrow">Organization members</p><h2 id="members-title" className="mt-1 text-xl font-semibold">Access roster</h2></div><span className="text-xs text-muted-foreground">{users.data?.items.length ?? 0} accounts</span></div>{users.error ? <p role="alert" className="py-6 text-sm text-destructive">Membership roster unavailable: {users.error.message}</p> : users.isLoading ? <p className="py-6 text-sm text-muted-foreground">Loading members…</p> : <div className="divide-y divide-white/[0.07] border-y border-white/[0.07]">{users.data?.items.map(member => <article key={member.membership_id} className="grid gap-2 py-4 sm:grid-cols-[minmax(0,1fr)_180px_100px] sm:items-center"><div><p className="text-sm font-medium">{member.name}</p><p className="mt-1 text-xs text-muted-foreground">{member.email}</p></div><span className="text-xs text-muted-foreground">{member.role.replaceAll('_', ' ')}{member.farmer_id ? ' · linked farm' : member.buyer_id ? ' · linked buyer' : ''}</span><span className="text-xs uppercase text-muted-foreground sm:text-right">{member.status}</span></article>)}</div>}</section>
    </>}
  </main></AppShell>;
}
