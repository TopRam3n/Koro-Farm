'use client';

import { useState } from 'react';
import {
  type Confirmation, type FulfilmentRecord, type Receipt, type Shipment, useFulfilmentCommands, useFulfilmentRecord, useFulfilmentSites,
} from '@/hooks/useFulfilment';
import { ErrorNote, Field, LoadState, Pill, Select, SubmitButton, TextArea, formValues, humanize, kg } from '@/components/trade/TradeUi';

const ENDED = ['COMPLETED', 'CLOSED_WITH_VARIANCE', 'CANCELLED', 'CLOSED'];
const localToIso = (value: string) => new Date(value).toISOString();
const when = (value: string | null) => value ? new Date(value).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' }) : '—';

/** What is shown about an order's outcome (P6). Reconciled is not success, and a variance stays visible for good. */
export const outcomeLabel: Record<string, [string, 'good' | 'warn' | 'info' | 'neutral']> = {
  COMPLETED: ['Completed', 'good'], CLOSED_WITH_VARIANCE: ['Closed with variance', 'warn'], RECONCILED: ['Reconciled, not closed', 'info'],
  IN_FULFILMENT: ['In fulfilment', 'info'], CANCELLED: ['Cancelled', 'neutral'], CLOSED: ['Closed (legacy)', 'neutral'],
};

/** Who stated a confirmation. A staff relay is never shown as the buyer's own statement (P5). */
export function confirmationSource(c: Confirmation) {
  if (c.channel === 'BUYER_ACCOUNT') return 'Confirmed by the buyer in their account';
  if (c.channel === 'LEGACY_UNQUANTIFIED') return 'Legacy yes/no flag from before quantities were recorded; not counted as confirmed quantity';
  return `Relayed by staff: ${c.buyer_representative} via ${c.communication_channel}, ${when(c.stated_at)} (${c.attestation})`;
}

export function FulfilmentSection({ orderId }: { orderId: string }) {
  const record = useFulfilmentRecord(orderId);
  return <section aria-labelledby="order-fulfilment" className="operational-panel p-5">
    <h2 id="order-fulfilment" className="text-base font-semibold">Fulfilment and reconciliation</h2>
    <p className="mt-1 text-xs text-muted-foreground">Physical records are never edited: corrections are added beside them. Figures here are computed from those records, not from the agent.</p>
    <LoadState query={record}>{record.data && <Body orderId={orderId} r={record.data} />}</LoadState>
  </section>;
}

function Body({ orderId, r }: { orderId: string; r: FulfilmentRecord }) {
  const ended = ENDED.includes(r.lifecycle_status);
  const f = r.figures;
  const figures: Array<[string, string, string]> = [
    ['Required', f.required_kg, 'What the buyer ordered'], ['Committed', f.committed_kg, 'Agreed by suppliers'],
    ['Received', f.received_kg, 'Physically arrived at a site'], ['Accepted', f.accepted_kg, 'Passed grading'],
    ['Rejected', f.rejected_kg, 'Failed grading'], ['Dispatched', f.dispatched_kg, 'Left a site for the buyer'],
    ['Delivered', f.delivered_kg, 'Arrived at the buyer, by proof of delivery'], ['Buyer-confirmed', f.buyer_confirmed_kg, 'Quantity the buyer has confirmed'],
    ['Disputed', f.disputed_kg, 'Under open dispute'], ['Released', f.released_kg, 'Reservations released; original commitments stay on record'],
  ];
  const [label, tone] = outcomeLabel[r.lifecycle_status] ?? [humanize(r.lifecycle_status), 'neutral'];
  const effective = r.reconciliations.find(v => v.version === r.effective_reconciliation_version);
  return <div className="mt-3 space-y-5">
    <div className="flex flex-wrap items-center gap-2" aria-label="Order outcome">
      <Pill tone={tone}>{label}</Pill>
      {r.effective_reconciliation_version && <span className="text-xs text-muted-foreground">Reconciliation v{r.effective_reconciliation_version} in effect</span>}
      {f.unconfirmed_deliveries > 0 && <Pill tone="warn">{f.unconfirmed_deliveries} delivery(ies) not confirmed by the buyer</Pill>}
    </div>
    {r.lifecycle_status === 'CLOSED_WITH_VARIANCE' && effective && <p role="note" className="rounded-md border border-warning/50 p-3 text-sm">
      Closed with an accepted variance: {kg(effective.variances.required_minus_accepted_kg)} short of the order against accepted produce, {kg(effective.variances.required_minus_confirmed_kg)} against buyer-confirmed quantity.
    </p>}
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5" aria-label="Fulfilment quantities">
      {figures.map(([name, value, hint]) => <div key={name} className="rounded-md border border-white/[0.07] p-3" title={hint}>
        <dt className="text-xs text-muted-foreground">{name}</dt><dd className="mt-1 text-lg font-semibold" data-fulfilment-figure={name}>{kg(value)}</dd>
      </div>)}
    </dl>
    {!ended && <Receiving orderId={orderId} r={r} />}
    <Receipts orderId={orderId} receipts={r.receipts} locked={ended} />
    <Shipments orderId={orderId} r={r} locked={ended} />
    <Disputes orderId={orderId} r={r} locked={ended} />
    <Reconciliations orderId={orderId} r={r} locked={ended} />
    {!ended && <Close orderId={orderId} r={r} />}
  </div>;
}

