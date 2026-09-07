import { Check, CircleAlert, RotateCcw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RecoveryStep } from '@/lib/mockdata';

export function RecoveryPanel({ steps, status }: { steps: RecoveryStep[]; status?: string }) {
  const complete = status === 'completed';
  const label = status ? status.replace(/_/g, ' ') : 'No recovery active';
  return <Card>
    <CardHeader className="flex-row items-center justify-between space-y-0 pb-4"><div><p className="font-mono text-xs uppercase tracking-[0.18em] text-warning">Agent activity</p><CardTitle className="mt-2 text-lg">Recovery run</CardTitle></div><Badge variant="outline" className={complete ? 'border-success/30 text-success' : 'border-warning/30 text-warning'}><RotateCcw className="mr-1.5 h-3.5 w-3.5" />{label}</Badge></CardHeader>
    <CardContent className="space-y-4">
      {steps.length ? steps.map((step, index) => <div className="flex gap-3" key={step.label}><div className="relative flex w-6 justify-center"><div className={`z-10 flex h-6 w-6 items-center justify-center rounded-full ${complete ? 'bg-success text-success-foreground' : 'bg-warning text-warning-foreground'}`}><Check className="h-3.5 w-3.5" /></div>{index < steps.length - 1 && <div className="absolute top-6 h-9 w-px bg-success/30" />}</div><div className="pb-1"><p className="text-sm font-medium">{step.label}</p><p className="text-xs leading-5 text-muted-foreground">{step.detail}</p></div></div>) : <p className="text-sm text-muted-foreground">No disruption has been recorded for this requirement.</p>}
      <div className="mt-2 flex items-start gap-2 border-t border-border/60 pt-4 text-xs text-muted-foreground"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary" />Decisions use deterministic quantity and cost calculations. No fulfilment is claimed before receipt and grading evidence.</div>
    </CardContent>
  </Card>;
}
