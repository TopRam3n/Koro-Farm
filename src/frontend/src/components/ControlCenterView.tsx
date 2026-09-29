'use client';

import { AlertTriangle, ArrowRight, CircleHelp, RefreshCw, ShieldAlert } from 'lucide-react';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { useAssurance, useEvents, useFulfilment } from '@/hooks/useAssurance';
import { assessActionState, classifyDeliveryWindow, formatDeliveryDate, windowPhaseLabel } from '@/lib/commandCenterState';

const requirementId = process.env.NEXT_PUBLIC_REQUIREMENT_ID ?? (process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? '00000000-0000-0000-0000-000000000500' : '');

export function ControlCenterView() {
  const assurance = useAssurance(requirementId);
  const fulfilment = useFulfilment(requirementId);
  const events = useEvents(requirementId);

  if (assurance.isLoading) return <CommandLoading />;
  if (!assurance.data) return <CommandError message={assurance.error?.message} onRetry={() => void assurance.refetch()} />;

  const data = assurance.data;
  const required = Number(data.requirement.required_quantity_kg);
  const committed = Number(data.committed_quantity_kg);
  const shortfall = Number(data.unfilled_quantity_kg);
  const windowPhase = classifyDeliveryWindow(data.requirement.delivery_window_start, data.requirement.delivery_window_end);
  const action = assessActionState({
    supplyHealth: data.supply_health,
    shortfallKg: shortfall,
    riskLabel: data.risk?.label,
    windowPhase,
    dataUnavailable: fulfilment.isError || events.isError,
  });
  const planningCoverage = required > 0 ? Math.round(committed / required * 100) : null;
  const retryUnavailableData = () => void Promise.all([fulfilment.refetch(), events.refetch()]);

  return <AppShell className="control-center-shell" compactNavGroups programme={`${data.requirement.buyer_name} · ${data.requirement.crop}`}>
    <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-7">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-sm font-semibold text-muted-foreground sm:text-base">Supply Assurance Control Room</h1>
        <span className="text-xs font-medium text-muted-foreground">Currently configured requirement</span>
      </div>

      <section aria-label="Commitment identity" className="commitment-object overflow-hidden border border-white/15 bg-card">
        <div className="grid gap-6 px-5 py-5 sm:px-7 sm:py-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(230px,0.6fr)] lg:items-center">
          <div className="min-w-0">
            <h2 className="text-2xl font-semibold leading-tight sm:text-3xl lg:text-4xl">{data.requirement.buyer_name}</h2>
            <p className="mt-2 text-lg font-semibold sm:text-xl"><span className="text-primary">{data.requirement.crop}</span><span className="mx-2 text-muted-foreground">/</span>Grade {data.requirement.grade}</p>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-3 border-t border-white/10 pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
            <div>
              <p className="text-xs font-medium text-muted-foreground">Planning health</p>
              <p className={`mt-1 text-xl font-semibold ${planningHealthTone(data.supply_health)}`}>{data.supply_health.replace(/_/g, ' ')}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground">Delivery window</p>
              <p className="mt-1 text-sm font-semibold tabular">{formatDeliveryDate(data.requirement.delivery_window_start)} – {formatDeliveryDate(data.requirement.delivery_window_end)}</p>
              <p className={`mt-1 text-sm font-semibold ${windowTone(windowPhase)}`}>{windowPhaseLabel(windowPhase)}</p>
            </div>
          </div>
        </div>
        <div className="grid gap-4 border-t border-white/10 bg-white/[0.02] px-5 py-4 sm:grid-cols-2 sm:px-7">
          <IdentityField label="Destination" value={data.requirement.destination || 'Not provided'} />
          <p className="text-sm leading-5 text-muted-foreground">Buyer commitment under active assurance. Programme data is limited to this configured requirement.</p>
        </div>
      </section>

      <section aria-labelledby="action-title" className={`commitment-action my-4 flex flex-col gap-4 border-y px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5 ${action.kind === 'required' || action.kind === 'review' ? 'border-warning/35 bg-warning/[0.07]' : 'border-white/15 bg-white/[0.035]'}`} role="status">
        <div className="flex min-w-0 items-start gap-3">
          <ActionIcon kind={action.kind} />
          <div>
            <h2 id="action-title" className={`text-lg font-semibold ${action.kind === 'required' || action.kind === 'review' ? 'text-warning' : 'text-foreground'}`}>{action.title}</h2>
            <p className="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">{action.reason}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {action.kind === 'required' || action.kind === 'review' ? <Link href={`/requirements/${data.requirement.id}`} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 bg-warning px-4 text-sm font-semibold text-warning-foreground hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Open requirement <ArrowRight className="h-4 w-4" /></Link> : null}
          {fulfilment.isError || events.isError ? <button type="button" onClick={retryUnavailableData} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-sm border border-white/20 px-4 text-sm font-semibold hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><RefreshCw className="h-4 w-4" />Retry data</button> : null}
        </div>
      </section>

      <div className="grid gap-x-10 gap-y-8 xl:grid-cols-2">
        <section aria-labelledby="planning-title" className="planning-ledger min-w-0 bg-card px-4 py-5 sm:px-6 sm:py-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 id="planning-title" className="text-xl font-semibold">Planning coverage</h2>
            <span className="text-sm text-muted-foreground">Plan v{data.requirement.plan_version} · as of time not provided</span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">Committed and authorized reserve supply. Not physical fulfilment.</p>
          <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-3">
            <QuantityFigure label="Required" value={formatQuantity(data.requirement.required_quantity_kg)} />
            <QuantityFigure label="Committed" value={formatQuantity(data.committed_quantity_kg)} tone="info" />
            <QuantityFigure label="Authorized standby" value={formatQuantity(data.standby_quantity_kg)} tone="info" />
            <QuantityFigure label="Planning shortfall" value={formatQuantity(data.unfilled_quantity_kg)} tone={shortfall > 0 ? 'attention' : 'default'} />
            <QuantityFigure label="Committed planning coverage" value={planningCoverage === null ? 'Unavailable' : `${planningCoverage}%`} />
          </dl>
          <div className="mt-6 flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
            <span><span className="text-muted-foreground">Structural risk</span><strong className={`ml-2 font-semibold ${riskTone(data.risk?.label)}`}>{data.risk?.label ?? 'Unavailable'}</strong>{data.risk ? <span className="ml-2 text-sm text-muted-foreground">{data.risk.calculation_version}</span> : null}</span>
            <span><span className="text-muted-foreground">Planning health</span><strong className={`ml-2 font-semibold ${planningHealthTone(data.supply_health)}`}>{data.supply_health.replace(/_/g, ' ')}</strong></span>
          </div>
          <details className="mt-5">
            <summary className="min-h-11 cursor-pointer py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Risk basis and limits</summary>
            <p className="pb-2 text-sm leading-5 text-muted-foreground">{data.risk ? data.risk.rules_triggered.length ? `Triggered rules: ${data.risk.rules_triggered.join(', ')}.` : `No rules triggered in ${data.risk.calculation_version}.` : 'A risk snapshot was not returned.'}</p>
          </details>
        </section>

        <section aria-labelledby="physical-title" className="physical-ledger min-w-0 bg-secondary px-4 py-5 sm:px-6 sm:py-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 id="physical-title" className="text-xl font-semibold">Physical fulfilment</h2>
            <span className="text-sm text-muted-foreground">Fulfilment summary · as of time not provided</span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">Observed movement and inspection. No schedule or completion is inferred.</p>
          <ol aria-label="Physical fulfilment stages" className="physical-stage-track mt-6 grid grid-cols-2 gap-x-5 gap-y-6 sm:grid-cols-4">
            <PhysicalStage label="Received" value={summaryQuantity(fulfilment.data?.received_kg, fulfilment.isLoading, fulfilment.isError)} source="Receiving record" tone="info" />
            <PhysicalStage label="Accepted" value={summaryQuantity(fulfilment.data?.accepted_kg, fulfilment.isLoading, fulfilment.isError)} source="Inspection record" tone="info" />
            <PhysicalStage label="Rejected" value={summaryQuantity(fulfilment.data?.rejected_kg, fulfilment.isLoading, fulfilment.isError)} source="Inspection record" tone={Number(fulfilment.data?.rejected_kg ?? 0) > 0 ? 'failure' : 'default'} />
            <PhysicalStage label="Shipped" value="Unavailable" source="Not returned by API" />
            <PhysicalStage label="Delivered" value="Unavailable" source="Not returned by API" />
            <PhysicalStage label="Buyer-confirmed" value="Unavailable" source="Not returned by API" />
            <PhysicalStage label="Reconciled" value="Unavailable" source="Not returned by API" />
          </ol>
          <p className="mt-6 text-sm leading-5 text-muted-foreground">Physical progress against a receiving schedule: <strong className="text-foreground">not assessable</strong>. No authoritative receiving schedule is returned by this API.</p>
        </section>
      </div>

      <section aria-labelledby="activity-title" className="mt-9">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="activity-title" className="text-lg font-semibold">Recent recorded changes</h2>
          <Link href="/activity" className="text-sm font-medium text-primary underline-offset-4 hover:underline">Open activity and audit</Link>
        </div>
        {events.isLoading ? <p className="py-4 text-sm text-muted-foreground">Loading requirement events…</p> : events.isError ? <p className="py-4 text-sm text-muted-foreground">Event history unavailable. Retry data to reassess.</p> : events.data?.length ? <ol className="mt-3">{events.data.slice(-5).reverse().map(event => <li key={event.id} className="grid gap-1 py-3 sm:grid-cols-[190px_minmax(0,1fr)_130px] sm:items-baseline"><time className="text-sm tabular text-muted-foreground">{formatEventTime(event.occurred_at)}</time><span className="text-base font-medium">{event.event_type.replace(/[._]/g, ' ')}</span><span className="text-sm text-muted-foreground">Actor: {event.actor_type}</span></li>)}</ol> : <p className="py-4 text-sm text-muted-foreground">No requirement events were returned.</p>}
      </section>

      <p className="mt-5 text-sm leading-5 text-muted-foreground">The current API does not return a snapshot timestamp, receiving schedule, delivery confirmation, reconciliation state, unified exception queue, or approval requirements. Their absence is shown as unavailable, not as zero or all-clear.</p>
    </main>
  </AppShell>;
}

