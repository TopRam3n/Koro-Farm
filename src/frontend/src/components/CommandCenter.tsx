'use client';

import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, BarChart3, ClipboardList, Clock3, RefreshCw, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { useIdentity } from '@/hooks/useIdentity';
import { apiFetch } from '@/lib/api';

type RequestSnapshot = {
  id: string;
  buyer_name: string;
  crop: string;
  grade: string;
  lifecycle_status: string;
  delivery_window_start: string;
  delivery_window_end: string;
  required_kg: string;
  accepted_offer_kg: string;
  pending_offer_kg: string;
  remaining_offer_kg: string;
  coverage_pct: number;
  coverage_status: 'COVERED' | 'PARTIALLY_COVERED' | 'UNFILLED';
};
type Offer = {
  id: string;
  requirement_id: string;
  buyer_name: string;
  farmer_name: string;
  crop: string;
  quantity_kg: string;
  status: string;
  created_at: string | null;
};
type Summary = {
  scope: 'buyer' | 'organization_staff';
  as_of: string;
  coverage_basis: string;
  totals: {
    all_requests: number;
    active_requests: number;
    draft_requests: number;
    covered_active_requests: number;
    partially_covered_active_requests: number;
    unfilled_active_requests: number;
    requests_needing_supply: number;
    requested_kg: string;
    accepted_offer_kg: string;
    pending_offer_kg: string;
    remaining_offer_kg: string;
    coverage_pct: number | null;
  };
  attention: RequestSnapshot[];
  recent_requests: RequestSnapshot[];
  recent_offers: Offer[];
  by_crop: Array<{ crop: string; requests: number; required_kg: string; accepted_offer_kg: string }>;
};

const kilograms = (value: string | number) => `${Number(value).toLocaleString('en-JM', { maximumFractionDigits: 3 })} kg`;
const human = (value: string) => value.replace(/_/g, ' ');
const safeDate = (value: string) => value ? value.slice(0, 10) : 'Unavailable';
const percent = (value: number | null) => value === null ? '—' : `${value.toFixed(1)}%`;
const tone = (status: string) => status === 'COVERED' || status === 'ACCEPTED'
  ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
  : status === 'PARTIALLY_COVERED' || status === 'PENDING'
    ? 'border-amber-500/25 bg-amber-500/10 text-amber-300'
    : 'border-white/15 bg-white/[0.04] text-slate-300';

