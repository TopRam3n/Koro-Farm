'use client';

import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BellRing, CircleAlert, MapPin, ShoppingBasket, Sprout } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

const crops = ['BANANA', 'BREADFRUIT', 'CALLALOO', 'CASSAVA', 'GINGER', 'MANGO', 'PLANTAIN', 'SWEET_POTATO', 'YAM'];

type Availability = {
  production_lot_id: string;
  farmer_name: string;
  parish: string;
  crop: string;
  quality_grade_estimate: string;
  harvest_start: string;
  harvest_end: string;
  expected_quantity_kg: string;
  available_quantity_kg: string;
  availability_confidence: string;
};
type CustomerOrder = { id: string; farmer_name: string; parish: string; crop: string; quantity_kg: string; status: string; created_at: string };
type AvailabilityAlert = { id: string; crop: string; minimum_quantity_kg: string; available_quantity_kg: string; farmer_name: string; parish: string; quality_grade_estimate: string; read: boolean };

export function MarketplaceWorkspace() {
  const queryClient = useQueryClient();
  const [cropFilter, setCropFilter] = useState('');
  const availability = useQuery({
    queryKey: ['marketplace', 'availability', cropFilter],
    queryFn: () => apiFetch<{ items: Availability[] }>(`/marketplace/availability${cropFilter ? `?crop=${cropFilter}` : ''}`),
    refetchInterval: 30_000,
  });
  const orders = useQuery({ queryKey: ['marketplace', 'orders'], queryFn: () => apiFetch<{ items: CustomerOrder[] }>('/marketplace/orders'), refetchInterval: 30_000 });
  const alerts = useQuery({ queryKey: ['marketplace', 'alerts'], queryFn: () => apiFetch<{ items: AvailabilityAlert[] }>('/marketplace/alerts'), refetchInterval: 30_000 });
  const placeOrder = useMutation({
    mutationFn: (payload: { production_lot_id: string; quantity_kg: string }) => apiFetch('/marketplace/orders', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: async () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'availability'] }),
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'orders'] }),
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'alerts'] }),
    ]),
  });
  const createWatch = useMutation({
    mutationFn: (payload: { crop: string; minimum_quantity_kg: string }) => apiFetch('/marketplace/watches', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['marketplace', 'alerts'] }),
  });
  const markRead = useMutation({
    mutationFn: (alertId: string) => apiFetch(`/marketplace/alerts/${alertId}/read`, { method: 'POST' }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['marketplace', 'alerts'] }),
  });

  async function submitWatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await createWatch.mutateAsync({ crop: String(values.get('crop')), minimum_quantity_kg: String(values.get('minimum_quantity_kg')) });
    form.reset();
  }

  return <AppShell programme="Produce marketplace"><main className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="mb-7"><p className="section-eyebrow">Customer workspace</p><h1 className="mt-2 text-3xl font-semibold">Available produce</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Browse farmer-reported harvests by food, quality, location, and harvest window. Availability is an estimate until confirmed.</p></header>

    <section aria-labelledby="availability-title">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><h2 id="availability-title" className="text-xl font-semibold">Farmers and harvests</h2><p className="mt-1 text-xs text-muted-foreground">{availability.data?.items.length ?? 0} available listings</p></div><label className="grid gap-1.5 text-xs font-medium text-muted-foreground">Filter food<select value={cropFilter} onChange={event => setCropFilter(event.target.value)} className="h-10 min-w-48 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground"><option value="">All foods</option>{crops.map(crop => <option key={crop} value={crop}>{crop.replace(/_/g, ' ')}</option>)}</select></label></div>
      {availability.isLoading ? <p className="py-10 text-sm text-muted-foreground">Loading available harvests…</p> : availability.error ? <p role="alert" className="py-10 text-sm text-destructive">Availability is temporarily unavailable.</p> : availability.data?.items.length ? <div className="grid gap-x-8 sm:grid-cols-2">{availability.data.items.map(listing => <AvailabilityCard key={listing.production_lot_id} listing={listing} pending={placeOrder.isPending} onOrder={(quantity) => placeOrder.mutate({ production_lot_id: listing.production_lot_id, quantity_kg: quantity })} />)}</div> : <div className="border-y border-white/[0.07] py-12 text-center"><Sprout className="mx-auto h-5 w-5 text-muted-foreground" /><p className="mt-3 text-sm font-medium">No matching harvests are available</p><p className="mt-1 text-xs text-muted-foreground">Create an availability alert to be notified when supply is listed.</p></div>}
      {placeOrder.error && <p role="alert" className="mt-4 flex items-center gap-2 text-sm text-destructive"><CircleAlert className="h-4 w-4" />{placeOrder.error.message}</p>}
      {placeOrder.isSuccess && <p role="status" className="mt-4 text-sm text-success">Order placed. The requested quantity is reserved pending fulfilment.</p>}
    </section>

    <section className="mt-9 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.72fr)]">
      <div id="orders"><div className="mb-4 flex items-end justify-between"><div><p className="section-eyebrow">Your requests</p><h2 className="mt-1 text-xl font-semibold">Orders</h2></div><span className="text-xs text-muted-foreground">{orders.data?.items.length ?? 0} orders</span></div>{orders.data?.items.length ? <div className="divide-y divide-white/[0.07] border-y border-white/[0.07]">{orders.data.items.map(order => <article key={order.id} className="flex items-center justify-between gap-4 py-4"><div><h3 className="text-sm font-medium">{order.quantity_kg} kg {order.crop.replace(/_/g, ' ')}</h3><p className="mt-1 text-xs text-muted-foreground">{order.farmer_name} · {order.parish}</p></div><span className="rounded-sm border border-primary/20 px-2 py-1 text-[10px] font-semibold uppercase text-primary">{order.status}</span></article>)}</div> : <p className="border-y border-white/[0.07] py-8 text-sm text-muted-foreground">Your orders will appear here.</p>}</div>
      <div id="alerts"><div className="mb-4"><p className="section-eyebrow">Availability notifications</p><h2 className="mt-1 text-xl font-semibold">Food alerts</h2></div><form onSubmit={submitWatch} className="grid gap-3 border-y border-white/[0.07] py-4 sm:grid-cols-[minmax(0,1fr)_110px_auto]"><label className="grid gap-1.5 text-xs font-medium text-muted-foreground">Food<select name="crop" required className="h-10 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground">{crops.map(crop => <option key={crop} value={crop}>{crop.replace(/_/g, ' ')}</option>)}</select></label><label className="grid gap-1.5 text-xs font-medium text-muted-foreground">Minimum kg<input name="minimum_quantity_kg" type="number" min="0.001" step="0.001" defaultValue="10" required className="h-10 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label><button type="submit" disabled={createWatch.isPending} className="mt-auto inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-white/10 px-3 text-xs font-semibold hover:bg-white/[0.05] disabled:opacity-60"><BellRing className="h-3.5 w-3.5" />{createWatch.isPending ? 'Saving…' : 'Alert me'}</button></form>
        <p className="mt-2 text-[11px] text-muted-foreground">In-app alerts refresh every 30 seconds while this page is open.</p>
        {createWatch.error && <p role="alert" className="mt-3 text-xs text-destructive">{createWatch.error.message}</p>}
        <ul className="mt-3 divide-y divide-white/[0.07]">{alerts.data?.items.map(alert => <li key={alert.id} className="flex items-start justify-between gap-3 py-3"><div className="flex gap-2.5"><BellRing className={`mt-0.5 h-4 w-4 shrink-0 ${alert.read ? 'text-muted-foreground' : 'text-warning'}`} /><div><p className="text-xs font-medium">{alert.crop.replace(/_/g, ' ')} available · {alert.available_quantity_kg} kg</p><p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">{alert.farmer_name}<MapPin className="ml-1 h-3 w-3" />{alert.parish}</p></div></div>{!alert.read && <button type="button" onClick={() => markRead.mutate(alert.id)} className="min-h-9 px-2 text-[10px] font-semibold text-primary">Mark read</button>}</li>)}</ul>
      </div>
    </section>
  </main></AppShell>;
}

function AvailabilityCard({ listing, pending, onOrder }: { listing: Availability; pending: boolean; onOrder: (quantity: string) => void }) {
  const [quantity, setQuantity] = useState('10');
  return <article className="grid gap-4 border-y border-white/[0.07] py-5 sm:grid-cols-[minmax(0,1fr)_170px] sm:items-center">
    <div><div className="flex flex-wrap items-center gap-2"><h3 className="text-base font-semibold">{listing.crop.replace(/_/g, ' ')}</h3><span className="text-[10px] font-semibold uppercase text-primary">Grade {listing.quality_grade_estimate}</span></div><p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground"><Sprout className="h-3.5 w-3.5" />{listing.farmer_name}<MapPin className="ml-1 h-3.5 w-3.5" />{listing.parish}</p><p className="mt-2 text-xs text-muted-foreground">Harvest {listing.harvest_start} to {listing.harvest_end}</p><p className="mt-2 text-xs"><strong className="tabular">{listing.available_quantity_kg} kg</strong><span className="ml-1 text-muted-foreground">available · {listing.availability_confidence.toLowerCase()} confidence</span></p></div>
    <form className="grid grid-cols-[1fr_auto] items-end gap-2" onSubmit={event => { event.preventDefault(); onOrder(quantity); }}><label className="grid gap-1 text-[10px] font-medium text-muted-foreground">Order kg<input type="number" min="0.001" max={listing.available_quantity_kg} step="0.001" value={quantity} onChange={event => setQuantity(event.target.value)} required className="h-10 w-full rounded-md border border-white/10 bg-background px-2 text-sm text-foreground" /></label><button type="submit" disabled={pending} className="grid h-10 w-10 place-items-center rounded-md bg-primary text-primary-foreground disabled:opacity-60" aria-label={`Place order for ${listing.crop.toLowerCase()}`} title="Place order"><ShoppingBasket className="h-4 w-4" /></button></form>
  </article>;
}
