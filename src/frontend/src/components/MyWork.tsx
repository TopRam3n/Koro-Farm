'use client';

import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardList } from 'lucide-react';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { useAssurance, useEvents, useFulfilment } from '@/hooks/useAssurance';

const requirementId = process.env.NEXT_PUBLIC_REQUIREMENT_ID ?? (process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? '00000000-0000-0000-0000-000000000500' : '');
const role = process.env.NEXT_PUBLIC_DEMO_ROLE ?? 'SUPPLY_COORDINATOR';

export function MyWork() {
  const assurance = useAssurance(requirementId);
  const fulfilment = useFulfilment(requirementId);
  const events = useEvents(requirementId);
  if (assurance.isLoading) return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">Loading authoritative work…</div>;
  if (!assurance.data) return <div role="alert" className="grid min-h-screen place-items-center text-sm text-destructive">My Work is unavailable. No tasks were substituted.</div>;
  const data = assurance.data;
  const shortfall = Number(data.unfilled_quantity_kg);
  const accepted = Number(fulfilment.data?.accepted_kg ?? 0);
  const required = Number(data.requirement.required_quantity_kg);
  const tasks = deriveTasks(role, data.supply_health, shortfall, accepted, required, events.data?.length ?? 0);
  return <AppShell programme={`${data.requirement.buyer_name} · ${data.requirement.crop}`}><main className="mx-auto max-w-[1320px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="mb-7"><p className="section-eyebrow">Role-aware operating queue</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">My Work</h1><p className="mt-2 text-sm text-muted-foreground">Tasks derived from current domain state for <span className="font-medium text-foreground">{role.replace(/_/g, ' ')}</span>.</p></header>
    <section className="grid gap-4 sm:grid-cols-3"><Summary label="Open work" value={String(tasks.length)} /><Summary label="Requirement health" value={data.supply_health.replace(/_/g, ' ')} /><Summary label="Physical acceptance" value={`${accepted} / ${required} kg`} /></section>
    <section className="operational-panel mt-7 overflow-hidden"><div className="flex items-end justify-between px-5 py-5"><div><p className="section-eyebrow">Authoritative tasks</p><h2 className="mt-2 text-xl font-semibold">Priority queue</h2></div><span className="text-xs text-muted-foreground">No inferred assignments</span></div>
      {tasks.length ? <ol className="divide-y divide-white/[0.07]">{tasks.map(task => <li key={task.title} className="grid gap-4 px-5 py-5 md:grid-cols-[32px_minmax(0,1fr)_auto] md:items-center"><span className={`grid h-8 w-8 place-items-center rounded-full ${task.urgent ? 'bg-warning/10 text-warning' : 'bg-primary/10 text-primary'}`}>{task.urgent ? <AlertTriangle className="h-4 w-4" /> : <ClipboardList className="h-4 w-4" />}</span><div><p className="text-sm font-medium">{task.title}</p><p className="mt-1 text-xs text-muted-foreground">{task.detail}</p></div><Link href={task.href} className="inline-flex items-center gap-2 text-xs font-semibold text-primary">Open <ArrowRight className="h-3.5 w-3.5" /></Link></li>)}</ol> : <div className="border-t border-white/[0.07] px-5 py-12 text-center"><CheckCircle2 className="mx-auto h-5 w-5 text-success" /><p className="mt-3 text-sm font-medium">No work is currently derivable for this role.</p><p className="mt-1 text-xs text-muted-foreground">KoroFarm does not fabricate placeholder tasks.</p></div>}
    </section>
  </main></AppShell>;
}

function deriveTasks(activeRole: string, health: string, shortfall: number, accepted: number, required: number, eventCount: number) {
  const tasks: { title: string; detail: string; href: string; urgent?: boolean }[] = [];
  if (activeRole === 'SUPPLY_COORDINATOR' && health !== 'COVERED') tasks.push({ title: 'Recover at-risk requirement', detail: `${shortfall} kg remains uncovered. Review authorized standby and escalation state.`, href: `/requirements/${requirementId}`, urgent: true });
  if (activeRole === 'WAREHOUSE_OPERATOR' && accepted < required) tasks.push({ title: 'Prepare for expected receipts', detail: `${required - accepted} kg has not reached accepted physical state.`, href: '/fulfilment' });
  if (activeRole === 'PROCUREMENT_MANAGER' && health !== 'COVERED') tasks.push({ title: 'Review commercial recovery exception', detail: 'Supply health requires procurement review before any approval-governed action.', href: '/assurance', urgent: true });
  if (activeRole === 'AUDITOR' && eventCount > 0) tasks.push({ title: 'Review recent material events', detail: `${eventCount} auditable events are available for the configured requirement.`, href: '/activity' });
  if (activeRole === 'FARMER') tasks.push({ title: 'Farmer identity linkage required', detail: 'No farmer membership is available in offline demo mode, so private supply tasks are withheld.', href: '/profile' });
  return tasks;
}

function Summary({ label, value }: { label: string; value: string }) { return <div className="operational-panel p-5"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>; }
