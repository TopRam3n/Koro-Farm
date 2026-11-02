'use client';

import { useState } from 'react';
import { AppShell } from '@/components/AppShell';
import { WorkspaceHeader } from '@/components/WorkspacePrimitives';
import { type BuyerDelivery, useBuyerCommands, useBuyerDeliveries } from '@/hooks/useFulfilment';
import { confirmationSource } from '@/components/trade/FulfilmentSection';
import { ErrorNote, Field, LoadState, Pill, SubmitButton, TextArea, formValues, kg } from '@/components/trade/TradeUi';

/** A buyer confirms what actually arrived, in their own account: the full quantity, part of it, or a difference. */
export function BuyerDeliveries() {
  const deliveries = useBuyerDeliveries();
  return <AppShell programme="Buyer"><main className="mx-auto max-w-[960px] px-4 py-6 sm:px-6 lg:px-8">
    <WorkspaceHeader eyebrow="Deliveries" title="My deliveries" description="Confirm what you received. If something is missing or wrong, say so here and it is raised with your supplier coordinator." />
    <LoadState query={deliveries} empty={<p className="mt-4 text-sm text-muted-foreground">No deliveries have been recorded for you yet.</p>}>
      <ul className="mt-4 space-y-4" aria-label="My deliveries">{deliveries.data?.map(d => <DeliveryItem key={d.id} delivery={d} />)}</ul>
    </LoadState>
  </main></AppShell>;
}

function DeliveryItem({ delivery }: { delivery: BuyerDelivery }) {
  const { confirm } = useBuyerCommands();
  const [mode, setMode] = useState<'none' | 'confirm' | 'difference'>('none');
  const c = delivery.confirmation;
  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const v = formValues(event.currentTarget);
    const ok = await confirm.mutateAsync({ deliveryId: delivery.id, confirmed_quantity_kg: v.confirmed_quantity_kg ?? '', discrepancy: mode === 'difference', note: v.note })
      .then(() => true, () => false);
    if (ok) setMode('none');
  }
  return <li data-delivery={delivery.id} className="operational-panel p-4 text-sm">
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-medium">{delivery.order}</span><span className="text-xs text-muted-foreground">Shipment {delivery.shipment_reference}</span>
    </div>
    <p className="mt-1">Recorded as delivered: {kg(delivery.delivered_quantity_kg)} on {new Date(delivery.delivered_at).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' })}</p>
    {c ? <p className="mt-1"><Pill tone={c.outcome === 'DISCREPANCY' ? 'warn' : 'good'}>{c.outcome === 'DISCREPANCY' ? 'Difference reported' : 'Confirmed'}</Pill> {kg(c.confirmed_quantity_kg)}
      <span className="block text-xs text-muted-foreground">{confirmationSource(c)}</span></p>
      : <p className="mt-1 text-warning">Waiting for your confirmation.</p>}
    <div className="mt-2 flex flex-wrap gap-2">
      <button type="button" onClick={() => setMode('confirm')} className="min-h-11 rounded-md border border-primary/60 px-3 text-sm text-primary">Confirm what I received</button>
      <button type="button" onClick={() => setMode('difference')} className="min-h-11 rounded-md border border-white/[0.14] px-3 text-sm">Report a difference</button>
    </div>
    {mode !== 'none' && <form onSubmit={onSubmit} aria-label={mode === 'confirm' ? 'Confirm delivery' : 'Report a difference'} className="mt-3 grid gap-3 sm:grid-cols-2">
      <Field label="Quantity you received (kg)" name="confirmed_quantity_kg" type="number" min="0" step="0.001" max={Number(delivery.delivered_quantity_kg)}
        defaultValue={mode === 'confirm' ? Number(delivery.delivered_quantity_kg) : undefined} required hint={`No more than the ${kg(delivery.delivered_quantity_kg)} recorded as delivered.`} />
      {mode === 'difference' && <TextArea label="What is different?" name="note" required minLength={3} />}
      <div className="sm:col-span-2"><SubmitButton busy={confirm.isPending}>{mode === 'confirm' ? 'Confirm' : 'Report difference'}</SubmitButton></div>
    </form>}
    <ErrorNote error={confirm.error} />
  </li>;
}
