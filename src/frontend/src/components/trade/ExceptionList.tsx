'use client';

import Link from 'next/link';
import { useState } from 'react';
import { type SupplyException, useAcknowledgeException, useExceptions, useResolveException } from '@/hooks/useTrade';
import { ErrorNote, Field, LoadState, Pill, SubmitButton, formValues, kg } from '@/components/trade/TradeUi';

export const exceptionKindLabel: Record<SupplyException['kind'], string> = {
  CAPACITY_SHORTFALL: 'Capacity shortfall',
  RESPONSE_OVERDUE: 'Supplier reply overdue',
  STANDBY_EXPIRED: 'Standby authorization expired',
};

/** Open supply exceptions, refreshed in the background so worker-raised exceptions appear without a reload. */
export function ExceptionList({ requirementId, empty, showOrder = false }: { requirementId?: string; empty: string; showOrder?: boolean }) {
  const exceptions = useExceptions({ requirementId });
  return <LoadState query={exceptions} empty={<p className="mt-3 text-sm text-muted-foreground" role="status">{empty}</p>}>
    <ul className="mt-3 space-y-3" aria-label="Open supply exceptions">
      {exceptions.data?.map(item => <ExceptionItem key={item.id} item={item} showOrder={showOrder} />)}
    </ul>
  </LoadState>;
}

function ExceptionItem({ item, showOrder }: { item: SupplyException; showOrder: boolean }) {
  const [resolving, setResolving] = useState(false);
  const acknowledge = useAcknowledgeException();
  const resolve = useResolveException();

  async function onResolve(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const ok = await resolve.mutateAsync({ exceptionId: item.id, resolution: formValues(event.currentTarget).resolution ?? '' }).then(() => true, () => false);
    if (ok) setResolving(false);
  }

  return <li data-exception={item.kind} className="rounded-md border border-destructive/40 p-4">
    <div className="flex flex-wrap items-center gap-2">
      <Pill tone="bad">{exceptionKindLabel[item.kind]}</Pill>
      {Number(item.shortfall_kg) > 0 && <span className="text-sm font-semibold">{kg(item.shortfall_kg)}</span>}
      {item.acknowledged_at ? <Pill tone="neutral">Acknowledged</Pill> : <Pill tone="warn">New</Pill>}
      <span className="text-xs text-muted-foreground">Opened {new Date(item.opened_at).toLocaleString('en-JM')}</span>
    </div>
    <p className="mt-2 text-sm">{item.summary}</p>
    {showOrder && <Link href={`/orders/${item.requirement_id}`} className="mt-1 inline-block text-xs text-primary underline-offset-2 hover:underline">{item.requirement_label ?? 'Open order'}</Link>}
    <div className="mt-3 flex flex-wrap gap-2">
      {!item.acknowledged_at && <button type="button" disabled={acknowledge.isPending} onClick={() => acknowledge.mutate({ exceptionId: item.id })} className="min-h-9 rounded-md border border-white/[0.14] px-3 text-xs disabled:opacity-60">Acknowledge</button>}
      <button type="button" onClick={() => setResolving(v => !v)} className="min-h-9 rounded-md px-3 text-xs text-muted-foreground">Resolve…</button>
    </div>
    {resolving && <form onSubmit={onResolve} aria-label="Resolve exception" className="mt-3 flex flex-wrap items-end gap-2">
      <div className="min-w-[240px] flex-1"><Field label="What was done" name="resolution" required minLength={3} hint="A capacity shortfall closes by itself once the exposure is covered; it cannot be resolved by hand while exposure remains." /></div>
      <SubmitButton busy={resolve.isPending}>Resolve</SubmitButton>
    </form>}
    <ErrorNote error={acknowledge.error ?? resolve.error} />
  </li>;
}