export function CommandCenter() {
  const identity = useIdentity();
  const role = identity.data?.active_role;
  const isFarmer = role === 'FARMER';
  const query = useQuery({
    queryKey: ['marketplace-command-center', identity.data?.active_organization_id, role, identity.data?.active_buyer_id],
    queryFn: () => apiFetch<Summary>('/marketplace/command-center/summary'),
    enabled: Boolean(role) && !isFarmer,
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });

  if (identity.isLoading) return <Centered title="Command Center" message="Checking your workspace access…" />;
  if (identity.isError || !role) return <Centered title="Account access unavailable" message={identity.error?.message ?? 'An active organization membership is required.'} />;
  if (isFarmer) return <AppShell programme="Farmer workspace"><main className="mx-auto max-w-4xl space-y-4 p-8"><h1 className="text-3xl font-semibold">Your farm workspace</h1><p className="text-sm text-muted-foreground">Procurement portfolio summaries are available to buyers and authorized operations staff. Use your farm workspace to manage harvests and buyer opportunities.</p><Link className="text-primary underline" href="/farmer">Open Harvest &amp; Quality</Link></main></AppShell>;

  const data = query.data;
  const t = data?.totals;
  const requestsLink = data?.scope === 'buyer' ? '/demand/demo-orders' : '/demand';
  return <AppShell programme={data?.scope === 'buyer' ? 'Buyer procurement · Command Center' : 'Organization procurement · Command Center'}>
    <main className="mx-auto max-w-[1440px] space-y-7 px-4 py-7 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="section-eyebrow">KoroFarm · Operations overview</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Command Center</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">See institutional demand, accepted farmer commitments, and outstanding supply across your permitted portfolio.</p></div>
        <div className="flex flex-wrap items-center gap-2"><Link href="/demand" className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/20 px-4 text-sm font-semibold hover:bg-white/[0.04]">Explore Demand <ArrowRight className="h-4 w-4" /></Link><button type="button" disabled={query.isFetching} onClick={() => void query.refetch()} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/20 px-4 text-sm font-semibold hover:bg-white/[0.04] disabled:opacity-50"><RefreshCw className="h-4 w-4" />Refresh</button></div>
      </header>
      {query.isLoading && <div role="status" className="operational-panel p-8 text-sm text-muted-foreground">Loading your procurement portfolio…</div>}
      {query.isError && <section role="alert" className="operational-panel space-y-3 p-6"><div className="flex items-center gap-2 font-semibold text-warning"><AlertTriangle className="h-5 w-5" />Command Center unavailable</div><p className="text-sm text-muted-foreground">{query.error.message}</p><p className="text-xs text-muted-foreground">Confirm the Phase 2 router is installed, the backend is running, and your account has an active buyer or staff membership. No figures are substituted.</p><button onClick={() => void query.refetch()} type="button" className="rounded border border-white/20 px-3 py-2 text-sm">Retry</button></section>}
      {t && data && <>
        <div className="flex flex-wrap justify-between gap-3 text-xs text-muted-foreground"><span>{data.scope === 'buyer' ? 'Your buyer portfolio' : 'Your organization portfolio'} · Accepted marketplace offers only</span><span>Snapshot {new Date(data.as_of).toLocaleString('en-JM')} · refreshes every 30 seconds</span></div>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Portfolio indicators">
          <Metric label="Active requests" value={String(t.active_requests)} note={`${t.all_requests} total · ${t.draft_requests} drafts`} icon="requests" />
          <Metric label="Accepted coverage" value={percent(t.coverage_pct)} note={`${kilograms(t.accepted_offer_kg)} accepted`} icon="coverage" />
          <Metric label="Requested supply" value={kilograms(t.requested_kg)} note="Open procurement requirements" icon="requests" />
          <Metric label="Remaining demand" value={kilograms(t.remaining_offer_kg)} note={`${t.requests_needing_supply} requests need supply`} icon="attention" />
        </section>
        <section className="operational-panel p-5 sm:p-6" aria-labelledby="coverage-title">
          <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 id="coverage-title" className="text-xl font-semibold">Portfolio commitment coverage</h2><p className="mt-1 text-sm text-muted-foreground">Accepted offers are reserved commitments, not received, inspected, or delivered produce.</p></div><span className="text-sm font-semibold tabular-nums">{percent(t.coverage_pct)}</span></div>
          <div className="mt-5 h-3 overflow-hidden rounded-full bg-white/10" role="meter" aria-label="Accepted commitment coverage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={t.coverage_pct ?? 0}><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.max(0, Math.min(100, t.coverage_pct ?? 0))}%` }} /></div>
          <div className="mt-5 grid gap-4 sm:grid-cols-4"><Mini label="Accepted offers" value={kilograms(t.accepted_offer_kg)} /><Mini label="Pending offers" value={kilograms(t.pending_offer_kg)} /><Mini label="Covered requests" value={String(t.covered_active_requests)} /><Mini label="Partially covered" value={String(t.partially_covered_active_requests)} /></div>
        </section>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.8fr)]">
          <section className="operational-panel min-w-0 p-5 sm:p-6" aria-labelledby="attention-title">
            <div className="flex items-center justify-between gap-3"><div><p className="section-eyebrow">Procurement gaps</p><h2 id="attention-title" className="mt-2 text-xl font-semibold">Needs supply attention</h2></div><span className="rounded-md border border-white/15 px-3 py-1 text-xs text-muted-foreground">{t.requests_needing_supply} open</span></div>
            {!data.attention.length ? <Empty message={t.active_requests ? 'All active requirements have accepted offer coverage.' : 'No active requirements to assess yet.'} /> : <div className="mt-4 divide-y divide-white/10">{data.attention.map(r => <article key={r.id} className="grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"><div><div className="flex flex-wrap items-center gap-2"><h3 className="text-sm font-semibold">Grade {r.grade} {human(r.crop)}</h3><span className={`rounded border px-2 py-0.5 text-[10px] ${tone(r.coverage_status)}`}>{human(r.coverage_status)}</span></div><p className="mt-1 text-xs text-muted-foreground">{r.buyer_name} · Delivery {safeDate(r.delivery_window_start)}–{safeDate(r.delivery_window_end)}</p><p className="mt-1 text-xs text-muted-foreground">{kilograms(r.accepted_offer_kg)} accepted / {kilograms(r.required_kg)} requested</p></div><div className="sm:text-right"><p className="text-lg font-semibold text-amber-300 tabular-nums">{kilograms(r.remaining_offer_kg)}</p><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Supply still needed</p></div></article>)}</div>}
            {t.requests_needing_supply > data.attention.length && <p className="mt-2 text-xs text-muted-foreground">Showing the {data.attention.length} earliest delivery windows. Open Demand for all requirements.</p>}
            <Link href={requestsLink} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline">Review procurement requests <ArrowRight className="h-4 w-4" /></Link>
          </section>
          <section className="operational-panel min-w-0 p-5 sm:p-6" aria-labelledby="crop-title"><div className="flex items-center gap-2"><BarChart3 className="h-5 w-5 text-primary" /><h2 id="crop-title" className="text-xl font-semibold">Demand by crop</h2></div><p className="mt-2 text-xs text-muted-foreground">Active requirements only; coverage based on accepted offers.</p>
            {!data.by_crop.length ? <Empty message="Crop breakdown will appear once requests become active." /> : <div className="mt-6 space-y-6">{data.by_crop.map(c => { const req = Number(c.required_kg); const cov = req > 0 ? Math.min(100, Number(c.accepted_offer_kg) / req * 100) : 0; return <div key={c.crop}><div className="flex items-center justify-between gap-3 text-sm"><span className="font-medium">{human(c.crop)}</span><span className="text-muted-foreground">{c.requests} requests</span></div><div className="mt-1 flex justify-between gap-3 text-xs text-muted-foreground"><span>{kilograms(c.accepted_offer_kg)} accepted</span><span>{kilograms(c.required_kg)} requested</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-primary" style={{width:`${Math.max(0, cov)}%`}} /></div></div>;})}</div>}
          </section>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="operational-panel min-w-0 p-5 sm:p-6" aria-labelledby="requests-title"><div className="flex items-center gap-2"><ClipboardList className="h-5 w-5 text-primary"/><h2 id="requests-title" className="text-lg font-semibold">Recent active requests</h2></div>
            {!data.recent_requests.length ? <Empty message="No active procurement requests are recorded."/> : <ul className="mt-4 divide-y divide-white/10">{data.recent_requests.map(r=><li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="text-sm font-semibold">{human(r.crop)} · Grade {r.grade}</p><p className="mt-1 text-xs text-muted-foreground">{r.buyer_name} · {safeDate(r.delivery_window_start)}</p></div><div className="text-right"><p className="text-sm font-semibold">{percent(r.coverage_pct)}</p><p className="text-xs text-muted-foreground">offer coverage</p></div></li>)}</ul>}
          </section>
          <section className="operational-panel min-w-0 p-5 sm:p-6" aria-labelledby="offers-title"><div className="flex items-center gap-2"><Clock3 className="h-5 w-5 text-primary"/><h2 id="offers-title" className="text-lg font-semibold">Recent farmer offers</h2></div>
            {!data.recent_offers.length ? <Empty message="No farmer offers are recorded for this portfolio."/> : <ul className="mt-4 divide-y divide-white/10">{data.recent_offers.map(o=><li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-3"><div><p className="text-sm font-semibold">{o.farmer_name} · {human(o.crop)}</p><p className="mt-1 text-xs text-muted-foreground">{kilograms(o.quantity_kg)} · {o.created_at ? safeDate(o.created_at) : 'Date unavailable'}</p></div><span className={`rounded border px-2 py-1 text-[10px] ${tone(o.status)}`}>{human(o.status)}</span></li>)}</ul>}
            <p className="mt-3 text-xs leading-5 text-muted-foreground">This is an offer-status feed, not a verified audit history. Acceptance dates and physical delivery are not inferred.</p>
          </section>
        </div>
        <p className="flex gap-2 text-xs leading-5 text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{data.coverage_basis}. The legacy finalized supply-plan commitments are deliberately excluded to avoid double-counting. Physical fulfilment and modeled supply risk require separate evidence.</p>
      </>}
    </main>
  </AppShell>;
}

function Metric({label,value,note,icon}:{label:string;value:string;note:string;icon:'requests'|'coverage'|'attention'}) {
  const Icon = icon === 'attention' ? AlertTriangle : icon === 'coverage' ? ShieldCheck : ClipboardList;
  return <div className="operational-panel p-5"><div className="flex justify-between gap-2"><p className="text-xs font-semibold text-muted-foreground">{label}</p><Icon className="h-4 w-4 text-primary" /></div><p className="mt-3 text-2xl font-semibold tabular-nums">{value}</p><p className="mt-2 text-xs text-muted-foreground">{note}</p></div>;
}
function Mini({label,value}:{label:string;value:string}) {return <div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-base font-semibold tabular-nums">{value}</p></div>;}
function Empty({message}:{message:string}) {return <p className="mt-4 rounded-md border border-dashed border-white/15 p-5 text-sm text-muted-foreground">{message}</p>;}
function Centered({title,message}:{title:string;message:string}) {return <main className="grid min-h-[60vh] place-items-center px-5"><div className="operational-panel max-w-md p-8"><h1 className="text-xl font-semibold">{title}</h1><p className="mt-3 text-sm text-muted-foreground">{message}</p></div></main>;}
