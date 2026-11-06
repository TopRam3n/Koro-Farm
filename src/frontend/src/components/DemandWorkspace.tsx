'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, ClipboardList, RefreshCw, Search } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { useIdentity } from '@/hooks/useIdentity';

type DemandItem = {
  id: string;
  buyer_id: string;
  buyer_name: string;
  programme_id: string | null;
  crop: string;
  grade: string;
  lifecycle_status: string;
  planning_supply_health: string;
  delivery_window_start: string;
  delivery_window_end: string;
  required_quantity_kg: string;
  accepted_offer_quantity_kg: string;
  pending_offer_quantity_kg: string;
  remaining_offer_quantity_kg: string;
  offer_coverage_pct: number;
  coverage_status: string;
  planned_committed_quantity_kg: string;
};
type DemandData = {
  items: DemandItem[];
  scope: 'buyer' | 'organization_staff';
  pagination: { offset: number; limit: number; total: number; has_more: boolean };
  summary: {
    page_requests: number;
    page_active_requests: number;
    page_requested_kg: string;
    page_accepted_offer_kg: string;
    page_remaining_offer_kg: string;
  };
  coverage_basis: string;
};

const PAGE_SIZE = 25;
const kg = (v: string | number) => `${Number(v).toLocaleString('en-JM', { maximumFractionDigits: 3 })} kg`;
const human = (v: string) => v.replace(/_/g, ' ');
const dates = (start: string, end: string) => `${start} – ${end}`;
const selectClass = 'h-11 min-w-0 rounded-md border border-white/15 bg-background px-3 text-sm text-foreground';

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="operational-panel p-4 sm:p-5"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>{note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}</div>;
}

