import { AlertTriangle, Check, Circle, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';

const tones: Record<string, string> = {
  COVERED: 'border-success/30 bg-success/10 text-success',
  COMPLETED: 'border-success/30 bg-success/10 text-success',
  VERIFIED: 'border-accent/30 bg-accent/10 text-accent',
  'BUILDING HISTORY': 'border-accent/25 bg-accent/10 text-accent',
  'NOT ASSESSED': 'border-white/10 bg-white/[0.04] text-muted-foreground',
  'AT RISK': 'border-warning/35 bg-warning/10 text-warning',
  'ESCALATION REQUIRED': 'border-destructive/35 bg-destructive/10 text-destructive',
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const normalized = status.replace(/_/g, ' ').toUpperCase();
  const Icon = normalized === 'COVERED' || normalized === 'COMPLETED' || normalized === 'VERIFIED'
    ? Check
    : normalized === 'AT RISK'
      ? AlertTriangle
      : normalized === 'ESCALATION REQUIRED'
        ? ShieldAlert
        : Circle;
  return <span className={cn('inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-semibold tracking-[0.08em]', tones[normalized] ?? tones['NOT ASSESSED'], className)}><Icon className="h-3.5 w-3.5" aria-hidden="true" />{normalized}</span>;
}
