import { AlertTriangle, CalendarDays, MapPin, ShieldCheck } from 'lucide-react';
import { Allocation, SupplyMetrics } from '@/lib/mockdata';
import { StatusBadge } from '@/components/StatusBadge';

interface Props {
  metrics: SupplyMetrics; allocations: Allocation[]; requirementId: string; crop: string; grade: string;
  buyerName: string; destination: string; deliveryWindow: string;
}

const kg = (value: number) => value.toLocaleString('en-JM', { maximumFractionDigits: 1 });

export function SupplyOverview({ metrics, allocations, requirementId, crop, grade, buyerName, destination, deliveryWindow }: Props) {
  const coverage = Math.min(100, Math.round((metrics.committedKg / metrics.requiredKg) * 100));
  const atRisk = metrics.health === 'AT_RISK' || metrics.health === 'ESCALATION_REQUIRED';
  return <section id="assurance" aria-labelledby="assurance-title" className={`overflow-hidden rounded-[14px] border bg-card ${atRisk ? 'border-warning/35' : 'border-primary/20'}`}>
    <div className="subtle-grid border-b border-white/[0.07] px-5 py-6 sm:px-7 lg:px-9 lg:py-8">
      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-start">
        <div>
          <p className="section-eyebrow">Can we keep the promise?</p>
          <h1 id="assurance-title" className="mt-3 text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">Grade {grade} {crop.toLowerCase()}</h1>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground"><span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-primary" />{buyerName}</span><span className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" />{destination}</span><span className="flex items-center gap-1.5"><CalendarDays className="h-3.5 w-3.5" />{deliveryWindow}</span></div>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end"><span data-testid="supply-health"><StatusBadge status={metrics.health} className="px-3 py-1.5 text-xs" /></span><span className="font-mono text-[10px] text-muted-foreground">{requirementId}</span></div>
      </div>
      <div className="mt-8 grid gap-7 lg:grid-cols-[minmax(220px,0.72fr)_minmax(0,1.55fr)] lg:items-end">
        <div><p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Required commitment</p><p className="tabular mt-1 text-[56px] font-semibold leading-none tracking-[-0.06em] sm:text-[68px]">{kg(metrics.requiredKg)}<span className="ml-2 text-xl font-medium tracking-normal text-muted-foreground">kg</span></p><p className="mt-3 text-sm text-muted-foreground">Active plan · {metrics.committedFarmerCount} committed farmers</p></div>
        <div>
          <div className="mb-3 flex items-end justify-between"><div><p className="text-xs text-muted-foreground">Committed planning coverage</p><p data-testid="committed-kg" className={`tabular mt-1 text-3xl font-semibold ${atRisk ? 'text-warning' : 'text-foreground'}`}>{kg(metrics.committedKg)} <span className="text-base font-normal text-muted-foreground">kg</span></p></div><p className={`tabular text-sm font-semibold ${atRisk ? 'text-warning' : 'text-success'}`}>{coverage}%</p></div>
          <div className="relative h-4 overflow-hidden rounded-[4px] bg-white/[0.06]" aria-label={`${coverage}% committed coverage`} role="img"><div className={`h-full transition-[width] duration-200 ${atRisk ? 'bg-warning' : 'bg-primary'}`} style={{ width: `${coverage}%` }} />{atRisk && <div className="absolute inset-y-0 right-0 bg-destructive/35" style={{ width: `${100 - coverage}%` }} />}</div>
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm"><span><span className="text-muted-foreground">Standby</span> <strong data-testid="standby-kg" className="tabular ml-1 text-accent">{kg(metrics.standbyKg)} kg</strong></span><span><span className="text-muted-foreground">Shortfall</span> <strong data-testid="shortfall-kg" className={`tabular ml-1 ${metrics.shortfallKg ? 'text-destructive' : 'text-foreground'}`}>{kg(metrics.shortfallKg)} kg</strong></span><span className="text-xs text-muted-foreground">Standby is reserved capacity, not buyer coverage.</span></div>
        </div>
      </div>
    </div>
    <div className={`flex items-start gap-3 px-5 py-4 text-sm sm:px-7 lg:px-9 ${atRisk ? 'bg-warning/[0.07]' : 'bg-primary/[0.04]'}`}>
      {atRisk ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" /> : <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" />}
      <p><strong>{atRisk ? `${kg(metrics.shortfallKg)} kg requires recovery.` : 'Supply commitment covered.'}</strong> <span className="text-muted-foreground">Planning coverage only. Physical delivery is tracked separately and has not been inferred.</span></p>
    </div>
  </section>;
}
