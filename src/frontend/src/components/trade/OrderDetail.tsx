'use client';

import { useEffect, useState } from 'react';
import { rememberActiveOrder } from '@/hooks/useActiveRequirement';
import {
  type Allocation, type Order, useCancelOrder, useOrder, useOrderHistory, useOrderSupply, usePlanOrder, useRespond, useSetDeadline,
  useSolicit, useUpdateOrder, useWithdraw,
} from '@/hooks/useTrade';
import { ExceptionList } from '@/components/trade/ExceptionList';
import {
  ErrorNote, Field, LoadState, Pill, Select, SubmitButton, SupplyStatePill, TextArea, TradePage, formValues, humanize, kg,
} from '@/components/trade/TradeUi';

export function OrderDetail({ id }: { id: string }) {
  const order = useOrder(id);
  useEffect(() => { rememberActiveOrder(id); }, [id]);
  const title = order.data ? `${order.data.crop.replace(/_/g, ' ')} for ${order.data.buyer_name}` : 'Order';
  return <TradePage eyebrow="Order" title={title} description="Terms, supplier commitments and the full history of this order."
    crumbs={[{ label: 'Orders', href: '/orders' }, { label: title }]}>
    <LoadState query={order}>
      {order.data && <div className="space-y-6">
        <Terms order={order.data} />
        <Supply order={order.data} />
        <section aria-labelledby="order-exceptions" className="operational-panel p-5">
          <h2 id="order-exceptions" className="text-base font-semibold">Needs attention</h2>
          <ExceptionList requirementId={id} empty="No open supply exceptions for this order." />
        </section>
        <History id={id} />
      </div>}
    </LoadState>
  </TradePage>;
}

function Terms({ order }: { order: Order }) {
  const [editing, setEditing] = useState(false);
  const update = useUpdateOrder(order.id);
  const cancel = useCancelOrder(order.id);
  const cancelled = order.lifecycle_status === 'CANCELLED';
  const editable = !cancelled && order.plan_version === 0;

  async function onEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    const changed = Object.fromEntries(Object.entries(values).filter(([key, value]) => String(order[key as keyof Order] ?? '') !== value));
    const ok = await update.mutateAsync({ expected_version: order.version, ...changed }).then(() => true, () => false);
    if (ok) setEditing(false);
  }

  async function onCancel(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await cancel.mutateAsync({ reason: formValues(event.currentTarget).reason ?? '' }).catch(() => null);
  }

  const rows: Array<[string, string]> = [
    ['Buyer', order.buyer_name ?? '—'], ['Crop and grade', `${order.crop.replace(/_/g, ' ')} · Grade ${order.grade}`],
    ['Required', kg(order.required_quantity_kg)], ['Delivery window', `${order.delivery_window_start} → ${order.delivery_window_end}`],
    ['Product form', order.product_form ?? '—'], ['Origin', order.origin ?? '—'], ['Destination', order.destination ?? '—'],
    ['Delivery terms', order.delivery_terms ?? '—'], ['Currency', order.currency ?? '—'], ['Notes', order.notes ?? '—'],
  ];

  return <section aria-labelledby="terms" className="operational-panel p-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="terms" className="text-base font-semibold">Order terms</h2>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={cancelled ? 'neutral' : 'info'}>{cancelled ? 'Cancelled' : humanize(order.lifecycle_status)}</Pill>
        <span className="text-xs text-muted-foreground">Version {order.version}</span>
        {editable && !editing && <button type="button" className="min-h-11 rounded-md border border-white/[0.14] px-3 text-sm" onClick={() => setEditing(true)}>Edit terms</button>}
      </div>
    </div>
    {cancelled && <p className="mt-2 text-sm text-muted-foreground">Cancelled: {order.cancellation_reason}</p>}
    {!editable && !cancelled && <p className="mt-2 text-xs text-muted-foreground">Supply planning has started, so terms are locked. Quantity changes go through a recorded buyer change.</p>}
    {!editing ? <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {rows.map(([label, value]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd>{value}</dd></div>)}
    </dl> : <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={onEdit} aria-label="Edit order terms">
      <Field label="Required quantity (kg)" name="required_quantity_kg" type="number" min="0.001" step="0.001" defaultValue={Number(order.required_quantity_kg)} required />
      <Field label="Delivery from" name="delivery_window_start" type="date" defaultValue={order.delivery_window_start} required />
      <Field label="Delivery to" name="delivery_window_end" type="date" defaultValue={order.delivery_window_end} required />
      <Field label="Product form" name="product_form" defaultValue={order.product_form ?? ''} />
      <Field label="Destination" name="destination" defaultValue={order.destination ?? ''} />
      <Field label="Delivery terms" name="delivery_terms" defaultValue={order.delivery_terms ?? ''} />
      <div className="sm:col-span-2"><TextArea label="Notes" name="notes" defaultValue={order.notes ?? ''} /></div>
      <div className="flex gap-2 sm:col-span-2">
        <SubmitButton busy={update.isPending}>Save changes</SubmitButton>
        <button type="button" className="min-h-11 rounded-md px-3 text-sm text-muted-foreground" onClick={() => { update.reset(); setEditing(false); }}>Discard</button>
      </div>
      <div className="sm:col-span-2"><ErrorNote error={update.error} /></div>
    </form>}
    {!cancelled && <details className="mt-4">
      <summary className="cursor-pointer text-sm text-muted-foreground">Cancel this order</summary>
      <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={onCancel} aria-label="Cancel order">
        <div className="min-w-[240px] flex-1"><Field label="Reason" name="reason" required minLength={3} /></div>
        <SubmitButton busy={cancel.isPending} variant="danger">Cancel order</SubmitButton>
      </form>
      <ErrorNote error={cancel.error} />
    </details>}
  </section>;
}

