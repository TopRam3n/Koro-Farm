'use client';

import { AlertTriangle, CheckCircle2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAcceptAllocation, useCreatePlan, useDropout, useRunRecovery } from '@/hooks/useAssurance';

type Allocation = { id: string; role: string; status: string; farmer_name: string; quantity_kg: string };

export function DemoControls({ requirementId, allocations, hasPlan, recoveryStatus }: { requirementId: string; allocations: Allocation[]; hasPlan: boolean; recoveryStatus?: string }) {
  const createPlan = useCreatePlan(requirementId);
  const dropout = useDropout(requirementId);
  const accept = useAcceptAllocation(requirementId);
  const recovery = useRunRecovery(requirementId);
  const committed = allocations.find((item) => item.farmer_name === 'Demo Farmer 1' && item.role === 'COMMITTED' && item.status === 'COMMITTED' && Number(item.quantity_kg) === 80)
    ?? allocations.find((item) => item.role === 'COMMITTED' && item.status === 'COMMITTED' && Number(item.quantity_kg) === 80);
  const solicitations = allocations.filter((item) => item.status === 'SOLICITED');
  const busy = createPlan.isPending || dropout.isPending || accept.isPending || recovery.isPending;
  const error = createPlan.error ?? dropout.error ?? accept.error ?? recovery.error;

  return <Card className="border-primary/25 bg-primary/5"><CardHeader className="pb-3"><p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Guided demo</p><CardTitle className="mt-2 text-lg">Supply-assurance controls</CardTitle></CardHeader><CardContent className="space-y-3">
    {!hasPlan && <Button disabled={busy} onClick={() => createPlan.mutate()}><Play className="mr-2 h-4 w-4" />Create deterministic supply plan</Button>}
    {hasPlan && committed && !recoveryStatus && <Button variant="outline" disabled={busy} onClick={() => dropout.mutate({ allocationId: committed.id, reason: 'demo_farmer_dropout' })}><AlertTriangle className="mr-2 h-4 w-4" />Simulate {committed.quantity_kg}kg dropout</Button>}
    {recoveryStatus === 'running' && <Button disabled={busy} onClick={() => recovery.mutate()}><Play className="mr-2 h-4 w-4" />Run bounded recovery</Button>}
    {solicitations.map((item) => <Button key={item.id} variant="outline" disabled={busy} onClick={() => accept.mutate(item.id)}><CheckCircle2 className="mr-2 h-4 w-4" />Accept {item.quantity_kg}kg replacement from {item.farmer_name}</Button>)}
    <p className="text-xs leading-5 text-muted-foreground">These controls invoke the live API. Farmer acceptance remains explicit; the system never counts a solicitation as buyer supply.</p>
    {error && <p className="text-xs text-destructive">{error.message}</p>}
  </CardContent></Card>;
}
