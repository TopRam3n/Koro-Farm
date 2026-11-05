'use client';

import Link from 'next/link';
import { useState } from 'react';
import { AppShell } from '@/components/AppShell';
import { WorkspaceHeader } from '@/components/WorkspacePrimitives';
import {
  type BuyerOrder, type BuyerOrderDelivery, type BuyerQuantities, useBuyerCommands, useBuyerOrder, useBuyerOrders,
} from '@/hooks/useFulfilment';
import { apiDownload } from '@/lib/api';
import { ErrorNote, Field, LoadState, Pill, SubmitButton, TextArea, formValues, humanize, kg } from '@/components/trade/TradeUi';

const when = (value?: string | null) => value ? new Date(value).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' }) : '—';

/** Quantities a buyer sees, never merged (R1 WP5, M2): their own confirmation and a staff relay are separate lines. */
const QUANTITIES: Array<[keyof BuyerQuantities, string, string]> = [
  ['required_kg', 'Ordered', 'What you ordered'],
  ['delivered_kg', 'Delivered', 'Recorded as delivered, with proof of delivery and any corrections'],
  ['confirmed_by_you_kg', 'Confirmed by you', 'What you confirmed in this account'],
  ['relayed_by_staff_kg', 'Relayed by staff', 'Confirmations staff recorded from a call, email or signed note; not your own statement'],
  ['awaiting_your_confirmation_kg', 'Awaiting your confirmation', 'Delivered, but you have not confirmed it yet'],
  ['disputed_kg', 'Under dispute', 'Open disputes'],
  ['still_to_deliver_kg', 'Still to deliver', 'Ordered minus delivered'],
];

export function BuyerPortal() {
  const orders = useBuyerOrders();
  const [selected, setSelected] = useState<string | null>(null);
  const active = selected ?? orders.data?.[0]?.requirement_id ?? null;
  return <AppShell programme="Buyer"><main className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6 lg:px-8">
    <WorkspaceHeader eyebrow="Buyer portal" title="My orders" description="Your orders and deliveries. Confirm what you received, follow up a difference, and download the delivery record." />
    <LoadState query={orders} empty={<p className="mt-4 text-sm text-muted-foreground">You have no orders yet. <Link href="/marketplace" className="text-primary hover:underline">See available produce</Link>.</p>}>
      <div className="mt-4 grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <ul aria-label="My orders" className="space-y-2">{orders.data?.map(order => <li key={order.requirement_id}>
          <button type="button" onClick={() => setSelected(order.requirement_id)} aria-current={active === order.requirement_id ? 'true' : undefined}
            className={`w-full rounded-md border p-3 text-left text-sm ${active === order.requirement_id ? 'border-primary/60 bg-primary/5' : 'border-white/[0.1]'}`}>
            <span className="font-medium">{orderTitle(order)}</span>
            <span className="mt-1 block text-xs text-muted-foreground">{order.status_label} · {kg(order.quantities.delivered_kg)} of {kg(order.quantities.required_kg)} delivered</span>
            {Number(order.quantities.awaiting_your_confirmation_kg) > 0 && <span className="mt-1 block text-xs text-warning">{kg(order.quantities.awaiting_your_confirmation_kg)} waiting for your confirmation</span>}
          </button>
        </li>)}</ul>
        {active && <OrderView id={active} />}
      </div>
    </LoadState>
  </main></AppShell>;
}

const orderTitle = (o: BuyerOrder) => `${humanize(o.crop)}, grade ${o.grade}`;

function OrderView({ id }: { id: string }) {
  const order = useBuyerOrder(id);
  const [downloadError, setDownloadError] = useState<unknown>(null);
  return <LoadState query={order}>{order.data && <section aria-label={`Order ${orderTitle(order.data)}`} className="space-y-5">
    <div className="operational-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{orderTitle(order.data)}</h2>
        <Pill tone={order.data.status === 'COMPLETED' ? 'good' : order.data.status === 'CANCELLED' ? 'neutral' : 'info'}>{order.data.status_label}</Pill>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">Delivery {order.data.delivery_window_start} to {order.data.delivery_window_end} · {order.data.destination}</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Order quantities">
        {QUANTITIES.map(([key, label, hint]) => <div key={key} className="rounded-md border border-white/[0.07] p-3" title={hint}>
          <dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold" data-buyer-figure={key}>{kg(order.data.quantities[key])}</dd>
        </div>)}
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={() => { setDownloadError(null); apiDownload(`/buyer/orders/${id}/delivery-record`, `korofarm-delivery-record-${id}.csv`).catch(setDownloadError); }}
          className="min-h-11 rounded-md border border-white/[0.14] px-3 text-sm">Download delivery record (CSV)</button>
      </div>
      <ErrorNote error={downloadError} />
    </div>
    <div>
      <h3 className="text-sm font-semibold">Deliveries</h3>
      {order.data.deliveries.length === 0 ? <p className="mt-1 text-sm text-muted-foreground">Nothing has been delivered yet.</p>
        : <ul className="mt-2 space-y-3" aria-label="Deliveries">{order.data.deliveries.map(d => <DeliveryCard key={d.id} delivery={d} />)}</ul>}
    </div>
    <div>
      <h3 className="text-sm font-semibold">Disputes</h3>
      {order.data.disputes.length === 0 ? <p className="mt-1 text-sm text-muted-foreground">No disputes.</p>
        : <ul className="mt-2 space-y-2 text-sm" aria-label="Disputes">{order.data.disputes.map(d => <li key={d.id} data-buyer-dispute={d.status} className="rounded-md border border-white/[0.1] p-3">
          <div className="flex flex-wrap items-center gap-2"><Pill tone={d.status === 'OPEN' ? 'warn' : 'neutral'}>{d.status === 'OPEN' ? 'Open' : humanize(d.status)}</Pill>
            <span className="text-xs text-muted-foreground">Raised by {d.raised_by} {when(d.created_at)}{d.quantity_kg ? ` · ${kg(d.quantity_kg)}` : ''}</span></div>
          <p className="mt-1">{d.description}</p>
          {d.resolution ? <p className="mt-1 text-xs">Outcome ({when(d.resolved_at)}): {d.resolution}</p> : <p className="mt-1 text-xs text-muted-foreground">Your supplier coordinator is looking into it.</p>}
        </li>)}</ul>}
    </div>
  </section>}</LoadState>;
}

