import { ArrowUpRight, CircleDollarSign, Truck } from 'lucide-react';
import { formatJmd } from '@/lib/mockdata';

export function EconomicsPanel({ economics }: { economics?: Record<string, string> | null }) {
  if (!economics) return <section className="operational-panel p-5"><p className="section-eyebrow">Unit economics</p><h2 className="mt-2 text-lg font-semibold">Recovery cost snapshot</h2><p className="mt-5 text-sm text-muted-foreground">No recovery cost snapshot yet. Cost is unknown, not J$0.</p></section>;
  const originalCost = Number(economics.original_landed_cost_jmd);
  const recoveredCost = Number(economics.recovered_landed_cost_jmd);
  const premium = Number(economics.recovery_premium_jmd);
  const premiumPercent = Number(economics.recovery_premium_pct).toFixed(2);
  return <section className="operational-panel p-5"><p className="section-eyebrow">Immutable economics</p><h2 className="mt-2 text-lg font-semibold">Recovery cost snapshot</h2><div className="mt-5 divide-y divide-white/[0.07]"><div className="flex items-center justify-between gap-4 py-3"><span className="flex items-center gap-2 text-xs text-muted-foreground"><CircleDollarSign className="h-4 w-4" />Original landed cost</span><strong className="tabular text-sm">{formatJmd(originalCost)}</strong></div><div className="flex items-center justify-between gap-4 py-3"><span className="flex items-center gap-2 text-xs text-muted-foreground"><Truck className="h-4 w-4" />Recovered landed cost</span><strong className="tabular text-sm">{formatJmd(recoveredCost)}</strong></div></div><div className="mt-3 flex items-end justify-between rounded-md border border-warning/20 bg-warning/[0.07] p-3"><div><p className="text-[11px] uppercase tracking-wider text-muted-foreground">Recovery delta</p><p className="tabular mt-1 text-xl font-semibold text-warning">+{formatJmd(premium)}</p></div><span className="flex items-center text-xs font-semibold text-warning"><ArrowUpRight className="h-4 w-4" />+{premiumPercent}%</span></div></section>;
}
