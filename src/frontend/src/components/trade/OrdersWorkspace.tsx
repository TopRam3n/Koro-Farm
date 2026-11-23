'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useBuyers, useCreateOrder, useCrops, useOrders } from '@/hooks/useTrade';
import { ErrorNote, Field, LoadState, Pill, Select, SubmitButton, TextArea, TradePage, formValues, humanize, kg } from '@/components/trade/TradeUi';
import { HonestEmpty } from '@/components/WorkspacePrimitives';
import { healthLabel } from '@/components/trade/OrderDetail';

export function OrdersWorkspace() {
  const orders = useOrders();
  return <TradePage eyebrow="Demand" title="Orders" description="Buyer orders your organization is assembling and fulfilling."
    crumbs={[{ label: 'Orders' }]}>
    <div className="mb-4 flex flex-wrap gap-2">
      <Link href="/orders/new" className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground">New order</Link>
      <Link href="/buyers" className="inline-flex min-h-11 items-center rounded-md border border-white/[0.14] px-4 text-sm">Buyers</Link>
      <Link href="/suppliers" className="inline-flex min-h-11 items-center rounded-md border border-white/[0.14] px-4 text-sm">Suppliers and lots</Link>
    </div>
    <section className="operational-panel p-5" aria-labelledby="orders-list">
      <h2 id="orders-list" className="sr-only">All orders</h2>
      <LoadState query={orders} empty={<HonestEmpty title="No orders yet" detail="Create a buyer, record supply, then create the first order." />}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm" aria-label="Orders">
            <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-2">Order</th><th>Buyer</th><th className="text-right">Quantity</th><th className="pl-3">Delivery</th><th className="pl-3">Status</th></tr></thead>
            <tbody className="divide-y divide-white/[0.07]">
              {orders.data?.map(order => <tr key={order.id}>
                <td className="py-3"><Link className="font-medium text-primary underline-offset-2 hover:underline" href={`/orders/${order.id}`}>{order.crop.replace(/_/g, ' ')} · Grade {order.grade}</Link></td>
                <td>{order.buyer_name}</td>
                <td className="text-right">{kg(order.required_quantity_kg)}</td>
                <td className="pl-3 text-xs">{order.delivery_window_start} → {order.delivery_window_end}</td>
                <td className="pl-3"><Pill tone={order.lifecycle_status === 'CANCELLED' ? 'neutral' : order.supply_health === 'COVERED' ? 'good' : order.supply_health === 'UNPLANNED' ? 'info' : 'warn'}>{order.lifecycle_status === 'CANCELLED' ? 'Cancelled' : healthLabel(order.supply_health, order.plan_version)}</Pill></td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </LoadState>
    </section>
  </TradePage>;
}

export function NewOrderForm() {
  const router = useRouter();
  const buyers = useBuyers();
  const crops = useCrops();
  const create = useCreateOrder();

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const order = await create.mutateAsync(formValues(event.currentTarget)).catch(() => null);
    // Navigate only once the server has stored the order.
    if (order) router.push(`/orders/${order.id}`);
  }

  return <TradePage eyebrow="Demand" title="New order" description="Record what the buyer needs. Supply is proposed and confirmed with suppliers afterwards."
    crumbs={[{ label: 'Orders', href: '/orders' }, { label: 'New order' }]}>
    <section className="operational-panel max-w-3xl p-5">
      {buyers.data?.length === 0 && <p className="mb-3 text-sm">You have no buyers yet. <Link className="text-primary underline" href="/buyers">Add a buyer</Link> first.</p>}
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
        <Select label="Buyer" name="buyer_id" required placeholder="Choose a buyer" options={(buyers.data ?? []).map(b => ({ value: b.id, label: b.name }))} />
        <Select label="Crop" name="crop" required placeholder="Choose a crop" options={(crops.data ?? []).filter(c => c.active).map(c => ({ value: c.code, label: c.name }))} />
        <Select label="Grade" name="grade" required options={[{ value: 'A', label: 'Grade A' }, { value: 'B', label: 'Grade B' }]} />
        <Field label="Required quantity (kg)" name="required_quantity_kg" type="number" min="0.001" step="0.001" required />
        <Field label="Delivery from" name="delivery_window_start" type="date" required />
        <Field label="Delivery to" name="delivery_window_end" type="date" required />
        <Field label="Product form" name="product_form" placeholder="e.g. Fresh, whole" />
        <Field label="Origin" name="origin" />
        <Field label="Destination" name="destination" />
        <Field label="Delivery terms" name="delivery_terms" placeholder="e.g. Delivered to buyer dock" />
        <Field label="Currency" name="currency" placeholder="JMD" maxLength={3} pattern="[A-Z]{3}" />
        <div className="sm:col-span-2"><TextArea label="Notes" name="notes" /></div>
        <div className="sm:col-span-2"><SubmitButton busy={create.isPending}>Create order</SubmitButton><ErrorNote error={create.error} /></div>
      </form>
    </section>
  </TradePage>;
}
