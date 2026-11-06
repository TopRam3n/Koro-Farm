'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Building2, ClipboardList, RefreshCw, Plus, Link2, AlertTriangle } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { useIdentity } from '@/hooks/useIdentity';

type RequestPreview = {
  id: string; crop: string; grade: string; lifecycle_status: string;
  required_quantity_kg: string; accepted_offer_quantity_kg?: string;
  delivery_window_start: string; delivery_window_end: string;
};
type Programme = {
  id: string; buyer_id: string; buyer_name: string; name: string; commodity_scope: string | null;
  start_date: string; end_date: string; status: 'ACTIVE' | 'PAUSED' | 'COMPLETED';
  requirement_count: number; active_requirement_count: number; draft_requirement_count: number;
  active_required_kg: string; active_accepted_offer_kg: string;
  active_pending_offer_kg: string; active_remaining_offer_kg: string;
  active_offer_coverage_pct: number; recent_requirements: RequestPreview[];
};
type ProgrammeResponse = {
  items: Programme[]; scope: string;
  pagination: { offset: number; limit: number; total: number; has_more: boolean };
  coverage_basis: string;
};
type BuyerResponse = { items: Array<{ id: string; name: string }> };
type AvailableResponse = { items: RequestPreview[] };

const PAGE_SIZE = 20;
const kg = (value: string | number) => `${Number(value).toLocaleString('en-JM', { maximumFractionDigits: 3 })} kg`;
const human = (value: string) => value.replace(/_/g, ' ');
const controlClass = 'min-h-11 w-full rounded-md border border-white/15 bg-background px-3 text-sm text-foreground';
const writes = new Set(['BUYER', 'PLATFORM_ADMIN', 'ORGANIZATION_ADMIN', 'PROCUREMENT_MANAGER']);

function Stat({ label, value, footnote }: { label: string; value: string; footnote?: string }) {
  return <div className="operational-panel p-4 sm:p-5"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>{footnote && <p className="mt-2 text-xs text-muted-foreground">{footnote}</p>}</div>;
}