export function DemandWorkspace() {
  const identity = useIdentity();
  const [crop, setCrop] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(0);
  const role = identity.data?.active_role;
  const isFarmer = role === 'FARMER';
  const isBuyer = role === 'BUYER';
  const allowed = Boolean(role && role !== 'FARMER');
  const query = useQuery({
    queryKey: ['marketplace', 'demand-ledger', identity.data?.active_organization_id, role, crop, status, page],
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
      if (crop) params.set('crop', crop);
      if (status) params.set('lifecycle_status', status);
      return apiFetch<DemandData>(`/marketplace/demand?${params}`);
    },
    enabled: allowed,
    retry: false,
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
  const data = query.data;
  const resetPage = (setter: (value: string) => void) => (next: string) => { setter(next); setPage(0); };

  return <AppShell programme="Institutional procurement · Demand"><main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="section-eyebrow">KoroFarm Operations</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Demand</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Buyer requirements, delivery windows and accepted farmer-offer coverage, sourced from the marketplace database.</p></div>
      <div className="flex flex-wrap gap-2">
        {isBuyer && <Link href="/demand/demo-orders" className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground">Manage requests <ArrowRight className="h-4 w-4" /></Link>}
        <button type="button" disabled={!allowed || query.isFetching} onClick={() => void query.refetch()} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/20 px-4 text-sm font-medium disabled:opacity-50"><RefreshCw className="h-4 w-4" />Refresh</button>
      </div>
    </header>

    {identity.isLoading && <p role="status" className="operational-panel p-6">Verifying your organization and role…</p>}
    {identity.isError && <div role="alert" className="operational-panel p-6"><h2 className="font-semibold">Account access unavailable</h2><p className="mt-2 text-sm text-muted-foreground">{identity.error.message}</p></div>}
    {isFarmer && <section className="operational-panel space-y-3 p-6"><h2 className="text-xl font-semibold">Buyer opportunities</h2><p className="text-sm text-muted-foreground">Farmers can review published opportunities and manage their own offers in the marketplace.</p><Link href="/demand/demo-orders" className="inline-flex items-center gap-2 text-primary underline underline-offset-4">Open buyer opportunities <ArrowRight className="h-4 w-4" /></Link></section>}
    {identity.data && !allowed && !isFarmer && <p role="alert" className="operational-panel p-6">Your active membership does not have access to the Demand ledger.</p>}
    {allowed && <>
      <section className="operational-panel p-4 sm:p-5" aria-label="Demand filters"><div className="flex flex-wrap items-end gap-3">
        <label className="grid min-w-[160px] flex-1 gap-1.5 text-xs text-muted-foreground">Crop<select className={selectClass} value={crop} onChange={e => resetPage(setCrop)(e.target.value)}><option value="">All crops</option><option value="GINGER">Ginger</option></select></label>
        <label className="grid min-w-[190px] flex-1 gap-1.5 text-xs text-muted-foreground">Lifecycle<select className={selectClass} value={status} onChange={e => resetPage(setStatus)(e.target.value)}>
          {['','DRAFT','PLANNING','ACTIVE','IN_FULFILMENT','RECONCILED','CLOSED','CANCELLED'].map(s => <option key={s} value={s}>{s ? human(s) : 'All statuses'}</option>)}
        </select></label>
        <div className="flex h-11 items-center gap-2 px-2 text-xs text-muted-foreground"><Search className="h-4 w-4" />{data ? `${data.pagination.total} matching requests` : 'Filter requests'}</div>
      </div></section>
      {query.isLoading && <p role="status" className="operational-panel p-6">Loading authorized requirements…</p>}
      {query.isError && <section role="alert" className="operational-panel p-6"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 text-warning"/><div><h2 className="font-semibold">Demand records unavailable</h2><p className="mt-2 text-sm text-muted-foreground">{query.error.message}</p><p className="mt-2 text-xs text-muted-foreground">Check /marketplace/demand in the backend and confirm the farmer_offers migration exists in the connected database. No quantities have been substituted.</p></div></div></section>}
      {data && <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Current page demand metrics">
          <Stat label="Active requests" value={String(data.summary.page_active_requests)} note="Shown page only" />
          <Stat label="Required" value={kg(data.summary.page_requested_kg)} />
          <Stat label="Accepted offers" value={kg(data.summary.page_accepted_offer_kg)} note="Not delivered supply" />
          <Stat label="Remaining" value={kg(data.summary.page_remaining_offer_kg)} />
        </div>
        <section className="operational-panel overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-5 py-4"><div><h2 className="text-lg font-semibold">Procurement requirements</h2><p className="mt-1 text-xs text-muted-foreground">{data.scope === 'buyer' ? 'Your linked buyer account' : 'Authorized organization portfolio'} · {data.pagination.total} results</p></div><span className="text-xs text-muted-foreground">Page {page + 1}</span></div>
          {!data.items.length && <div className="px-5 py-12 text-center"><ClipboardList className="mx-auto h-6 w-6 text-muted-foreground"/><h3 className="mt-3 font-medium">No matching requirements</h3><p className="mt-1 text-sm text-muted-foreground">Change the filters or create a procurement request from the buyer marketplace.</p></div>}
          <div className="divide-y divide-white/[0.08]">{data.items.map(item => {
            const pct = Math.max(0, Math.min(100, Number(item.offer_coverage_pct) || 0));
            return <article key={item.id} className="p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{human(item.crop)} · Grade {item.grade}</h3><p className="mt-1 text-sm text-muted-foreground">{item.buyer_name} · {dates(item.delivery_window_start, item.delivery_window_end)}</p><p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">Requirement {item.id}</p></div><div className="flex flex-wrap gap-2"><span className="rounded-md border border-white/15 px-2.5 py-1 text-xs">{human(item.lifecycle_status)}</span><span className="rounded-md border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs text-primary">{human(item.coverage_status)}</span></div></div>
              <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4"><div><dt className="text-xs text-muted-foreground">Required</dt><dd className="mt-1 font-semibold tabular-nums">{kg(item.required_quantity_kg)}</dd></div><div><dt className="text-xs text-muted-foreground">Accepted offers</dt><dd className="mt-1 font-semibold tabular-nums">{kg(item.accepted_offer_quantity_kg)}</dd></div><div><dt className="text-xs text-muted-foreground">Outstanding</dt><dd className="mt-1 font-semibold tabular-nums">{kg(item.remaining_offer_quantity_kg)}</dd></div><div><dt className="text-xs text-muted-foreground">Pending offers</dt><dd className="mt-1 font-semibold tabular-nums">{kg(item.pending_offer_quantity_kg)}</dd></div></dl>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10" role="meter" aria-label="Accepted offer coverage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}><div className="h-full rounded-full bg-primary" style={{width:`${pct}%`}}/></div><div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-muted-foreground"><span>{pct.toFixed(1)}% accepted-offer coverage</span><span>{item.programme_id ? 'Linked to programme' : 'No programme linked'}</span></div>
              {Number(item.planned_committed_quantity_kg) > 0 && <p className="mt-3 text-xs text-muted-foreground">Separate finalized operations-plan commitment: {kg(item.planned_committed_quantity_kg)}. Not added to offer coverage.</p>}
              <div className="mt-4 flex flex-wrap gap-4 text-sm">{isBuyer ? <Link href="/demand/demo-orders" className="font-medium text-primary hover:underline">Review offers <ArrowRight className="inline h-4 w-4"/></Link> : <Link href={`/requirements/${item.id}`} className="font-medium text-primary hover:underline">Open staff requirement <ArrowRight className="inline h-4 w-4"/></Link>}</div>
            </article>;
          })}</div>
        </section>
        <div className="flex flex-wrap items-center justify-between gap-4"><p className="text-xs text-muted-foreground">Showing {data.items.length ? data.pagination.offset + 1 : 0}–{data.pagination.offset + data.items.length} of {data.pagination.total}. Summary metrics describe this page.</p><div className="flex gap-2"><button type="button" className="rounded border border-white/20 px-4 py-2 text-sm disabled:opacity-40" disabled={page === 0 || query.isFetching} onClick={() => setPage(p => Math.max(0, p-1))}>Previous</button><button type="button" className="rounded border border-white/20 px-4 py-2 text-sm disabled:opacity-40" disabled={!data.pagination.has_more || query.isFetching} onClick={() => setPage(p => p+1)}>Next</button></div></div>
        <p className="flex items-start gap-2 text-xs leading-5 text-muted-foreground"><ClipboardList className="mt-0.5 h-4 w-4 shrink-0" />{data.coverage_basis} Demand reflects procurement commitments, not confirmed fulfilment. Refresh after an offer is accepted.</p>
      </>}
    </>}
  </main></AppShell>;
}
