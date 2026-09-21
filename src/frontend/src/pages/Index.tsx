'use client';

import { Activity, ArrowDown, Check, CircleAlert, FileCheck2, GitBranch, MapPin, Package, ShieldCheck } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { SupplyOverview } from '@/components/SupplyOverview';
import { RecoveryPanel } from '@/components/RecoveryPanel';
import { AllocationTable } from '@/components/AllocationTable';
import { EconomicsPanel } from '@/components/EconomicsPanel';
import { FulfilmentPanel } from '@/components/FulfilmentPanel';
import { DemoControls } from '@/components/DemoControls';
import { PanelBoundary } from '@/components/PanelBoundary';
import { StatusBadge } from '@/components/StatusBadge';
import { useAssurance, useEvents, useFulfilment } from '@/hooks/useAssurance';
import type { Allocation, RecoveryStep, SupplyMetrics } from '@/lib/mockdata';

const requirementId = process.env.NEXT_PUBLIC_REQUIREMENT_ID ?? (process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? '00000000-0000-0000-0000-000000000500' : '');

export default function Index() {
  const assurance = useAssurance(requirementId);
  const fulfilment = useFulfilment(requirementId);
  const events = useEvents(requirementId);

  if (!requirementId) return <SetupState />;
  if (assurance.isLoading) return <LoadingState />;
  if (assurance.error || !assurance.data) return <ErrorState message={assurance.error?.message} />;

  const data = assurance.data;
  const metrics: SupplyMetrics = {
    requiredKg: Number(data.requirement.required_quantity_kg), committedKg: Number(data.committed_quantity_kg), standbyKg: Number(data.standby_quantity_kg), shortfallKg: Number(data.unfilled_quantity_kg), committedFarmerCount: data.committed_farmer_count, standbyFarmerCount: data.standby_farmer_count, health: data.supply_health as SupplyMetrics['health'],
  };
  const allocations: Allocation[] = data.allocations.map((item) => ({ id: item.id, farmer: item.farmer_name, farmerId: item.farmer_id, parish: item.parish, lotId: item.production_lot_id, quantityKg: Number(item.quantity_kg), role: item.role, status: item.status as Allocation['status'] }));
  const recoverySteps: RecoveryStep[] = data.latest_recovery ? [
    { label: 'Disruption detected', detail: `${data.latest_disruption?.lost_kg ?? 'Unknown'} kg committed supply lost`, state: 'complete' },
    { label: 'Allocation lost', detail: 'The affected production allocation was removed from committed coverage', state: 'complete' },
    { label: 'Requirement marked at risk', detail: `${data.latest_recovery.remaining_shortfall_kg} kg shortfall recorded`, state: 'complete' },
    { label: data.latest_recovery.status === 'completed' ? 'Authorized standby activated' : 'Recovery ready', detail: `${data.latest_recovery.standby_activated_kg} kg standby activated`, state: data.latest_recovery.status === 'completed' ? 'complete' : 'active' },
    ...(data.latest_recovery.status === 'completed' ? [{ label: 'Committed coverage restored', detail: 'Planning coverage restored. Physical delivery not yet claimed.', state: 'complete' as const }] : []),
  ] : [];
  const programme = `${data.requirement.buyer_name} · ${data.requirement.crop}`;
  const deliveryWindow = `${data.requirement.delivery_window_start} – ${data.requirement.delivery_window_end}`;
  const parishTotals = allocations.reduce<Record<string, number>>((totals, item) => { if (item.role === 'COMMITTED' && item.status !== 'LOST') totals[item.parish] = (totals[item.parish] ?? 0) + item.quantityKg; return totals; }, {});
  const committedTotal = Object.values(parishTotals).reduce((sum, value) => sum + value, 0);

  return <AppShell programme={programme}>
    <main id="overview" className="mx-auto max-w-[1540px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <header className="mb-7 flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><p className="section-eyebrow">Supply assurance control room</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em]">Operational overview</h1><p className="mt-2 max-w-2xl text-sm text-muted-foreground">One active requirement. See what is safe, what changed, and what the network is doing next.</p></div><div className="flex items-center gap-3"><StatusBadge status={metrics.health} /><span className="text-xs text-muted-foreground">Risk: <strong className={data.risk?.label === 'HIGH' ? 'text-destructive' : data.risk?.label === 'MEDIUM' ? 'text-warning' : 'text-success'}>{data.risk?.label ?? 'UNKNOWN'}</strong></span></div></header>

      <SupplyOverview metrics={metrics} allocations={allocations} requirementId={data.requirement.id} crop={data.requirement.crop} grade={data.requirement.grade} buyerName={data.requirement.buyer_name} destination={data.requirement.destination} deliveryWindow={deliveryWindow} />

      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(310px,0.65fr)]">
        <PanelBoundary name="Recovery"><RecoveryPanel steps={recoverySteps} status={data.latest_recovery?.status} /></PanelBoundary>
        <div className="space-y-6"><DemoControls requirementId={data.requirement.id} allocations={data.allocations} hasPlan={data.requirement.plan_version > 0} recoveryStatus={data.latest_recovery?.status} /><PanelBoundary name="Economics"><EconomicsPanel economics={data.economics} /></PanelBoundary></div>
      </section>

      <section id="activity" className="mt-6 operational-panel overflow-hidden"><SectionHeading eyebrow="Decision ledger" title="Agent activity" detail="Chronological evidence from the authoritative domain event stream." /><ol className="divide-y divide-white/[0.06]">{events.data?.length ? events.data.map((event, index) => <li key={event.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[110px_24px_minmax(0,1fr)_100px] sm:items-center"><time className="tabular text-[11px] text-muted-foreground">{new Date(event.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time><span className="grid h-6 w-6 place-items-center rounded-full border border-accent/25 bg-accent/10 text-accent"><Check className="h-3 w-3" /></span><div><p className="text-sm font-medium">{event.event_type.replace(/\./g, ' ')}</p><p className="mt-0.5 text-[11px] text-muted-foreground">Event {index + 1} · immutable audit record</p></div><span className="text-right text-[10px] uppercase tracking-wider text-muted-foreground">{event.actor_type}</span></li>) : <li className="px-5 py-8 text-center text-sm text-muted-foreground">Event history is unavailable; core quantities remain visible.</li>}</ol></section>

      <section id="supply" className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(310px,0.55fr)]"><PanelBoundary name="Physical fulfilment"><FulfilmentPanel summary={fulfilment.error ? null : fulfilment.data} /></PanelBoundary><section className="operational-panel p-5"><p className="section-eyebrow">Geographic exposure</p><h2 className="mt-2 text-lg font-semibold">Committed supply by parish</h2><div className="mt-5 space-y-4">{Object.entries(parishTotals).sort((a, b) => b[1] - a[1]).map(([parish, value]) => { const percent = committedTotal ? Math.round(value / committedTotal * 100) : 0; return <div key={parish}><div className="mb-1.5 flex justify-between text-xs"><span>{parish}</span><span className="tabular text-muted-foreground">{value} kg · {percent}%</span></div><div className="h-1.5 overflow-hidden rounded-sm bg-white/[0.06]"><div className="h-full bg-accent/75" style={{ width: `${percent}%` }} /></div></div>; })}</div><p className="mt-5 flex gap-2 border-t border-white/[0.07] pt-4 text-xs leading-5 text-muted-foreground"><MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />Parish distribution is shown because coordinates are not available. No farm locations have been fabricated.</p></section></section>

      <div className="mt-6"><AllocationTable allocations={allocations} /></div>

      <section className="mt-6 grid gap-6 xl:grid-cols-3">
        <section className="operational-panel p-5" aria-labelledby="trace-title"><p className="section-eyebrow">Provenance</p><h2 id="trace-title" className="mt-2 text-lg font-semibold">Traceability chain</h2><div className="mt-5">{['Farmer', 'Production lot', 'Allocation', 'Received sublot', 'Shipment', 'Buyer confirmation', 'Trade evidence'].map((label, index, arr) => <div key={label} className="flex flex-col items-start"><div className="flex items-center gap-3"><span className={`grid h-7 w-7 place-items-center rounded-md border ${index < 3 ? 'border-success/25 bg-success/10 text-success' : 'border-white/[0.08] text-muted-foreground'}`}>{index < 3 ? <Check className="h-3.5 w-3.5" /> : <Package className="h-3.5 w-3.5" />}</span><span className={`text-sm ${index < 3 ? 'text-foreground' : 'text-muted-foreground'}`}>{label}</span></div>{index < arr.length - 1 && <ArrowDown className="ml-2.5 my-1 h-3 w-3 text-muted-foreground/50" />}</div>)}</div></section>
        <section id="compliance" className="operational-panel p-5"><p className="section-eyebrow">Compliance</p><h2 className="mt-2 text-lg font-semibold">Trade route rules</h2><div className="mt-6 border-y border-white/[0.07] py-7 text-center"><FileCheck2 className="mx-auto h-5 w-5 text-muted-foreground" /><p className="mt-3 text-sm font-medium">No verified rule on file</p><p className="mt-1 text-xs leading-5 text-muted-foreground">No authoritative compliance record was returned for this requirement. KoroFarm will not generate one.</p></div><p className="mt-4 text-xs text-muted-foreground">Route: Jamaica → {data.requirement.destination}</p></section>
        <section id="evidence" className="operational-panel p-5"><p className="section-eyebrow">Trade evidence</p><div className="mt-2 flex items-start justify-between gap-3"><h2 className="text-lg font-semibold">Fulfilment record</h2><StatusBadge status="BUILDING HISTORY" /></div><div className="mt-6 border-y border-white/[0.07] py-5"><p className="text-sm font-medium">Evidence not yet issued</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Delivery, buyer confirmation, and verified reconciliation are required.</p></div><p className="mt-4 text-xs leading-5 text-muted-foreground">Verified fulfilment records may be shared by the farmer with authorized third parties. This is not a credit decision or financing recommendation.</p></section>
      </section>

      <footer className="mt-8 flex flex-col justify-between gap-3 border-t border-white/[0.07] py-5 text-[11px] text-muted-foreground sm:flex-row"><p>Agentic Supply Assurance for Caribbean Food Systems</p><p className="flex items-center gap-2"><GitBranch className="h-3 w-3" />Planning · monitoring · recovery · verification</p></footer>
    </main>
  </AppShell>;
}

function SectionHeading({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) { return <div className="border-b border-white/[0.07] px-5 py-5"><p className="section-eyebrow">{eyebrow}</p><h2 className="mt-2 text-xl font-semibold">{title}</h2><p className="mt-1 text-xs text-muted-foreground">{detail}</p></div>; }
function LoadingState() { return <div className="grid min-h-screen place-items-center bg-background px-6"><div className="w-full max-w-4xl animate-pulse"><div className="h-3 w-40 rounded bg-white/[0.07]" /><div className="mt-4 h-9 w-72 rounded bg-white/[0.07]" /><div className="mt-8 h-80 rounded-xl border border-white/[0.06] bg-card" /><p className="sr-only">Loading authoritative supply programme</p></div></div>; }
function SetupState() { return <div className="grid min-h-screen place-items-center px-6"><div className="operational-panel max-w-lg p-8"><p className="section-eyebrow">Configuration required</p><h1 className="mt-3 text-2xl font-semibold">Choose a live supply requirement</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">Set <code className="rounded bg-muted px-1.5 py-0.5">NEXT_PUBLIC_REQUIREMENT_ID</code>, then restart the frontend. Only authoritative API state will be shown.</p></div></div>; }
function ErrorState({ message }: { message?: string }) { return <div className="grid min-h-screen place-items-center px-6"><div role="alert" className="max-w-lg rounded-xl border border-destructive/30 bg-destructive/[0.05] p-7"><CircleAlert className="h-6 w-6 text-destructive" /><h1 className="mt-4 text-xl font-semibold">Authoritative supply state is unavailable</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">{message ?? 'Unknown API error'}. No quantities have been assumed and demo data was not substituted.</p></div></div>; }