export function ProgrammesWorkspace() {
  const identity = useIdentity();
  const queryClient = useQueryClient();
  const role = identity.data?.active_role;
  const allowed = Boolean(role && role !== 'FARMER');
  const isBuyer = role === 'BUYER';
  const editable = Boolean(role && writes.has(role));
  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [programmeName, setProgrammeName] = useState('');
  const [commodity, setCommodity] = useState('GINGER');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [createBuyerId, setCreateBuyerId] = useState('');
  const [selectedProgrammeId, setSelectedProgrammeId] = useState<string | null>(null);
  const [selectedRequirementId, setSelectedRequirementId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const programmes = useQuery({
    queryKey: ['marketplace', 'programmes', identity.data?.active_organization_id, role, statusFilter, page],
    queryFn: () => {
      const qs = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
      if (statusFilter) qs.set('status_filter', statusFilter);
      return apiFetch<ProgrammeResponse>(`/marketplace/programmes?${qs}`);
    },
    enabled: allowed,
    retry: false,
    staleTime: 10_000,
  });

  const buyers = useQuery({
    queryKey: ['marketplace', 'programme-buyers', identity.data?.active_organization_id, role],
    queryFn: () => apiFetch<BuyerResponse>('/marketplace/programmes/buyers'),
    enabled: allowed && editable,
    retry: false,
  });
  const selected = programmes.data?.items.find(item => item.id === selectedProgrammeId);
  const available = useQuery({
    queryKey: ['marketplace', 'programme-unassigned', selected?.buyer_id, identity.data?.active_organization_id],
    queryFn: () => apiFetch<AvailableResponse>(`/marketplace/programmes/available-requirements?buyer_id=${encodeURIComponent(selected!.buyer_id)}`),
    enabled: editable && Boolean(selected),
    retry: false,
  });

  async function mutate(action: () => Promise<unknown>, successMessage: string) {
    setBusy(true); setError(''); setNotice('');
    try {
      await action();
      setNotice(successMessage);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['marketplace', 'programmes'] }),
        queryClient.invalidateQueries({ queryKey: ['marketplace', 'programme-unassigned'] }),
        queryClient.invalidateQueries({ queryKey: ['marketplace', 'demand-ledger'] }),
        queryClient.invalidateQueries({ queryKey: ['marketplace', 'command-center'] }),
      ]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      name: programmeName.trim(), commodity_scope: commodity || null,
      start_date: startDate, end_date: endDate,
      ...(!isBuyer ? { buyer_id: createBuyerId } : {}),
    };
    void mutate(async () => {
      await apiFetch('/marketplace/programmes', { method: 'POST', body: JSON.stringify(payload) });
      setProgrammeName(''); setShowCreate(false); setPage(0);
    }, 'Programme created. Link existing requirements to begin tracking coverage.');
  }

  function attach(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !selectedRequirementId) return;
    void mutate(async () => {
      await apiFetch(`/marketplace/programmes/${selected.id}/requirements/${selectedRequirementId}`, { method: 'POST' });
      setSelectedRequirementId('');
    }, 'Requirement linked to programme. Active request totals now include accepted farmer offers.');
  }

  const summary = programmes.data?.items.reduce((acc, p) => ({
    active: acc.active + p.active_requirement_count,
    requested: acc.requested + Number(p.active_required_kg),
    accepted: acc.accepted + Number(p.active_accepted_offer_kg),
    remaining: acc.remaining + Number(p.active_remaining_offer_kg),
  }), { active: 0, requested: 0, accepted: 0, remaining: 0 });

  return <AppShell programme="Institutional procurement · Programmes"><main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="flex flex-wrap items-end justify-between gap-4"><div>
      <p className="section-eyebrow">KoroFarm Operations</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Programmes</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Organize institutional buyer relationships, link procurement requirements, and measure accepted-offer commitments.</p>
    </div><div className="flex flex-wrap gap-2">
      {editable && <button type="button" onClick={() => setShowCreate(v => !v)} className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground"><Plus className="h-4 w-4" />New programme</button>}
      <button type="button" disabled={!allowed || programmes.isFetching} onClick={() => void programmes.refetch()} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/20 px-4 text-sm disabled:opacity-50"><RefreshCw className="h-4 w-4" />Refresh</button>
    </div></header>

    {identity.isLoading && <p role="status" className="operational-panel p-6">Verifying your organization and role…</p>}
    {identity.isError && <div role="alert" className="operational-panel p-6">Account access unavailable: {identity.error.message}</div>}
    {role === 'FARMER' && <section className="operational-panel p-6"><h2 className="font-semibold">Farmer opportunities</h2><p className="mt-2 text-sm text-muted-foreground">Programmes are managed by buyers and authorized staff. Farmers can participate through published buyer requests.</p><Link className="mt-3 inline-block text-primary underline" href="/demand/demo-orders">View buyer opportunities</Link></section>}
    {error && <div role="alert" className="operational-panel border border-destructive/30 p-4 text-sm text-destructive">{error}</div>}
    {notice && <div role="status" className="operational-panel border border-primary/30 p-4 text-sm text-primary">{notice}</div>}

    {allowed && showCreate && editable && <form onSubmit={create} className="operational-panel space-y-4 p-5"><h2 className="text-lg font-semibold">Create a procurement programme</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {!isBuyer && <label className="grid gap-1 text-sm">Buyer<select className={controlClass} required value={createBuyerId} onChange={e => setCreateBuyerId(e.target.value)}><option value="">Select a buyer</option>{buyers.data?.items.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
        <label className="grid gap-1 text-sm">Programme name<input required minLength={3} maxLength={200} className={controlClass} value={programmeName} onChange={e => setProgrammeName(e.target.value)} placeholder="e.g. Hotel Ginger Supply 2027" /></label>
        <label className="grid gap-1 text-sm">Commodity scope<select className={controlClass} value={commodity} onChange={e => setCommodity(e.target.value)}><option value="GINGER">Ginger</option><option value="">General procurement</option></select></label>
        <label className="grid gap-1 text-sm">Start date<input className={controlClass} required type="date" value={startDate} onChange={e => setStartDate(e.target.value)} /></label>
        <label className="grid gap-1 text-sm">End date<input className={controlClass} required type="date" min={startDate} value={endDate} onChange={e => setEndDate(e.target.value)} /></label>
      </div><button disabled={busy || (!isBuyer && !createBuyerId)} type="submit" className="min-h-11 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground disabled:opacity-50">{busy ? 'Saving…' : 'Create programme'}</button>
      {buyers.isError && <p role="alert" className="text-sm text-destructive">Could not load authorized buyers: {buyers.error.message}</p>}
    </form>}

    {allowed && <><section className="operational-panel flex flex-wrap items-center gap-3 p-4" aria-label="Programme filters"><label className="grid min-w-[190px] gap-1 text-xs text-muted-foreground">Status<select className={controlClass} value={statusFilter} onChange={e => {setStatusFilter(e.target.value);setPage(0);setSelectedProgrammeId(null);}}><option value="">All statuses</option><option value="ACTIVE">Active</option><option value="PAUSED">Paused</option><option value="COMPLETED">Completed</option></select></label><p className="ml-auto text-xs text-muted-foreground">{programmes.data?.pagination.total ?? '—'} matching programmes</p></section>
      {programmes.isLoading && <p role="status" className="operational-panel p-6">Loading authorized programmes…</p>}
      {programmes.isError && <section role="alert" className="operational-panel flex gap-3 p-6"><AlertTriangle className="h-5 w-5 shrink-0 text-warning" /><div><h2 className="font-semibold">Programmes unavailable</h2><p className="mt-2 text-sm text-muted-foreground">{programmes.error.message}</p><p className="mt-2 text-xs text-muted-foreground">Check /marketplace/programmes, the backend .env configuration, and your active membership. No programme data has been substituted.</p></div></section>}
      {programmes.data && <>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Visible programmes summary"><Stat label="Active requirements" value={String(summary?.active ?? 0)} footnote="Visible programmes on this page"/><Stat label="Required" value={kg(summary?.requested ?? 0)} /><Stat label="Accepted offers" value={kg(summary?.accepted ?? 0)} footnote="Not delivered quantity" /><Stat label="Remaining demand" value={kg(summary?.remaining ?? 0)} /></section>
        {!programmes.data.items.length && <div className="operational-panel py-12 text-center"><Building2 className="mx-auto h-8 w-8 text-muted-foreground"/><h2 className="mt-3 font-semibold">No programmes found</h2><p className="mt-2 text-sm text-muted-foreground">Create a programme for an institutional buyer or change the status filter.</p></div>}
        <div className="space-y-4">{programmes.data.items.map(p => {
          const expanded = selectedProgrammeId === p.id;
          const coverage = Math.min(100,Math.max(0,p.active_offer_coverage_pct));
          return <article className="operational-panel p-5 sm:p-6" key={p.id}>
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="section-eyebrow">{p.buyer_name}</p><h2 className="mt-2 text-xl font-semibold">{p.name}</h2><p className="mt-2 text-sm text-muted-foreground">{p.commodity_scope || 'General'} · {p.start_date} to {p.end_date}</p></div><span className="rounded-md border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-medium">{human(p.status)}</span></div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Stat label="Active requests" value={String(p.active_requirement_count)} footnote={`${p.requirement_count} total linked`} /><Stat label="Required" value={kg(p.active_required_kg)} /><Stat label="Accepted offers" value={kg(p.active_accepted_offer_kg)} /><Stat label="Outstanding" value={kg(p.active_remaining_offer_kg)} /></div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10" role="meter" aria-label={`Accepted offer coverage of ${p.name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={coverage}><div className="h-full rounded-full bg-primary" style={{width:`${coverage}%`}} /></div><p className="mt-2 text-xs text-muted-foreground">{coverage.toFixed(1)}% of active demand backed by accepted farmer offers · Pending: {kg(p.active_pending_offer_kg)} · {p.draft_requirement_count} draft requests excluded from active totals</p>
            <div className="mt-5 flex flex-wrap gap-4"><button type="button" onClick={() => {setSelectedProgrammeId(expanded ? null : p.id);setSelectedRequirementId('');}} className="inline-flex min-h-10 items-center gap-2 text-sm font-medium text-primary underline-offset-4 hover:underline"><ClipboardList className="h-4 w-4" />{expanded ? 'Close details' : 'View linked requests'}</button><Link href="/demand" className="inline-flex min-h-10 items-center gap-2 text-sm text-primary hover:underline">Demand ledger <ArrowRight className="h-4 w-4"/></Link></div>
            {expanded && <div className="mt-4 space-y-4 border-t border-white/10 pt-5"><h3 className="font-semibold">Recently linked requirements</h3>{!p.recent_requirements.length && <p className="text-sm text-muted-foreground">No requirements linked. Use the form below to associate an existing buyer request.</p>}
              {p.recent_requirements.map(r => <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/10 p-3 text-sm"><div><p className="font-medium">{human(r.crop)} · Grade {r.grade} · {r.lifecycle_status}</p><p className="mt-1 text-xs text-muted-foreground">{r.delivery_window_start} to {r.delivery_window_end} · {kg(r.required_quantity_kg)} required</p></div><span className="text-xs text-muted-foreground">{kg(r.accepted_offer_quantity_kg ?? '0')} accepted</span></div>)}
              {p.requirement_count > p.recent_requirements.length && <p className="text-xs text-muted-foreground">Showing the five most recent requirements; the figures above include all linked requests.</p>}
              {editable && p.status === 'ACTIVE' && <form onSubmit={attach} className="space-y-2 rounded-md border border-white/10 p-4"><label className="grid gap-1 text-sm">Link an unassigned request<select className={controlClass} value={selectedRequirementId} onChange={e => setSelectedRequirementId(e.target.value)} required><option value="">Select a buyer requirement</option>{available.data?.items.map(r => <option key={r.id} value={r.id}>{human(r.crop)} Grade {r.grade} · {kg(r.required_quantity_kg)} · {r.lifecycle_status} · {r.delivery_window_start}</option>)}</select></label><button type="submit" disabled={busy || !selectedRequirementId} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/20 px-4 text-sm disabled:opacity-50"><Link2 className="h-4 w-4" />Link requirement</button>{available.isLoading && <p className="text-xs text-muted-foreground">Loading unassigned buyer requests…</p>}{available.isError && <p role="alert" className="text-xs text-destructive">{available.error.message}</p>}</form>}
              {editable && <div className="flex flex-wrap gap-2"><button type="button" disabled={busy || p.status === 'ACTIVE'} onClick={() => void mutate(() => apiFetch(`/marketplace/programmes/${p.id}`,{method:'PATCH', body:JSON.stringify({status:'ACTIVE'})}), 'Programme activated.')} className="rounded border border-white/20 px-3 py-2 text-xs disabled:opacity-40">Activate</button><button type="button" disabled={busy || p.status === 'PAUSED'} onClick={() => void mutate(() => apiFetch(`/marketplace/programmes/${p.id}`,{method:'PATCH', body:JSON.stringify({status:'PAUSED'})}), 'Programme paused.')} className="rounded border border-white/20 px-3 py-2 text-xs disabled:opacity-40">Pause</button><button type="button" disabled={busy || p.status === 'COMPLETED'} onClick={() => void mutate(() => apiFetch(`/marketplace/programmes/${p.id}`,{method:'PATCH', body:JSON.stringify({status:'COMPLETED'})}), 'Programme marked completed (requirements are unchanged).')} className="rounded border border-white/20 px-3 py-2 text-xs disabled:opacity-40">Complete</button></div>}
            </div>}
          </article>;
        })}</div>
        <div className="flex flex-wrap items-center justify-between gap-4"><p className="text-xs text-muted-foreground">Showing {programmes.data.items.length ? programmes.data.pagination.offset + 1 : 0}–{programmes.data.pagination.offset + programmes.data.items.length} of {programmes.data.pagination.total}. Top metrics reflect this page, not the full portfolio.</p><div className="flex gap-2"><button type="button" className="rounded border border-white/20 px-4 py-2 text-sm disabled:opacity-40" disabled={page === 0 || programmes.isFetching} onClick={() => {setPage(v => Math.max(0,v-1));setSelectedProgrammeId(null);}}>Previous</button><button type="button" className="rounded border border-white/20 px-4 py-2 text-sm disabled:opacity-40" disabled={!programmes.data.pagination.has_more || programmes.isFetching} onClick={() => {setPage(v => v+1);setSelectedProgrammeId(null);}}>Next</button></div></div>
        <p className="text-xs leading-5 text-muted-foreground">{programmes.data.coverage_basis} A programme contains buyer requirements, and those requirements link to accepted farmer offers. No receipts, shipments, or delivery confirmations are inferred.</p>
      </>}
    </>}
  </main></AppShell>;
}
