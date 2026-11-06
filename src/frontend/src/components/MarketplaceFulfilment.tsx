'use client';

import { FormEvent, useRef, useState } from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { useIdentity } from '@/hooks/useIdentity';

type Offer = {
  id: string; offer_id: string; requirement_id: string; production_lot_id: string;
  buyer_name: string; farmer_name: string; parish: string; crop: string; grade: string;
  delivery_window_start: string; delivery_window_end: string;
  accepted_offer_kg: string; received_kg: string; awaiting_receipt_kg: string;
  inspected_accepted_kg: string; inspected_rejected_kg: string; pending_inspection_kg: string;
};
type Receipt = {
  id: string; offer_id: string; fulfilment_node_id: string; fulfilment_node_name: string;
  received_quantity_kg: string; received_at: string; receipt_evidence_reference: string;
  inspection_status: string; accepted_quantity_kg: string; rejected_quantity_kg: string;
  assigned_grade: string | null; rejection_reason: string | null;
  inspection_evidence_reference: string | null; inspected_at: string | null;
  evidence_verified: boolean;
};
type FulfilmentData = {
  scope: string; as_of: string;
  totals: { accepted_offer_kg: string; received_kg: string; awaiting_receipt_kg: string;
    inspected_accepted_kg: string; inspected_rejected_kg: string; pending_inspection_kg: string };
  offers_count: number; items: Offer[]; receipts_count: number; receipts: Receipt[];
  truncated: boolean; note: string;
};
type Node = { id: string; name: string; node_type: string; parish: string };
const kg = (value: string) => `${Number(value).toLocaleString('en-JM', { maximumFractionDigits: 3 })} kg`;
const human = (value: string) => value.replace(/_/g, ' ');
const safeDate = (value: string) => {
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? new Intl.DateTimeFormat('en-JM', { dateStyle: 'medium', timeStyle: 'short' }).format(d) : 'Unknown';
};

