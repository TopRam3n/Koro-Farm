'use client';

import Link from 'next/link';
import { type OverviewItem, type OverviewQueue, useFulfilmentOverview } from '@/hooks/useFulfilment';
import { useCan } from '@/hooks/useIdentity';
import { LoadState, Pill, TradePage, kg } from '@/components/trade/TradeUi';

const when = (value?: string | null) => value ? new Date(value).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' }) : '';

/** Queue order and wording per role's work (R1 WP5, M1). Every figure comes from the records; nothing is estimated. */
const QUEUES: Array<{ key: string; title: string; hint: string; line: (item: OverviewItem) => string }> = [
  { key: 'receipts_today', title: "Today's receipts", hint: 'Received at a site since midnight (Jamaica time).',
    line: i => `${i.supplier}: ${kg(i.received_kg)} at ${when(i.received_at)}` },
  { key: 'ungraded_receipts', title: 'Waiting for grading', hint: 'Received but not yet graded; accepted quantity is unknown until then.',
    line: i => `${i.supplier}: ${kg(i.received_kg)} received ${when(i.received_at)}` },
  { key: 'open_shipments', title: 'Shipments not yet dispatched', hint: 'Open shipments still at a site.', line: i => `Shipment ${i.reference}` },
  { key: 'in_transit', title: 'Dispatched, delivery not recorded', hint: 'Left a site; no proof of delivery recorded yet.',
    line: i => `Shipment ${i.reference}, dispatched ${when(i.dispatched_at)}` },
  { key: 'awaiting_buyer_confirmation', title: 'Deliveries awaiting the buyer', hint: 'Delivered, with no confirmation from the buyer yet. Delivered is not confirmed.',
    line: i => `Shipment ${i.reference}: ${kg(i.delivered_kg)} delivered ${when(i.delivered_at)}` },
  { key: 'sequence_flags', title: 'Event times to review', hint: 'Recorded times that cannot all be right. Nothing has been changed.', line: i => i.message ?? '' },
  { key: 'open_disputes', title: 'Open disputes', hint: 'Raised by the buyer or staff; each blocks close-out until resolved.',
    line: i => `${i.party === 'BUYER' ? 'Buyer' : 'Staff'}: ${i.description}${i.quantity_kg ? ` (${kg(i.quantity_kg)})` : ''}` },
  { key: 'reconciliations_pending_review', title: 'Corrections waiting for a second reviewer', hint: 'A material correction needs someone other than its author.',
    line: i => `Version ${i.version}${i.reason ? `: ${i.reason}` : ''}` },
  { key: 'ready_to_close', title: 'Reconciled, not closed', hint: 'Reconciled is not success: an order closes as completed only when every obligation is delivered and confirmed.',
    line: i => i.can_complete ? 'Can be closed as completed' : `Blocked: ${(i.blockers ?? []).join('; ')}` },
];

export function FulfilmentOverview() {
  const overview = useFulfilmentOverview();
  const can = useCan();
  return <TradePage eyebrow="Physical operations" title="Fulfilment Center"
    description="Work across all open orders. Queues you can act on come first; the rest are shown for information. Open an order to record anything."
    crumbs={[{ label: 'Command Center', href: '/' }, { label: 'Fulfilment Center' }]}>
    <LoadState query={overview}>
      {overview.data && <>
        <p className="text-xs text-muted-foreground">{overview.data.open_orders} open order(s). Updated {when(overview.data.generated_at)}.</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {[...QUEUES].sort((a, b) => Number(can(queueOf(overview.data.queues, b.key).action_permission)) - Number(can(queueOf(overview.data.queues, a.key).action_permission)))
            .map(q => <Queue key={q.key} spec={q} queue={queueOf(overview.data.queues, q.key)} actionable={can(queueOf(overview.data.queues, q.key).action_permission)} />)}
        </div>
      </>}
    </LoadState>
  </TradePage>;
}

const queueOf = (queues: Record<string, OverviewQueue>, key: string): OverviewQueue => queues[key] ?? { items: [], count: 0, action_permission: '' };

function Queue({ spec, queue, actionable }: { spec: typeof QUEUES[number]; queue: OverviewQueue; actionable: boolean }) {
  return <section aria-labelledby={`queue-${spec.key}`} data-queue={spec.key} data-actionable={actionable ? 'yes' : 'no'} className="operational-panel p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 id={`queue-${spec.key}`} className="text-sm font-semibold">{spec.title}</h2>
      <div className="flex items-center gap-2">
        <Pill tone={queue.count ? (actionable ? 'warn' : 'info') : 'neutral'}>{queue.count}</Pill>
        <span className="text-[11px] text-muted-foreground">{actionable ? 'You can act on these' : 'For information'}</span>
      </div>
    </div>
    <p className="mt-1 text-xs text-muted-foreground">{spec.hint}</p>
    {queue.count === 0 ? <p className="mt-2 text-sm text-muted-foreground">Nothing here.</p>
      : <ul className="mt-2 divide-y divide-white/[0.07] text-sm" aria-label={spec.title}>
        {queue.items.slice(0, 8).map((item, index) => <li key={`${item.requirement_id}-${index}`} className="py-2">
          <Link href={`/orders/${item.requirement_id}`} className="font-medium text-primary hover:underline">{item.order}</Link>
          <span className="block text-xs text-muted-foreground">{spec.line(item)}</span>
        </li>)}
        {queue.count > 8 && <li className="py-2 text-xs text-muted-foreground">and {queue.count - 8} more</li>}
      </ul>}
  </section>;
}
