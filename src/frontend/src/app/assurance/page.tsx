'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { AuthGate } from '@/components/AuthGate';
import { AppShell } from '@/components/AppShell';
import { ControlCenterView } from '@/components/ControlCenterView';
import { apiFetch } from '@/lib/api';

type Me = { active_role: string | null; active_buyer_id?: string | null };
type Offer = { id: string; farmer_name: string; parish: string; quantity_kg: string; status: string };
type AssuranceRequest = {
  id: string; buyer_name: string; crop: string; grade: string;
  lifecycle_status: string; delivery_window_start: string; delivery_window_end: string;
  required_quantity_kg: string; committed_quantity_kg: string;
  pending_offer_quantity_kg: string; remaining_quantity_kg: string;
  coverage_pct: number; coverage_status: string; committed_farmer_count: number; offers: Offer[];
};
type AssuranceList = { items: AssuranceRequest[]; buyer_name: string; coverage_basis: string };
const kg = (v: string) => `${Number(v).toLocaleString('en-JM', {maximumFractionDigits: 3})} kg`;
const human = (v: string) => v.replace(/_/g, ' ');

function BuyerAssurance() {
  const query = useQuery({ queryKey: ['buyer-marketplace-assurance'], queryFn: () => apiFetch<AssuranceList>('/marketplace/requests/assurance'), retry: false, refetchInterval: 30000 });
  const data = query.data;
  const active = data?.items.filter(r => r.lifecycle_status !== 'CANCELLED') ?? [];
  const total = active.reduce((s, r) => s + Number(r.required_quantity_kg), 0);
  const accepted = active.reduce((s, r) => s + Number(r.committed_quantity_kg), 0);
  const remaining = active.reduce((s, r) => s + Number(r.remaining_quantity_kg), 0);
  return <AppShell programme="Procurement assurance"><main className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-6 lg:px-8">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">Buyer procurement</p><h1 className="mt-2 text-3xl font-semibold">Assurance Center</h1><p className="mt-2 text-sm text-slate-400">Track accepted farmer commitments and remaining supply for your procurement requests.</p></div><Link href="/demand/demo-orders" className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500">Manage procurement requests</Link></header>
    {query.isLoading && <p role="status" className="text-slate-300">Loading procurement assurance…</p>}
    {query.isError && <section role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-5"><p className="font-medium text-red-300">Assurance data unavailable</p><p className="mt-2 text-sm text-slate-300">{query.error.message}</p><button onClick={() => void query.refetch()} className="mt-3 rounded border px-3 py-2 text-sm">Retry</button></section>}
    {data && <>
      <p className="text-sm text-slate-400">{data.buyer_name} · Coverage counts accepted farmer offers only; pending offers do not reserve stock.</p>
      <section className="grid gap-3 sm:grid-cols-4" aria-label="Assurance summary">{[
        ['Requests', String(active.length)], ['Requested', `${total.toLocaleString('en-JM')} kg`],
        ['Accepted', `${accepted.toLocaleString('en-JM')} kg`], ['Remaining', `${remaining.toLocaleString('en-JM')} kg`],
      ].map(([label, value]) => <div key={label} className="rounded-xl border border-white/10 bg-[#12201b] p-5"><p className="text-xs text-slate-400">{label}</p><p className="mt-2 text-2xl font-bold tabular-nums">{value}</p></div>)}</section>
      {!data.items.length && <section className="rounded-xl border border-dashed border-white/15 p-8 text-center"><h2 className="font-semibold">No procurement requests</h2><p className="mt-2 text-sm text-slate-400">Publish a request in the marketplace to start tracking assurance.</p><Link className="mt-3 inline-block text-emerald-300 underline" href="/demand/demo-orders">Open procurement requests</Link></section>}
      <section className="space-y-4" aria-label="Individual request assurance">{data.items.map(r => <article key={r.id} className="space-y-4 rounded-xl border border-white/10 bg-[#12201b] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">{human(r.crop)} · Grade {r.grade}</h2><p className="mt-1 text-sm text-slate-400">Delivery: {r.delivery_window_start} – {r.delivery_window_end} · {human(r.lifecycle_status)}</p></div><span className={`rounded-full px-3 py-1 text-xs font-semibold ${r.coverage_status === 'COVERED' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-amber-400/15 text-amber-300'}`}>{human(r.coverage_status)}</span></div>
        <div className="grid gap-3 sm:grid-cols-4">{[['Required', kg(r.required_quantity_kg)], ['Accepted', kg(r.committed_quantity_kg)], ['Remaining', kg(r.remaining_quantity_kg)], ['Pending offers', kg(r.pending_offer_quantity_kg)]].map(([label,value]) => <div key={label}><p className="text-xs text-slate-400">{label}</p><p className="mt-1 font-semibold tabular-nums">{value}</p></div>)}</div>
        <div role="meter" aria-label="Accepted coverage percentage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(r.coverage_pct)} className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-emerald-500" style={{width: `${Math.min(100, Math.max(0,r.coverage_pct))}%`}} /></div>
        <p className="text-xs text-slate-400">{r.coverage_pct.toFixed(1)}% accepted coverage · {r.committed_farmer_count} committed farmers</p>
        {r.offers.length > 0 && <div className="border-t border-white/10 pt-3"><h3 className="text-sm font-semibold">Farmer offers</h3><div className="mt-2 space-y-2">{r.offers.map(o => <div key={o.id} className="flex flex-wrap items-center justify-between gap-2 text-sm"><span>{o.farmer_name} · {o.parish} · {kg(o.quantity_kg)}</span><span className="text-slate-300">{human(o.status)}</span></div>)}</div></div>}
        <Link href="/demand/demo-orders" className="inline-block text-sm font-medium text-emerald-300 hover:underline">Review requests and offers →</Link>
      </article>)}</section>
      <p className="text-xs text-slate-500">This marketplace coverage summary is distinct from finalized operations supply plans, fulfilment receipts, and verified delivered supply. It does not generate risk scores or authorize recoveries.</p>
    </>}
  </main></AppShell>;
}

function AssuranceWorkspace() {
  const me = useQuery({queryKey: ['assurance-user-role'], queryFn: () => apiFetch<Me>('/me'), retry: false});
  if (me.isLoading) return <p role="status" className="p-8">Loading assurance workspace…</p>;
  if (me.isError) return <div role="alert" className="p-8">Unable to load account permissions: {me.error.message}</div>;
  if (me.data?.active_role === 'BUYER') return <BuyerAssurance />;
  if (me.data?.active_role === 'FARMER') return <AppShell programme="Assurance"><main className="mx-auto max-w-4xl space-y-4 p-8"><h1 className="text-3xl font-semibold">Farmer commitments</h1><p className="text-slate-400">Manage your offers and accepted commitments in Buyer Opportunities.</p><Link href="/demand/demo-orders" className="text-emerald-300 underline">Open Buyer Opportunities</Link></main></AppShell>;
  return <ControlCenterView />;
}

export default function Page() { return <AuthGate><AssuranceWorkspace /></AuthGate>; }