function IdentityField({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs font-semibold text-muted-foreground">{label}</p><p className="mt-1 text-base font-medium">{value || 'Not provided'}</p></div>;
}

function QuantityFigure({ label, value, tone = 'default' }: { label: string; value: string; tone?: 'default' | 'attention' | 'info' }) {
  const color = tone === 'attention' ? 'text-warning' : tone === 'info' ? 'text-accent' : 'text-foreground';
  return <div className="min-w-0"><dt className="text-sm font-medium text-muted-foreground">{label}</dt><dd className={`mt-1 break-words text-2xl font-semibold leading-tight tabular sm:text-3xl ${color}`}>{value}</dd></div>;
}

function PhysicalStage({ label, value, source, tone = 'default' }: { label: string; value: string; source: string; tone?: 'default' | 'info' | 'failure' }) {
  const color = tone === 'info' ? 'text-accent' : tone === 'failure' ? 'text-destructive' : 'text-foreground';
  return <li className="min-w-0 border-t border-white/15 pt-3"><p className="text-sm font-semibold">{label}</p><p className={`mt-2 break-words text-xl font-semibold leading-tight tabular ${color}`}>{value}</p><p className="mt-1 text-sm leading-5 text-muted-foreground">{source}</p></li>;
}

function ActionIcon({ kind }: { kind: 'required' | 'review' | 'incomplete' | 'limited' }) {
  const Icon = kind === 'required' ? ShieldAlert : kind === 'review' ? AlertTriangle : CircleHelp;
  return <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${kind === 'required' || kind === 'review' ? 'text-warning' : 'text-muted-foreground'}`} aria-hidden="true" />;
}

function formatQuantity(value?: string | null) {
  if (value === undefined || value === null || !Number.isFinite(Number(value))) return 'Unavailable';
  return `${new Intl.NumberFormat('en-JM', { maximumFractionDigits: 3 }).format(Number(value))} kg`;
}

function summaryQuantity(value: string | undefined, isLoading: boolean, isError: boolean) {
  if (isError) return 'Unavailable';
  if (isLoading) return 'Loading';
  return value === undefined ? 'Not returned' : formatQuantity(value);
}

function formatEventTime(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Timestamp unavailable';
  return new Intl.DateTimeFormat('en-JM', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Jamaica' }).format(date);
}

function CommandLoading() {
  return <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8" aria-busy="true"><h1 className="text-2xl font-semibold">Supply Assurance Control Room</h1><p className="mt-4 text-sm text-muted-foreground">Loading authoritative requirement data…</p></main>;
}

function CommandError({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8"><h1 className="text-2xl font-semibold">Supply Assurance Control Room</h1><div role="alert" className="mt-5 border-y border-warning/40 py-5"><h2 className="flex items-center gap-2 text-base font-semibold"><AlertTriangle className="h-5 w-5 text-warning" />Requirement data unavailable</h2><p className="mt-2 text-sm text-muted-foreground">{message ?? 'The authoritative requirement could not be loaded.'} No quantities or status have been substituted.</p><button type="button" onClick={onRetry} className="mt-4 inline-flex min-h-11 items-center gap-2 border border-white/20 px-4 text-sm font-semibold hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><RefreshCw className="h-4 w-4" />Retry</button></div></main>;
}

function planningHealthTone(value: string) {
  if (value === 'COVERED') return 'text-success';
  if (value === 'AT_RISK') return 'text-warning';
  if (value === 'ESCALATION_REQUIRED') return 'text-destructive';
  return 'text-muted-foreground';
}

function riskTone(value?: string) {
  if (value === 'LOW') return 'text-success';
  if (value === 'MEDIUM') return 'text-warning';
  if (value === 'HIGH') return 'text-destructive';
  return 'text-muted-foreground';
}

function windowTone(phase: ReturnType<typeof classifyDeliveryWindow>) {
  return phase === 'ENDS_TODAY' || phase === 'OVERDUE' ? 'text-warning' : 'text-muted-foreground';
}