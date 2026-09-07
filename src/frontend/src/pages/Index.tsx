'use client';

import { Activity, ArrowRight, Database, ShieldCheck } from 'lucide-react';
import { Header } from '@/components/Header';
import { SupplyOverview } from '@/components/SupplyOverview';
import { RecoveryPanel } from '@/components/RecoveryPanel';
import { AllocationTable } from '@/components/AllocationTable';
import { EconomicsPanel } from '@/components/EconomicsPanel';
import { FulfilmentPanel } from '@/components/FulfilmentPanel';
import { DemoControls } from '@/components/DemoControls';
import { PanelBoundary } from '@/components/PanelBoundary';
import { useAssurance, useEvents, useFulfilment } from '@/hooks/useAssurance';
import type { Allocation, RecoveryStep, SupplyMetrics } from '@/lib/mockdata';

const requirementId = process.env.NEXT_PUBLIC_REQUIREMENT_ID ?? (process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? '00000000-0000-0000-0000-000000000500' : '');

export default function Index() {
  const assurance = useAssurance(requirementId);
  const fulfilment = useFulfilment(requirementId);
  const events = useEvents(requirementId);

  if (!requirementId) return <div className="flex min-h-screen items-center justify-center bg-background px-6"><div className="max-w-lg rounded-lg border border-border bg-card p-8 shadow-sm"><p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Demo setup required</p><h2 className="mt-3 text-2xl font-semibold">Choose a live supply requirement</h2><p className="mt-3 leading-6 text-muted-foreground">Set <code className="rounded bg-muted px-1.5 py-0.5">NEXT_PUBLIC_REQUIREMENT_ID</code> in <code className="rounded bg-muted px-1.5 py-0.5">.env.local</code>, then restart the frontend. The dashboard will only show authoritative API state.</p></div></div>;
  if (assurance.isLoading) return <div className="flex min-h-screen items-center justify-center bg-background">Loading supply programme...</div>;
  if (assurance.error || !assurance.data) return <div className="flex min-h-screen items-center justify-center bg-background px-6"><div className="max-w-lg rounded-lg border border-destructive/30 p-6"><p className="font-semibold text-destructive">Unable to load authoritative supply state</p><p className="mt-2 text-sm text-muted-foreground">{assurance.error?.message ?? 'Unknown API error'}. No quantities have been assumed.</p></div></div>;

  const data = assurance.data;
  const metrics: SupplyMetrics = {
    requiredKg: Number(data.requirement.required_quantity_kg),
    committedKg: Number(data.committed_quantity_kg),
    standbyKg: Number(data.standby_quantity_kg),
    shortfallKg: Number(data.unfilled_quantity_kg),
    committedFarmerCount: data.committed_farmer_count,
    standbyFarmerCount: data.standby_farmer_count,
    health: data.supply_health as SupplyMetrics['health'],
  };
  const allocations: Allocation[] = data.allocations.map((item) => ({
    id: item.id,
    farmer: item.farmer_name,
    farmerId: item.farmer_id,
    parish: item.parish,
    lotId: item.production_lot_id,
    quantityKg: Number(item.quantity_kg),
    role: item.role,
    status: item.status as Allocation['status'],
  }));
  const recoverySteps: RecoveryStep[] = data.latest_recovery ? [
    { label: 'Disruption detected', detail: `${data.latest_disruption?.lost_kg ?? 'Unknown'} kg commitment lost`, state: 'complete' },
    { label: 'Requirement marked at risk', detail: `${data.latest_recovery.remaining_shortfall_kg} kg shortfall recorded`, state: 'complete' },
    { label: data.latest_recovery.status === 'completed' ? 'Standby capacity activated' : 'Recovery awaiting next bounded action', detail: `${data.latest_recovery.standby_activated_kg} kg standby activated`, state: data.latest_recovery.status === 'completed' ? 'complete' : 'active' },
    ...(data.latest_recovery.status === 'completed' ? [{ label: 'Committed coverage restored', detail: 'Planning coverage is restored; physical delivery is not yet claimed', state: 'complete' as const }] : []),
  ] : [];
  const requirement = {
    id: data.requirement.id,
    crop: data.requirement.crop,
    grade: data.requirement.grade,
    destination: data.requirement.destination,
    buyerName: data.requirement.buyer_name,
    deliveryWindow: `${data.requirement.delivery_window_start} to ${data.requirement.delivery_window_end}`,
  };

  return <div className="min-h-screen bg-background">
    <Header />
    <main className="mx-auto max-w-[1500px] px-5 py-8 lg:px-10">
      <section className="mb-8 flex flex-col justify-between gap-5 border-b border-border/70 pb-8 md:flex-row md:items-end">
        <div className="max-w-2xl"><p className="mb-3 font-mono text-xs uppercase tracking-[0.2em] text-primary">Jamaica / institutional procurement</p><h2 className="text-4xl font-semibold tracking-tight md:text-5xl">One dependable supply programme.</h2><p className="mt-4 max-w-xl text-base leading-7 text-muted-foreground">The assurance layer turns fragmented smallholder production into a committed hotel supply SLA, then protects it when reality changes.</p></div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><span className="h-2 w-2 rounded-full bg-success" />{process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? 'DEMO · deterministic offline state' : 'LIVE · backend authoritative'}</div>
      </section>
      <SupplyOverview metrics={metrics} allocations={allocations} requirementId={requirement.id} crop={requirement.crop} grade={requirement.grade} buyerName={requirement.buyerName} destination={requirement.destination} deliveryWindow={requirement.deliveryWindow} />
      <section className="mt-6 grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <PanelBoundary name="Recovery"><RecoveryPanel steps={recoverySteps} status={data.latest_recovery?.status} /></PanelBoundary>
        <div className="space-y-6"><DemoControls requirementId={requirement.id} allocations={data.allocations} hasPlan={data.requirement.plan_version > 0} recoveryStatus={data.latest_recovery?.status} /><PanelBoundary name="Economics"><EconomicsPanel economics={data.economics} /></PanelBoundary><PanelBoundary name="Physical fulfilment"><FulfilmentPanel summary={fulfilment.error ? null : fulfilment.data} /></PanelBoundary></div>
      </section>
      <section className="mt-6 rounded-lg border border-border bg-card p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Operational evidence</p><h3 className="mt-2 text-lg font-semibold">Event chronology</h3></div><span className="font-mono text-sm">Risk: {data.risk?.label ?? 'UNKNOWN'}</span></div><ol className="mt-4 grid gap-2 md:grid-cols-2">{events.data?.map((event) => <li key={event.id} className="rounded border border-border/70 p-3 text-sm"><span className="font-mono text-xs text-muted-foreground">{new Date(event.occurred_at).toLocaleTimeString()}</span><p className="mt-1 font-medium">{event.event_type.replace(/\./g, ' ')}</p></li>) ?? <li className="text-sm text-muted-foreground">Event history unavailable; core quantities remain visible.</li>}</ol></section>
      <section className="mt-6"><AllocationTable allocations={allocations} /></section>
      <section className="mt-8 grid gap-4 border-t border-border/70 pt-6 text-xs text-muted-foreground md:grid-cols-3">
        <div className="flex gap-3"><ShieldCheck className="h-4 w-4 shrink-0 text-success" /><p><span className="font-medium text-foreground">Verified state.</span> Unknown fulfilment evidence remains unknown until a receipt or inspection is recorded.</p></div>
        <div className="flex gap-3"><Database className="h-4 w-4 shrink-0 text-primary" /><p><span className="font-medium text-foreground">Deterministic tools.</span> Quantities, risk, allocation, and landed cost come from structured system state.</p></div>
        <div className="flex gap-3"><Activity className="h-4 w-4 shrink-0 text-warning" /><p><span className="font-medium text-foreground">Next checkpoint.</span> Receive and grade every farmer sublot at the collection node.</p></div>
      </section>
      <div className="mt-8 flex items-center gap-2 border-t border-border/70 pt-5 text-xs text-muted-foreground"><span>{requirement.id}</span><ArrowRight className="h-3 w-3" /><span>{requirement.crop} / {requirement.grade}</span><ArrowRight className="h-3 w-3" /><span>{requirement.destination}</span></div>
    </main>
  </div>;
}
