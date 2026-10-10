import { Activity, ArrowRight, Database, ShieldCheck } from 'lucide-react';
import { Header } from '@/components/Header';
import { SupplyOverview } from '@/components/SupplyOverview';
import { RecoveryPanel } from '@/components/RecoveryPanel';
import { AllocationTable } from '@/components/AllocationTable';
import { EconomicsPanel } from '@/components/EconomicsPanel';
import { FulfilmentPanel } from '@/components/FulfilmentPanel';
import Landing from '@/components/Landing';
import { ginger500Allocations, ginger500Requirement } from '@/domain/fixtures/ginger-500kg';
import { selectCoverage, selectRequirementHealth } from '@/domain/selectors';
import type { RecoveryStep, SupplyMetrics } from '@/domain/types';

export default function Index() {
  const coverage = selectCoverage(ginger500Requirement.requiredKg, ginger500Allocations);
  const supplyMetrics: SupplyMetrics = { requiredKg: coverage.requiredKg, committedKg: coverage.committedKg, standbyKg: coverage.standbyKg, shortfallKg: coverage.uncoveredKg, committedFarmerCount: ginger500Allocations.filter(a => a.state === 'COMMITTED' || a.state === 'STANDBY_ACTIVATED').length, standbyFarmerCount: ginger500Allocations.filter(a => a.state === 'STANDBY').length, health: selectRequirementHealth(coverage.requiredKg, coverage.committedKg) };
  const recoverySteps: RecoveryStep[] = [
    { label: 'Disruption detected', detail: 'Nadine Ellis reported an 80 kg shortfall', state: 'complete' },
    { label: 'Requirement marked at risk', detail: '420 kg remained against the 500 kg requirement', state: 'complete' },
    { label: 'Standby capacity activated', detail: '80 kg activated from Peter Wallace reserve lot', state: 'complete' },
    { label: 'Coverage restored', detail: '500 kg committed coverage restored', state: 'complete' },
  ];
  return <div className="min-h-screen bg-background">
    <Landing />
    <Header />
    <main className="mx-auto max-w-[1500px] px-5 py-8 lg:px-10">
      <section className="mb-8 flex flex-col justify-between gap-5 border-b border-border/70 pb-8 md:flex-row md:items-end">
        <div className="max-w-2xl"><p className="mb-3 font-mono text-xs uppercase tracking-[0.2em] text-primary">Jamaica / institutional procurement</p><h2 className="text-4xl font-semibold tracking-tight md:text-5xl">One dependable supply programme.</h2><p className="mt-4 max-w-xl text-base leading-7 text-muted-foreground">The assurance layer turns fragmented smallholder production into a committed hotel supply SLA, then protects it when reality changes.</p></div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><span className="h-2 w-2 animate-pulse rounded-full bg-success" />Last verified today at 09:42</div>
      </section>
      <SupplyOverview metrics={supplyMetrics} allocations={ginger500Allocations} />
      <section className="mt-6 grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <RecoveryPanel steps={recoverySteps} />
        <div className="space-y-6"><EconomicsPanel /><FulfilmentPanel /></div>
      </section>
      <section className="mt-6"><AllocationTable allocations={ginger500Allocations} /></section>
      <section className="mt-8 grid gap-4 border-t border-border/70 pt-6 text-xs text-muted-foreground md:grid-cols-3">
        <div className="flex gap-3"><ShieldCheck className="h-4 w-4 shrink-0 text-success" /><p><span className="font-medium text-foreground">Verified state.</span> Unknown fulfilment evidence remains unknown until a receipt or inspection is recorded.</p></div>
        <div className="flex gap-3"><Database className="h-4 w-4 shrink-0 text-primary" /><p><span className="font-medium text-foreground">Deterministic tools.</span> Quantities, risk, allocation, and landed cost come from structured system state.</p></div>
        <div className="flex gap-3"><Activity className="h-4 w-4 shrink-0 text-warning" /><p><span className="font-medium text-foreground">Next checkpoint.</span> Receive and grade every farmer sublot at the collection node.</p></div>
      </section>
      <div className="mt-8 flex items-center gap-2 border-t border-border/70 pt-5 text-xs text-muted-foreground"><span>{ginger500Requirement.id}</span><ArrowRight className="h-3 w-3" /><span>{ginger500Requirement.crop} / {ginger500Requirement.grade}</span><ArrowRight className="h-3 w-3" /><span>{ginger500Requirement.destination}</span></div>
    </main>
  </div>;
}