export function MarketplaceFulfilment() {
  const identity = useIdentity();
  const client = useQueryClient();
  const ledger = useQuery({
    queryKey: ['marketplace', 'fulfilment'], queryFn: () => apiFetch<FulfilmentData>('/marketplace/fulfilment'),
    retry: false, refetchInterval: 30_000,
  });
  const nodes = useQuery({
    queryKey: ['marketplace', 'fulfilment', 'nodes'],
    queryFn: () => apiFetch<{ items: Node[] }>('/marketplace/fulfilment/nodes'), retry: false,
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const commandKeys = useRef<Record<string, string>>({});
  const role = identity.data?.active_role;
  const canReceive = role === 'WAREHOUSE_OPERATOR' || role === 'PLATFORM_ADMIN';
  const canCreateNode = role === 'ORGANIZATION_ADMIN' || role === 'PLATFORM_ADMIN';

  async function perform(id: string, path: string, payload: object, message: string) {
    setBusy(id); setError(''); setSuccess('');
    const key = commandKeys.current[id] ?? (commandKeys.current[id] = `marketplace-${crypto.randomUUID()}`);
    try {
      await apiFetch(path, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(payload) });
      delete commandKeys.current[id];
      await client.invalidateQueries({ queryKey: ['marketplace', 'fulfilment'] });
      setSuccess(message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Request failed. No state was assumed.');
    } finally { setBusy(null); }
  }

  function receive(event: FormEvent<HTMLFormElement>, offerId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    void perform(`receive-${offerId}`, `/marketplace/fulfilment/offers/${offerId}/receipts`, {
      fulfilment_node_id: String(fields.get('node_id')),
      received_quantity_kg: String(fields.get('quantity')),
      receipt_evidence_reference: String(fields.get('reference')),
    }, 'Receipt recorded. Inspection is still pending.');
  }

  function inspect(event: FormEvent<HTMLFormElement>, receiptId: string) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const accepted = String(fields.get('accepted'));
    const rejected = String(fields.get('rejected'));
    void perform(`inspect-${receiptId}`, `/marketplace/fulfilment/receipts/${receiptId}/inspect`, {
      accepted_quantity_kg: accepted,
      rejected_quantity_kg: rejected,
      assigned_grade: Number(accepted) > 0 ? String(fields.get('grade')) : null,
      rejection_reason: Number(rejected) > 0 ? String(fields.get('reason')) : null,
      inspection_evidence_reference: String(fields.get('reference')),
    }, 'Inspection saved. Accepted and rejected quantities are now recorded.');
  }

  async function createNode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy('create-node'); setError(''); setSuccess('');
    try {
      await apiFetch('/marketplace/fulfilment/nodes', { method: 'POST', body: JSON.stringify({
        name: String(fields.get('name')), node_type: String(fields.get('node_type')),
        parish: String(fields.get('parish')),
      }) });
      await client.invalidateQueries({ queryKey: ['marketplace', 'fulfilment', 'nodes'] });
      form.reset();
      setSuccess('Receiving location added. Warehouse operators can now select it.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create receiving location.');
    } finally { setBusy(null); }
  }

  const totals = ledger.data?.totals;
  const label = ledger.data?.scope === 'buyer' ? 'Your accepted supplier commitments' :
    ledger.data?.scope === 'farmer' ? 'Your accepted offers and receiving history' :
    'Accepted offers across your organization';

  return <AppShell programme="Marketplace fulfilment">
    <main className="mx-auto max-w-[1380px] space-y-7 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="section-eyebrow">Physical operations</p><h1 className="mt-2 text-3xl font-semibold">Fulfilment Center</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Track actual receipts and inspections against accepted marketplace farmer offers. A commitment is not a delivery.</p></div>
        <button type="button" onClick={() => { void ledger.refetch(); void nodes.refetch(); }} disabled={ledger.isFetching || nodes.isFetching}
          className="min-h-10 rounded-md border border-white/20 px-4 text-sm font-semibold hover:bg-white/[0.04] disabled:opacity-50">Refresh</button>
      </header>

      {identity.isError && <p role="alert" className="rounded-lg border border-red-500/30 p-4 text-sm text-red-300">Account information unavailable: {identity.error.message}</p>}
      {ledger.isLoading && <p role="status" className="py-12 text-muted-foreground">Loading accepted offers and recorded receipts…</p>}
      {ledger.isError && <section role="alert" className="rounded-lg border border-red-500/30 p-5"><h2 className="font-semibold">Fulfilment data unavailable</h2><p className="mt-2 text-sm text-red-300">{ledger.error.message}</p><p className="mt-2 text-xs text-muted-foreground">Confirm the marketplace fulfilment migration and authenticated backend route are installed.</p></section>}
      {error && <p role="alert" className="rounded-md border border-red-500/40 px-4 py-3 text-sm text-red-300">{error}</p>}
      {success && <p role="status" className="rounded-md border border-emerald-500/30 px-4 py-3 text-sm text-emerald-300">{success}</p>}

      {ledger.data && <>
        <div><p className="text-sm font-medium">{label}</p><p className="mt-1 text-xs text-muted-foreground">As of {safeDate(ledger.data.as_of)} · {ledger.data.offers_count} accepted offers · {ledger.data.receipts_count} receiving records</p></div>
        <section aria-label="Marketplace fulfilment totals" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {([
            ['Committed', totals?.accepted_offer_kg], ['Received', totals?.received_kg],
            ['Not received', totals?.awaiting_receipt_kg], ['Accepted after inspection', totals?.inspected_accepted_kg],
            ['Rejected', totals?.inspected_rejected_kg], ['Pending inspection', totals?.pending_inspection_kg],
          ] as const).map(([name,value]) => <div key={name} className="operational-panel p-4"><p className="text-xs text-muted-foreground">{name}</p><p className="mt-2 text-lg font-semibold tabular-nums">{value == null ? 'Unavailable' : kg(value)}</p></div>)}
        </section>
        <p className="rounded-md border border-amber-500/20 bg-amber-500/[0.04] px-4 py-3 text-xs leading-5 text-muted-foreground">{ledger.data.note}</p>
        {ledger.data.truncated && <p role="status" className="text-sm text-amber-300">Showing the first 100 offers and receipts. Totals cover the complete authorized result set.</p>}

        {canCreateNode && <section className="operational-panel p-5"><h2 className="text-lg font-semibold">Register a receiving location</h2><p className="mt-1 text-xs text-muted-foreground">Organization administrators can configure a depot or inspection location for warehouse receiving.</p>
          <form onSubmit={createNode} className="mt-4 grid gap-3 sm:grid-cols-[1fr_160px_160px_auto] sm:items-end">
            <label className="grid gap-1 text-xs">Location name<input name="name" minLength={3} required placeholder="Kingston Collection Depot" className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
            <label className="grid gap-1 text-xs">Type<select name="node_type" className="h-10 rounded border border-white/20 bg-background px-3 text-sm"><option value="WAREHOUSE">Warehouse</option><option value="COLLECTION">Collection</option><option value="INSPECTION">Inspection</option></select></label>
            <label className="grid gap-1 text-xs">Parish<input name="parish" minLength={2} required placeholder="Kingston" className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
            <button disabled={busy != null} className="h-10 rounded bg-primary px-4 text-xs font-semibold text-primary-foreground disabled:opacity-50">Add location</button>
          </form></section>}

        <section className="space-y-4"><div className="flex flex-wrap items-baseline justify-between gap-3"><h2 className="text-xl font-semibold">Accepted farmer offers</h2><Link href="/demand" className="text-sm font-medium text-primary underline underline-offset-4">Demand overview</Link></div>
          {!ledger.data.items.length && <p className="operational-panel p-8 text-sm text-muted-foreground">No accepted marketplace offers in your permitted scope. Pending offers do not qualify for receiving. <Link href="/demand/demo-orders" className="text-primary underline">Open procurement requests</Link>.</p>}
          <div className="grid gap-4 lg:grid-cols-2">{ledger.data.items.map(offer => <article key={offer.id} className="operational-panel space-y-4 p-5">
            <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-lg font-semibold">{human(offer.crop)} · Grade {offer.grade}</h3><p className="mt-1 text-xs text-muted-foreground">{offer.farmer_name} · {offer.parish} → {offer.buyer_name}</p></div><span className="rounded border border-emerald-500/30 px-2 py-1 text-[10px] text-emerald-300">ACCEPTED OFFER</span></div>
            <div className="grid grid-cols-3 gap-3 text-sm"><div><p className="text-xs text-muted-foreground">Committed</p><p className="font-semibold">{kg(offer.accepted_offer_kg)}</p></div><div><p className="text-xs text-muted-foreground">Received</p><p className="font-semibold">{kg(offer.received_kg)}</p></div><div><p className="text-xs text-muted-foreground">To receive</p><p className="font-semibold">{kg(offer.awaiting_receipt_kg)}</p></div></div>
            <div className="h-1.5 overflow-hidden rounded bg-white/10"><div className="h-full bg-emerald-500" style={{ width: `${Number(offer.accepted_offer_kg) > 0 ? Math.min(100, 100 * Number(offer.received_kg) / Number(offer.accepted_offer_kg)) : 0}%` }} /></div>
            <p className="text-xs text-muted-foreground">Inspected: {kg(offer.inspected_accepted_kg)} accepted · {kg(offer.inspected_rejected_kg)} rejected · {kg(offer.pending_inspection_kg)} pending</p>
            {canReceive && Number(offer.awaiting_receipt_kg) > 0 && <form onSubmit={event => receive(event, offer.offer_id)} className="space-y-3 border-t border-white/10 pt-4">
              <h4 className="font-medium">Record physical receipt</h4>
              {nodes.isError && <p role="alert" className="text-xs text-red-300">Unable to load receiving locations: {nodes.error.message}</p>}
              {nodes.data?.items.length ? <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs">Receiving location<select name="node_id" required className="h-10 rounded border border-white/20 bg-background px-3 text-sm">{nodes.data.items.map(node => <option key={node.id} value={node.id}>{node.name} · {node.parish}</option>)}</select></label>
                <label className="grid gap-1 text-xs">Received quantity (kg)<input name="quantity" type="number" min="0.001" step="0.001" max={offer.awaiting_receipt_kg} defaultValue={offer.awaiting_receipt_kg} required className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
                <label className="grid gap-1 text-xs sm:col-span-2">Receipt docket / evidence reference<input name="reference" required minLength={3} maxLength={500} placeholder="DOCKET-2026-001" className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
                <button className="h-10 rounded bg-primary px-4 text-xs font-semibold text-primary-foreground disabled:opacity-50 sm:col-span-2" disabled={busy != null}>Record receipt</button>
              </div> : <p className="text-xs text-amber-300">No active receiving location is registered. Ask an organization administrator to add one before recording stock.</p>}
            </form>}
            <p className="break-all font-mono text-[10px] text-muted-foreground">Offer {offer.id.slice(0,13)}… · Lot {offer.production_lot_id.slice(0,13)}…</p>
          </article>)}</div>
        </section>

        <section className="space-y-4"><h2 className="text-xl font-semibold">Receipt & inspection ledger</h2>
          {!ledger.data.receipts.length && <p className="operational-panel p-6 text-sm text-muted-foreground">No physical receipts have been recorded yet.</p>}
          <div className="grid gap-4 lg:grid-cols-2">{ledger.data.receipts.map(receipt => <article key={receipt.id} className="operational-panel space-y-3 p-5">
            <div className="flex flex-wrap justify-between gap-3"><div><h3 className="font-semibold">{receipt.fulfilment_node_name}</h3><p className="mt-1 text-xs text-muted-foreground">Received {safeDate(receipt.received_at)}</p></div><span className="h-fit rounded border border-white/20 px-2 py-1 text-[10px]">{human(receipt.inspection_status)}</span></div>
            <p className="text-sm">Received <strong>{kg(receipt.received_quantity_kg)}</strong> · Accepted <strong>{kg(receipt.accepted_quantity_kg)}</strong> · Rejected <strong>{kg(receipt.rejected_quantity_kg)}</strong></p>
            <p className="text-xs text-muted-foreground">Receipt evidence reference: {receipt.receipt_evidence_reference} · Not independently verified</p>
            {receipt.inspection_evidence_reference && <p className="text-xs text-muted-foreground">Inspection evidence reference: {receipt.inspection_evidence_reference} · Not independently verified</p>}
            {receipt.rejection_reason && <p className="text-xs text-amber-300">Rejection reason: {receipt.rejection_reason}</p>}
            {canReceive && receipt.inspection_status === 'PENDING_INSPECTION' && <form onSubmit={event => inspect(event, receipt.id)} className="space-y-3 border-t border-white/10 pt-4"><h4 className="font-medium">Inspect received produce</h4>
              <p className="text-xs text-muted-foreground">Accepted + rejected must equal the entire {kg(receipt.received_quantity_kg)} received amount.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs">Accepted (kg)<input name="accepted" type="number" min="0" max={receipt.received_quantity_kg} step="0.001" defaultValue={receipt.received_quantity_kg} required className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
                <label className="grid gap-1 text-xs">Rejected (kg)<input name="rejected" type="number" min="0" max={receipt.received_quantity_kg} step="0.001" defaultValue="0" required className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
                <label className="grid gap-1 text-xs">Accepted grade<select name="grade" className="h-10 rounded border border-white/20 bg-background px-3 text-sm"><option value="A">Grade A</option><option value="B">Grade B</option></select></label>
                <label className="grid gap-1 text-xs">Rejection reason (when rejecting)<input name="reason" maxLength={200} placeholder="e.g. quality defects" className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
                <label className="grid gap-1 text-xs sm:col-span-2">Inspection evidence reference<input name="reference" minLength={3} maxLength={500} required placeholder="CHECK-2026-001" className="h-10 rounded border border-white/20 bg-background px-3 text-sm" /></label>
                <button disabled={busy != null} className="h-10 rounded bg-primary px-4 text-xs font-semibold text-primary-foreground disabled:opacity-50 sm:col-span-2">Save inspection</button>
              </div></form>}
            <p className="break-all font-mono text-[10px] text-muted-foreground">Receipt {receipt.id}</p>
          </article>)}</div>
        </section>
      </>}
    </main>
  </AppShell>;
}
