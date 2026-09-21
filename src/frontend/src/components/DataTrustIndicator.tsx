import { CheckCircle2, Clock3, Database, HelpCircle } from 'lucide-react';

type TrustState = 'VERIFIED' | 'SYSTEM DERIVED' | 'STALE' | 'UNVERIFIED';
const styles: Record<TrustState, string> = { VERIFIED: 'text-success border-success/25 bg-success/10', 'SYSTEM DERIVED': 'text-accent border-accent/25 bg-accent/10', STALE: 'text-warning border-warning/25 bg-warning/10', UNVERIFIED: 'text-muted-foreground border-white/[0.08] bg-white/[0.03]' };

export function DataTrustIndicator({ state, detail }: { state: TrustState; detail?: string }) {
  const Icon = state === 'VERIFIED' ? CheckCircle2 : state === 'SYSTEM DERIVED' ? Database : state === 'STALE' ? Clock3 : HelpCircle;
  return <span title={detail} className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-semibold tracking-[0.08em] ${styles[state]}`}><Icon className="h-2.5 w-2.5" />{state}</span>;
}