function DeliveryCard({ delivery }: { delivery: BuyerOrderDelivery }) {
  const { confirm, dispute } = useBuyerCommands();
  const [mode, setMode] = useState<'none' | 'confirm' | 'difference' | 'dispute'>('none');
  const current = delivery.current_statement;
  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const v = formValues(event.currentTarget);
    const run = mode === 'dispute'
      ? dispute.mutateAsync({ deliveryId: delivery.id, description: v.description ?? '', quantity_kg: v.quantity_kg || undefined })
      : confirm.mutateAsync({ deliveryId: delivery.id, confirmed_quantity_kg: v.confirmed_quantity_kg ?? '', discrepancy: mode === 'difference', note: v.note });
    if (await run.then(() => true, () => false)) setMode('none');
  }
  return <li data-buyer-delivery={delivery.id} className="operational-panel p-4 text-sm">
    <div className="flex flex-wrap items-center gap-2"><span className="font-medium">Shipment {delivery.shipment_reference}</span>
      <span className="text-xs text-muted-foreground">{when(delivery.delivered_at)}</span></div>
    <p className="mt-1">Delivered {kg(delivery.delivered_quantity_kg)}{delivery.corrections.length ? ` (recorded ${kg(delivery.recorded_quantity_kg)}, ${delivery.corrections.length} correction(s))` : ''}</p>
    {current ? <p className="mt-1" data-statement-source={current.source}><Pill tone={current.outcome === 'DISCREPANCY' ? 'warn' : 'good'}>{current.outcome === 'DISCREPANCY' ? 'Difference reported' : 'Confirmed'}</Pill> {kg(current.confirmed_quantity_kg)}
      <span className="block text-xs text-muted-foreground">{current.source_label}{current.source === 'STAFF_RELAYED' ? `: ${current.buyer_representative} via ${current.communication_channel}, ${when(current.stated_at)}` : ''}</span></p>
      : <p className="mt-1 text-warning">Waiting for your confirmation.</p>}
    {delivery.statement_history.length > 1 && <details className="mt-1 text-xs"><summary className="cursor-pointer text-muted-foreground">Earlier statements ({delivery.statement_history.length - 1})</summary>
      <ol className="mt-1 space-y-1">{delivery.statement_history.slice(0, -1).map(s => <li key={s.id}>{when(s.created_at)}: {kg(s.confirmed_quantity_kg)}, {s.source_label}</li>)}</ol></details>}
    <div className="mt-2 flex flex-wrap gap-2">
      <button type="button" onClick={() => setMode('confirm')} className="min-h-11 rounded-md border border-primary/60 px-3 text-sm text-primary">Confirm what I received</button>
      <button type="button" onClick={() => setMode('difference')} className="min-h-11 rounded-md border border-white/[0.14] px-3 text-sm">Report a difference</button>
      <button type="button" onClick={() => setMode('dispute')} className="min-h-11 rounded-md px-3 text-sm text-muted-foreground">Raise another problem</button>
    </div>
    {mode !== 'none' && <form onSubmit={onSubmit} aria-label={mode === 'confirm' ? 'Confirm delivery' : mode === 'difference' ? 'Report a difference' : 'Raise a problem'} className="mt-3 grid gap-3 sm:grid-cols-2">
      {mode !== 'dispute' && <Field label="Quantity you received (kg)" name="confirmed_quantity_kg" type="number" min="0" step="0.001" max={Number(delivery.delivered_quantity_kg)}
        defaultValue={mode === 'confirm' ? Number(delivery.delivered_quantity_kg) : undefined} required hint={`No more than the ${kg(delivery.delivered_quantity_kg)} recorded as delivered.`} />}
      {mode === 'difference' && <TextArea label="What is different?" name="note" required minLength={3} />}
      {mode === 'dispute' && <>
        <div className="sm:col-span-2"><TextArea label="What is the problem?" name="description" required minLength={3} /></div>
        <Field label="Quantity affected (kg, optional)" name="quantity_kg" type="number" min="0" step="0.001" />
      </>}
      <div className="sm:col-span-2"><SubmitButton busy={confirm.isPending || dispute.isPending}>{mode === 'confirm' ? 'Confirm' : mode === 'difference' ? 'Report difference' : 'Raise problem'}</SubmitButton></div>
    </form>}
    <ErrorNote error={confirm.error ?? dispute.error} />
  </li>;
}