function Supply({ order }: { order: Order }) {
  const supply = useOrderSupply(order.id);
  const plan = usePlanOrder(order.id);
  const cancelled = order.lifecycle_status === 'CANCELLED';
  const s = supply.data;
  const figures: Array<[string, string | undefined, string]> = s ? [
    ['Committed', s.committed_quantity_kg, 'Supplier acceptance recorded. Stays recorded even if the supplier later reports less.'],
    ['Currently covered', s.currently_covered_kg, 'Committed quantity the suppliers\u2019 latest capacity reports still support'],
    ['Exposed', s.exposed_kg, 'Committed quantity the suppliers\u2019 latest capacity reports no longer support'],
    ['Authorized standby', s.standby_quantity_kg, 'Supplier authorization recorded; not buyer coverage'],
    ['Standby uncovered', s.standby_uncovered_kg, 'Authorized standby the supplier\u2019s reported capacity no longer supports'],
    ['Expired standby', s.expired_standby_kg, 'Standby authorizations past their end date; no longer usable'],
    ['Awaiting supplier', s.solicited_quantity_kg, 'Asked, no answer yet'],
    ['Proposed', s.proposed_quantity_kg, 'Suggested by the planner; not yet asked'],
    ['Not yet committed', s.unfilled_quantity_kg, 'Required minus committed. Exposed quantity is shown separately and is not included here.'],
  ] : [];
  return <section aria-labelledby="supply" className="operational-panel p-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="supply" className="text-base font-semibold">Supply</h2>
      {s && <Pill tone={s.supply_health === 'COVERED' ? 'good' : s.supply_health === 'UNPLANNED' ? 'info' : 'warn'}>{healthLabel(s.supply_health, order.plan_version)}</Pill>}
    </div>
    <LoadState query={supply}>
      {s && <>
        <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5" aria-label="Supply states">
          {figures.map(([label, value, hint]) => <div key={label} className={`rounded-md border p-3 ${label === 'Exposed' && Number(value) > 0 ? 'border-destructive/60' : 'border-white/[0.07]'}`} title={hint}>
            <dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold" data-figure={label}>{kg(value)}</dd>
          </div>)}
        </dl>
        {Number(s.exposed_kg) > 0 && <p role="alert" className="mt-3 text-sm text-destructive">{kg(s.exposed_kg)} of the committed supply is no longer backed by the suppliers&apos; reported capacity. The commitments remain on record; nothing has been activated automatically.</p>}
        {Number(s.unsupported_legacy_kg) > 0 && <p className="mt-3 text-sm text-destructive">{kg(s.unsupported_legacy_kg)} was recorded before supplier consent was captured and does not count as committed.</p>}
        {order.plan_version === 0 && !cancelled && <div className="mt-4">
          <button type="button" disabled={plan.isPending} onClick={() => plan.mutate()} className="min-h-11 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60">
            {plan.isPending ? 'Proposing…' : 'Propose supply'}
          </button>
          <p className="mt-1 text-xs text-muted-foreground">The planner suggests suppliers from your declared lots. Nothing is reserved or committed until each supplier accepts.</p>
          <ErrorNote error={plan.error} />
        </div>}
        {s.allocations.length > 0 && <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm" aria-label="Supplier allocations">
            <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-2">Supplier</th><th>Role</th><th className="text-right">Quantity</th><th className="pl-3">State</th><th className="pl-3">Action</th></tr></thead>
            <tbody className="divide-y divide-white/[0.07]">
              {s.allocations.map(allocation => <AllocationRow key={allocation.id} orderId={order.id} allocation={allocation} locked={cancelled} />)}
            </tbody>
          </table>
        </div>}
      </>}
    </LoadState>
  </section>;
}