function Receiving({ orderId, r }: { orderId: string; r: FulfilmentRecord }) {
  const sites = useFulfilmentSites();
  const { receive } = useFulfilmentCommands(orderId);
  if (r.receivable_allocations.length === 0) return null;
  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const v = formValues(form);
    const ok = await receive.mutateAsync({ ...v, received_at: localToIso(v.received_at ?? '') }).then(() => true, () => false);
    if (ok) form.reset();
  }
  return <details>
    <summary className="cursor-pointer text-sm font-medium">Record a receipt</summary>
    <form onSubmit={onSubmit} aria-label="Record a receipt" className="mt-2 grid gap-3 sm:grid-cols-3">
      <Select label="Supplier commitment" name="allocation_id" required placeholder="Choose" options={r.receivable_allocations.map(a => ({ value: a.allocation_id, label: `${a.farmer_name} (${a.parish}), ${kg(a.obligation_kg)} owed` }))} />
      <Select label="Fulfilment site" name="fulfilment_node_id" required placeholder="Choose" options={(sites.data ?? []).map(s => ({ value: s.id, label: `${s.name}, ${s.parish}` }))} />
      <Field label="Received (kg)" name="received_quantity_kg" type="number" min="0.001" step="0.001" required />
      <Field label="Received at" name="received_at" type="datetime-local" required />
      <Field label="Receipt evidence" name="receipt_evidence_reference" placeholder="e.g. weighbridge ticket" />
      <div className="self-end"><SubmitButton busy={receive.isPending}>Save receipt</SubmitButton></div>
    </form>
    <ErrorNote error={receive.error} />
  </details>;
}

function Receipts({ orderId, receipts, locked }: { orderId: string; receipts: Receipt[]; locked: boolean }) {
  if (receipts.length === 0) return <p className="text-sm text-muted-foreground">Nothing has been received for this order yet.</p>;
  return <div className="overflow-x-auto">
    <table className="w-full min-w-[640px] text-sm" aria-label="Receipts">
      <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-2">Supplier</th><th className="text-right">Received</th><th className="text-right">Accepted</th><th className="text-right">Rejected</th><th className="pl-3">Grading</th></tr></thead>
      <tbody className="divide-y divide-white/[0.07]">{receipts.map(receipt => <ReceiptRow key={receipt.id} orderId={orderId} receipt={receipt} locked={locked} />)}</tbody>
    </table>
  </div>;
}