/** UNPLANNED after a proposal means suppliers are still being asked; say so rather than "Unplanned". */
export function healthLabel(health: string, planVersion: number) {
  return health === 'UNPLANNED' && planVersion > 0 ? 'Assembling supply' : humanize(health);
}

function AllocationRow({ orderId, allocation, locked }: { orderId: string; allocation: Allocation; locked: boolean }) {
  const [responding, setResponding] = useState(false);
  const [rescheduling, setRescheduling] = useState(false);
  const solicit = useSolicit(orderId);
  const withdraw = useWithdraw(orderId);
  const open = allocation.status === 'PROPOSED' || allocation.status === 'SOLICITED';
  const exposed = Number(allocation.exposed_kg ?? 0) > 0;
  const label = `${allocation.farmer_name} ${allocation.role === 'STANDBY' ? 'standby' : 'commitment'}`;
  return <>
    <tr data-allocation={allocation.id}>
      <td className="py-2">{allocation.farmer_name}<span className="block text-xs text-muted-foreground">{allocation.parish}</span></td>
      <td>{allocation.role === 'STANDBY' ? 'Standby' : 'Commitment'}</td>
      <td className="text-right">{kg(allocation.quantity_kg)}{exposed && <span className="block text-[11px] text-destructive" data-exposed={allocation.exposed_kg ?? ''}>{kg(allocation.exposed_kg)} exposed</span>}</td>
      <td className="pl-3"><SupplyStatePill status={allocation.status} consent={allocation.consent_status} />
        {allocation.status === 'SOLICITED' && allocation.response_due_at && <span className="block text-[11px] text-muted-foreground">Reply by {formatDue(allocation.response_due_at)}{allocation.reminder_sent_at ? ' · reminder sent' : ''}</span>}
        {allocation.status === 'EXPIRED' && allocation.role === 'COMMITTED' && <span className="block text-[11px] text-muted-foreground">No reply by the deadline. Not treated as acceptance or refusal.</span>}
        {allocation.activation_conditions && <span className="block text-[11px] text-muted-foreground">If: {allocation.activation_conditions}{allocation.authorization_valid_until ? ` (until ${allocation.authorization_valid_until})` : ''}</span>}
      </td>
      <td className="pl-3">{!locked && allocation.status === 'EXPIRED' && allocation.role === 'COMMITTED' && <button type="button" aria-label={`Ask ${label} again`} disabled={solicit.isPending} onClick={() => solicit.mutate({ allocationId: allocation.id })} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary disabled:opacity-60">Ask again</button>}
        {!locked && open && <div className="flex flex-wrap gap-2">
        {allocation.status === 'PROPOSED' && <button type="button" aria-label={`Ask ${label}`} disabled={solicit.isPending} onClick={() => solicit.mutate({ allocationId: allocation.id })} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary disabled:opacity-60">Ask supplier</button>}
        {allocation.status === 'SOLICITED' && <button type="button" aria-label={`Record response for ${label}`} onClick={() => setResponding(v => !v)} className="min-h-9 rounded-md border border-primary/60 px-3 text-xs text-primary">Record response</button>}
        {allocation.status === 'SOLICITED' && <button type="button" aria-label={`Change reply deadline for ${label}`} onClick={() => setRescheduling(v => !v)} className="min-h-9 rounded-md px-3 text-xs text-muted-foreground">Change deadline</button>}
        <button type="button" aria-label={`Withdraw ${label}`} disabled={withdraw.isPending} onClick={() => withdraw.mutate({ allocationId: allocation.id, reason: 'Withdrawn by coordinator' })} className="min-h-9 rounded-md px-3 text-xs text-muted-foreground disabled:opacity-60">Withdraw</button>
      </div>}<ErrorNote error={solicit.error ?? withdraw.error} /></td>
    </tr>
    {responding && allocation.status === 'SOLICITED' && <tr><td colSpan={5} className="pb-4"><ResponseForm orderId={orderId} allocation={allocation} onDone={() => setResponding(false)} /></td></tr>}
    {rescheduling && allocation.status === 'SOLICITED' && <tr><td colSpan={5} className="pb-4"><DeadlineForm orderId={orderId} allocation={allocation} onDone={() => setRescheduling(false)} /></td></tr>}
  </>;
}

export function formatDue(value: string) {
  return new Date(value).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' });
}

/** `datetime-local` gives wall-clock time with no zone; send it as an absolute instant. */
export function localToIso(value: string) {
  return new Date(value).toISOString();
}

function DeadlineForm({ orderId, allocation, onDone }: { orderId: string; allocation: Allocation; onDone: () => void }) {
  const deadline = useSetDeadline(orderId);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    const ok = await deadline.mutateAsync({ allocationId: allocation.id, respond_by: localToIso(values.respond_by ?? ''), reason: values.reason ?? '' }).then(() => true, () => false);
    if (ok) onDone();
  }

  return <form onSubmit={onSubmit} aria-label={`Reply deadline for ${allocation.farmer_name}`} className="grid gap-3 rounded-md border border-white/[0.1] p-4 sm:grid-cols-2">
    <p className="text-xs text-muted-foreground sm:col-span-2">The change and your reason are recorded in the order history. A missed deadline never counts as the supplier&apos;s answer.</p>
    <Field label="New reply deadline" name="respond_by" type="datetime-local" required />
    <Field label="Reason for the change" name="reason" required minLength={3} />
    <div className="sm:col-span-2"><SubmitButton busy={deadline.isPending}>Save deadline</SubmitButton><ErrorNote error={deadline.error} /></div>
  </form>;
}

function ResponseForm({ orderId, allocation, onDone }: { orderId: string; allocation: Allocation; onDone: () => void }) {
  const respond = useRespond(orderId);
  const [decision, setDecision] = useState('ACCEPTED');
  const standby = allocation.role === 'STANDBY';

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const ok = await respond.mutateAsync({ allocationId: allocation.id, ...formValues(event.currentTarget) }).then(() => true, () => false);
    if (ok) onDone();
  }

  return <form onSubmit={onSubmit} aria-label={`Supplier response for ${allocation.farmer_name}`} className="grid gap-3 rounded-md border border-white/[0.1] p-4 sm:grid-cols-2">
    <p className="text-xs text-muted-foreground sm:col-span-2">Record what {allocation.farmer_name} told you. This is stored as their decision, relayed by you, with your attestation.</p>
    <Select label="Supplier decision" name="decision" value={decision} onChange={event => setDecision(event.target.value)} required
      options={[{ value: 'ACCEPTED', label: standby ? 'Authorizes standby' : 'Accepts' }, { value: 'DECLINED', label: 'Declines' }]} />
    <Field label="How the supplier told you" name="attestation_method" required minLength={3} placeholder="e.g. phone call, signed form" />
    <Field label="Evidence reference" name="evidence_reference" placeholder="e.g. call log entry" />
    {decision === 'ACCEPTED' && <Field label="Accepted quantity (kg)" name="accepted_quantity_kg" type="number" min="0.001" step="0.001" max={Number(allocation.quantity_kg)} placeholder={String(Number(allocation.quantity_kg))} hint="Leave blank to accept the full quantity." />}
    {decision === 'ACCEPTED' && standby && <>
      <div className="sm:col-span-2"><TextArea label="Activation conditions" name="activation_conditions" required placeholder="When the supplier agrees to be called on" /></div>
      <Field label="Authorization valid until" name="valid_until" type="date" />
    </>}
    <div className="sm:col-span-2"><SubmitButton busy={respond.isPending}>Save supplier response</SubmitButton><ErrorNote error={respond.error} /></div>
  </form>;
}

function History({ id }: { id: string }) {
  const history = useOrderHistory(id);
  return <section aria-labelledby="history" className="operational-panel p-5">
    <h2 id="history" className="text-base font-semibold">History</h2>
    <LoadState query={history}>
      <ol className="mt-3 space-y-2 text-sm" aria-label="Order history">
        {history.data?.map(event => <li key={event.id} className="flex flex-wrap gap-x-3 border-l border-white/[0.12] pl-3">
          <span className="font-medium">{humanize(event.event_type.replace(/\./g, ' '))}</span>
          <span className="text-xs text-muted-foreground">{new Date(event.occurred_at).toLocaleString('en-JM')} · {event.actor_type}{event.actor_id ? ` ${event.actor_id.slice(0, 8)}` : ''}</span>
        </li>)}
      </ol>
    </LoadState>
  </section>;
}