function ReceiptRow({ orderId, receipt, locked }: { orderId: string; receipt: Receipt; locked: boolean }) {
  const [grading, setGrading] = useState(false);
  const { grade } = useFulfilmentCommands(orderId);
  async function onGrade(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const ok = await grade.mutateAsync({ sublotId: receipt.id, ...formValues(event.currentTarget) }).then(() => true, () => false);
    if (ok) setGrading(false);
  }
  return <>
    <tr data-receipt={receipt.id}>
      <td className="py-2">{receipt.farmer_name}<span className="block text-xs text-muted-foreground">{when(receipt.received_at)}</span></td>
      <td className="text-right">{kg(receipt.received_kg)}</td>
      <td className="text-right">{receipt.graded ? kg(receipt.accepted_kg) : '—'}</td>
      <td className="text-right">{receipt.graded ? kg(receipt.rejected_kg) : '—'}</td>
      <td className="pl-3">{receipt.graded ? <span>Grade {receipt.assigned_grade}{receipt.corrections ? ` · ${receipt.corrections} correction(s)` : ''}{receipt.rejection_reason ? ` · ${receipt.rejection_reason}` : ''}</span>
        : locked ? 'Not graded' : <button type="button" onClick={() => setGrading(v => !v)} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary">Record grading</button>}</td>
    </tr>
    {grading && <tr><td colSpan={5} className="pb-3"><form onSubmit={onGrade} aria-label={`Grading for ${receipt.farmer_name}`} className="grid gap-3 rounded-md border border-white/[0.1] p-3 sm:grid-cols-3">
      <Field label="Accepted (kg)" name="accepted_quantity_kg" type="number" min="0" step="0.001" required />
      <Field label="Rejected (kg)" name="rejected_quantity_kg" type="number" min="0" step="0.001" required />
      <Select label="Grade" name="assigned_grade" required options={['A', 'B', 'C'].map(g => ({ value: g, label: `Grade ${g}` }))} />
      <Field label="Rejection reason" name="rejection_reason" />
      <Field label="Inspection evidence" name="inspection_evidence_reference" />
      <div className="self-end"><SubmitButton busy={grade.isPending}>Save grading</SubmitButton></div>
      <div className="sm:col-span-3"><ErrorNote error={grade.error} /></div>
    </form></td></tr>}
  </>;
}

function Shipments({ orderId, r, locked }: { orderId: string; r: FulfilmentRecord; locked: boolean }) {
  const sites = useFulfilmentSites();
  const { createShipment } = useFulfilmentCommands(orderId);
  const unshipped = r.receipts.filter(x => x.graded && !x.shipment_id && Number(x.accepted_kg) > 0);
  async function onCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const v = formValues(form);
    const ok = await createShipment.mutateAsync({ fulfilment_node_id: v.fulfilment_node_id ?? '', reference: v.reference ?? '' }).then(() => true, () => false);
    if (ok) form.reset();
  }
  return <div>
    <h3 className="text-sm font-semibold">Shipments</h3>
    {r.shipments.length === 0 && <p className="mt-1 text-sm text-muted-foreground">No shipments yet.</p>}
    <ul className="mt-2 space-y-3" aria-label="Shipments">{r.shipments.map(s => <ShipmentItem key={s.id} orderId={orderId} shipment={s} unshipped={unshipped} locked={locked} />)}</ul>
    {!locked && unshipped.length > 0 && <form onSubmit={onCreate} aria-label="New shipment" className="mt-3 flex flex-wrap items-end gap-2">
      <div className="min-w-[200px]"><Select label="From site" name="fulfilment_node_id" required placeholder="Choose" options={(sites.data ?? []).map(s => ({ value: s.id, label: s.name }))} /></div>
      <div className="min-w-[160px]"><Field label="Shipment reference" name="reference" required minLength={3} /></div>
      <SubmitButton busy={createShipment.isPending} variant="secondary">New shipment</SubmitButton>
    </form>}
    <ErrorNote error={createShipment.error} />
  </div>;
}

function ShipmentItem({ orderId, shipment, unshipped, locked }: { orderId: string; shipment: Shipment; unshipped: Receipt[]; locked: boolean }) {
  const c = useFulfilmentCommands(orderId);
  const [panel, setPanel] = useState<'none' | 'deliver' | 'cancel' | 'confirm'>('none');
  const d = shipment.delivery;
  const error = c.addToShipment.error ?? c.dispatch.error ?? c.deliver.error ?? c.cancelShipment.error ?? c.relayConfirmation.error;
  const done = () => setPanel('none');
  return <li data-shipment={shipment.status} className="rounded-md border border-white/[0.1] p-3 text-sm">
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-medium">{shipment.reference}</span><Pill tone={shipment.status === 'DELIVERED' ? 'good' : shipment.status === 'CANCELLED' ? 'neutral' : 'info'}>{humanize(shipment.status)}</Pill>
      {shipment.dispatched_at && <span className="text-xs text-muted-foreground">Dispatched {when(shipment.dispatched_at)}</span>}
    </div>
    {shipment.cancellation_reason && <p className="mt-1 text-xs text-muted-foreground">Cancelled: {shipment.cancellation_reason}</p>}
    {d && <div className="mt-2 space-y-1">
      <p>Delivered {kg(d.delivered_quantity_kg)} on {when(d.delivered_at)}{d.adjustments.length ? ` (recorded ${kg(d.recorded_quantity_kg)}, ${d.adjustments.length} correction(s))` : ''}</p>
      {d.confirmation ? <p data-confirmation={d.confirmation.channel}>
        <span className={d.confirmation.outcome === 'DISCREPANCY' ? 'text-warning' : 'text-success'}>{d.confirmation.outcome === 'DISCREPANCY' ? 'Discrepancy reported' : 'Confirmed'}: {kg(d.confirmation.confirmed_quantity_kg)}</span>
        <span className="block text-xs text-muted-foreground">{confirmationSource(d.confirmation)}</span>
      </p> : <p className="text-warning">Not confirmed by the buyer. The order cannot be completed until it is.</p>}
    </div>}
    {!locked && <div className="mt-2 flex flex-wrap gap-2">
      {shipment.status === 'OPEN' && unshipped.map(x => <button key={x.id} type="button" disabled={c.addToShipment.isPending} onClick={() => c.addToShipment.mutate({ shipmentId: shipment.id, received_sublot_id: x.id })}
        className="min-h-9 rounded-md border border-white/[0.14] px-3 text-xs">Add {x.farmer_name} {kg(x.accepted_kg)}</button>)}
      {shipment.status === 'OPEN' && <button type="button" disabled={c.dispatch.isPending} onClick={() => c.dispatch.mutate({ shipmentId: shipment.id })} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary">Dispatch</button>}
      {shipment.status === 'OPEN' && <button type="button" onClick={() => setPanel('cancel')} className="min-h-9 rounded-md px-3 text-xs text-muted-foreground">Cancel shipment</button>}
      {shipment.status === 'DISPATCHED' && <button type="button" onClick={() => setPanel('deliver')} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary">Record delivery</button>}
      {d && <button type="button" onClick={() => setPanel('confirm')} className="min-h-9 rounded-md border border-white/[0.14] px-3 text-xs">Record buyer&apos;s confirmation</button>}
    </div>}
    {panel === 'cancel' && <ReasonForm label="Why is this shipment cancelled?" busy={c.cancelShipment.isPending} submit="Cancel shipment"
      onSubmit={reason => c.cancelShipment.mutateAsync({ shipmentId: shipment.id, reason }).then(done, () => null)} />}
    {panel === 'deliver' && <form aria-label={`Delivery for ${shipment.reference}`} className="mt-2 grid gap-3 sm:grid-cols-3" onSubmit={async event => {
      event.preventDefault();
      const v = formValues(event.currentTarget);
      await c.deliver.mutateAsync({ shipmentId: shipment.id, ...v, delivered_at: localToIso(v.delivered_at ?? '') }).then(done, () => null);
    }}>
      <Field label="Delivered (kg)" name="delivered_quantity_kg" type="number" min="0" step="0.001" required />
      <Field label="Delivered at" name="delivered_at" type="datetime-local" required />
      <Field label="Proof of delivery" name="delivery_evidence_reference" />
      <div><SubmitButton busy={c.deliver.isPending}>Save delivery</SubmitButton></div>
    </form>}
    {panel === 'confirm' && d && <form aria-label={`Buyer confirmation for ${shipment.reference}`} className="mt-2 grid gap-3 sm:grid-cols-3" onSubmit={async event => {
      event.preventDefault();
      const v = formValues(event.currentTarget);
      await c.relayConfirmation.mutateAsync({ deliveryId: d.id, ...v, discrepancy: v.discrepancy === 'yes', stated_at: localToIso(v.stated_at ?? '') }).then(done, () => null);
    }}>
      <p className="text-xs text-muted-foreground sm:col-span-3">Record what the buyer&apos;s representative told you. It is shown as relayed by you, never as the buyer&apos;s own confirmation. The buyer can also confirm in their account.</p>
      <Field label="Confirmed quantity (kg)" name="confirmed_quantity_kg" type="number" min="0" step="0.001" max={Number(d.delivered_quantity_kg)} required />
      <Field label="Buyer's representative" name="buyer_representative" required minLength={2} />
      <Field label="How they told you" name="communication_channel" required minLength={2} placeholder="e.g. phone call, signed delivery note" />
      <Field label="When they said it" name="stated_at" type="datetime-local" required />
      <Field label="Your attestation" name="attestation" required minLength={3} placeholder="e.g. signed note held on file" />
      <Select label="Did they report a difference?" name="discrepancy" options={[{ value: 'no', label: 'No' }, { value: 'yes', label: 'Yes, a discrepancy' }]} />
      <div className="sm:col-span-2"><TextArea label="Note (required for a discrepancy)" name="note" /></div>
      <div className="self-end"><SubmitButton busy={c.relayConfirmation.isPending}>Save confirmation</SubmitButton></div>
    </form>}
    <ErrorNote error={error} />
  </li>;
}

function ReasonForm({ label, submit, busy, onSubmit }: { label: string; submit: string; busy: boolean; onSubmit: (reason: string) => unknown }) {
  return <form className="mt-2 flex flex-wrap items-end gap-2" aria-label={label} onSubmit={event => { event.preventDefault(); onSubmit(formValues(event.currentTarget).reason ?? ''); }}>
    <div className="min-w-[240px] flex-1"><Field label={label} name="reason" required minLength={3} /></div>
    <SubmitButton busy={busy} variant="secondary">{submit}</SubmitButton>
  </form>;
}

function Disputes({ orderId, r, locked }: { orderId: string; r: FulfilmentRecord; locked: boolean }) {
  const c = useFulfilmentCommands(orderId);
  const [raising, setRaising] = useState(false);
  return <div>
    <h3 className="text-sm font-semibold">Disputes</h3>
    {r.disputes.length === 0 && <p className="mt-1 text-sm text-muted-foreground">No disputes.</p>}
    <ul className="mt-2 space-y-2 text-sm" aria-label="Disputes">{r.disputes.map(d => <li key={d.id} className="rounded-md border border-white/[0.1] p-3">
      <div className="flex flex-wrap items-center gap-2"><Pill tone={d.status === 'OPEN' ? 'warn' : 'neutral'}>{humanize(d.status)}</Pill>
        <span className="text-xs text-muted-foreground">Raised by {d.party === 'BUYER' ? 'the buyer' : 'staff'} {when(d.created_at)}{d.quantity_kg ? ` · ${kg(d.quantity_kg)}` : ''}</span></div>
      <p className="mt-1">{d.description}</p>
      {d.resolution && <p className="mt-1 text-xs text-muted-foreground">Outcome: {d.resolution}</p>}
      {d.status === 'OPEN' && !locked && <ReasonForm label="Resolution" submit="Resolve" busy={c.resolveDispute.isPending}
        onSubmit={resolution => c.resolveDispute.mutate({ disputeId: d.id, outcome: 'RESOLVED', resolution })} />}
    </li>)}</ul>
    {!locked && <button type="button" onClick={() => setRaising(v => !v)} className="mt-2 min-h-9 rounded-md px-3 text-xs text-muted-foreground">Raise a discrepancy</button>}
    {raising && <ReasonForm label="What is wrong?" submit="Raise" busy={c.raiseDispute.isPending}
      onSubmit={description => c.raiseDispute.mutateAsync({ description }).then(() => setRaising(false), () => null)} />}
    <ErrorNote error={c.resolveDispute.error ?? c.raiseDispute.error} />
  </div>;
}

function Reconciliations({ orderId, r, locked }: { orderId: string; r: FulfilmentRecord; locked: boolean }) {
  const c = useFulfilmentCommands(orderId);
  const latest = r.reconciliations.at(-1);
  return <div>
    <h3 className="text-sm font-semibold">Reconciliation</h3>
    {r.reconciliations.length === 0 && <p className="mt-1 text-sm text-muted-foreground">Not reconciled yet.</p>}
    <ol className="mt-2 space-y-2 text-sm" aria-label="Reconciliation versions">{r.reconciliations.map(v => <li key={v.id} className="rounded-md border border-white/[0.1] p-3">
      <div className="flex flex-wrap items-center gap-2"><span className="font-medium">Version {v.version}</span>
        <Pill tone={v.status === 'EFFECTIVE' ? 'good' : v.status === 'PENDING_REVIEW' ? 'warn' : 'neutral'}>{v.status === 'PENDING_REVIEW' ? 'Waiting for a second reviewer' : humanize(v.status)}</Pill>
        {v.legacy && <Pill>Migrated record</Pill>}<span className="text-xs text-muted-foreground">{when(v.created_at)}</span></div>
      {v.reason && <p className="mt-1 text-xs text-muted-foreground">Correction reason: {v.reason}</p>}
      <p className="mt-1 text-xs">Received {kg(v.figures.received_kg)}, accepted {kg(v.figures.accepted_kg)}, delivered {kg(v.figures.delivered_kg)}, buyer-confirmed {kg(v.figures.buyer_confirmed_kg)}</p>
      {v.status === 'PENDING_REVIEW' && !locked && <div className="mt-2 flex gap-2">
        <button type="button" onClick={() => c.review.mutate({ reconciliationId: v.id, approve: true, note: 'Checked against the records' })} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary">Approve correction</button>
        <button type="button" onClick={() => c.review.mutate({ reconciliationId: v.id, approve: false, note: 'Does not match the records' })} className="min-h-9 rounded-md px-3 text-xs text-muted-foreground">Reject</button>
      </div>}
    </li>)}</ol>
    {!locked && latest?.status !== 'PENDING_REVIEW' && <form aria-label="Reconcile" className="mt-2 flex flex-wrap items-end gap-2" onSubmit={event => { event.preventDefault(); c.reconcile.mutate(formValues(event.currentTarget)); }}>
      {latest && <div className="min-w-[240px] flex-1"><Field label="Reason for the correction" name="reason" required minLength={3} /></div>}
      <SubmitButton busy={c.reconcile.isPending} variant="secondary">{latest ? 'Record a corrected version' : 'Reconcile'}</SubmitButton>
    </form>}
    <ErrorNote error={c.reconcile.error ?? c.review.error} />
  </div>;
}

function Close({ orderId, r }: { orderId: string; r: FulfilmentRecord }) {
  const { close } = useFulfilmentCommands(orderId);
  if (!r.effective_reconciliation_version) return null;
  return <div className="rounded-md border border-white/[0.1] p-3">
    <h3 className="text-sm font-semibold">Close the order</h3>
    {r.completion.can_complete
      ? <p className="mt-1 text-sm">Every obligation is delivered and confirmed by the buyer with no open dispute.</p>
      : <ul className="mt-1 list-disc pl-5 text-sm text-warning" aria-label="Why it cannot be completed">{r.completion.blockers.map(b => <li key={b}>{b}</li>)}</ul>}
    <p className="mt-1 text-xs text-muted-foreground">Closing releases only reservations that were never received. Open standby is released and open requests are withdrawn; the released stock must be confirmed again before it is offered to another order.</p>
    <div className="mt-2 flex flex-wrap items-end gap-2">
      {r.completion.can_complete && <button type="button" disabled={close.isPending} onClick={() => close.mutate({ accept_variance: false })} className="min-h-11 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground">Close as completed</button>}
      <form aria-label="Close with an accepted variance" className="flex flex-wrap items-end gap-2" onSubmit={event => { event.preventDefault(); close.mutate({ accept_variance: true, reason: formValues(event.currentTarget).reason }); }}>
        <div className="min-w-[260px]"><Field label="Documented reason for accepting the difference" name="reason" required minLength={3} hint="Procurement managers and organization administrators only." /></div>
        <SubmitButton busy={close.isPending} variant="secondary">Close with variance</SubmitButton>
      </form>
    </div>
    <ErrorNote error={close.error} />
  </div>;
}
