'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { AuthGate } from '@/components/AuthGate';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

type Commitment = { id: string; farmer_id: string; farmer_name: string; quantity_kg: number; status: 'COMMITTED' | 'WITHDRAWN' };
type DemoOrder = {
    id: string; buyer_name: string; crop: string; required_quantity_kg: number; delivery_date: string;
    allocations: Commitment[]; committed_quantity_kg: number; remaining_quantity_kg: number; supply_health: string
};
type Farmer = { external_id: string; name: string; crops: string[] };
type FarmerStock = { crop: string; available_quantity_kg: number; harvest_start: string; harvest_end: string };

const crops = ['GINGER', 'TOMATOES', 'SWEET_PEPPERS', 'LETTUCE', 'ONIONS', 'IRISH_POTATOES'];
const human = (value: string) => value.split('_').join(' ');
const deliveryDefault = () => { const day = new Date(); day.setDate(day.getDate() + 7); return day.toISOString().slice(0, 10); };
const inputClass = 'mt-1 block w-full rounded-lg border border-white/15 bg-[#111d1a] px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-400';

function Marketplace() {
    const [view, setView] = useState<'hotel' | 'farmer'>('hotel');
    const [buyer, setBuyer] = useState('Harbour View Hotel (Demo)');
    const [crop, setCrop] = useState('GINGER');
    const [quantity, setQuantity] = useState(500);
    const [delivery, setDelivery] = useState(deliveryDefault);
    const [orders, setOrders] = useState<DemoOrder[]>([]);
    const [farmers, setFarmers] = useState<Farmer[]>([]);
    const [farmerId, setFarmerId] = useState('F001');
    const [stock, setStock] = useState<FarmerStock[]>([]);
    const [offers, setOffers] = useState<Record<string, number>>({});
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const refresh = useCallback(async () => {
        const [requests, profiles, available] = await Promise.all([
            apiFetch<{ items: DemoOrder[] }>('/demo-orders'),
            apiFetch<{ items: Farmer[] }>('/demo-history/farmers'),
            apiFetch<{ items: FarmerStock[] }>(`/demo-farmer-availability/${farmerId}`),
        ]);
        setOrders(requests.items); setFarmers(profiles.items); setStock(available.items);
    }, [farmerId]);
    useEffect(() => { void refresh().catch((e: unknown) => setError(String(e))); }, [refresh]);

    const submit = async (path: string, body?: object) => {
        setBusy(true); setError('');
        try {
            const payload = body && path.endsWith('/commit') && process.env.NEXT_PUBLIC_APP_MODE !== 'demo'
                ? { ...body, request_key: crypto.randomUUID() } : body;
            await apiFetch(path, { method: 'POST', ...(payload ? { body: JSON.stringify(payload) } : {}) });
            await refresh();
        } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
        finally { setBusy(false); }
    };

    const deleteRequest = async (order: DemoOrder) => {
        if (!window.confirm(`Delete the ${order.required_quantity_kg} kg ${human(order.crop)} request from ${order.buyer_name}? All simulated farmer commitments to it will also be removed.`)) return;
        setBusy(true); setError('');
        try {
            await apiFetch(`/demo-orders/${order.id}`, { method: 'DELETE' });
            await refresh();
        } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
        finally { setBusy(false); }
    };

    const selected = farmers.find((farmer) => farmer.external_id === farmerId);
    const canSupply = (order: DemoOrder) => stock.some((lot) => lot.crop === order.crop &&
        lot.harvest_start <= order.delivery_date && lot.harvest_end >= order.delivery_date);

    return <AppShell programme="Buyer–Farmer Marketplace · Demo"><main className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-6 lg:px-8">
        <div><Link href="/demand" className="text-sm text-emerald-300 hover:underline">← Back to Demand</Link>
            <div className="mt-4 flex flex-wrap items-center gap-3"><h1 className="text-3xl font-bold tracking-tight">Buyer & Farmer Marketplace</h1><span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-300">SIMULATED DEMO</span></div>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">Hotels post crop requirements. Farmers browse open requests and choose how much of their own demo stock to commit. Every commitment is simulated, not a real supply confirmation.</p>
        </div>
        <div className="flex w-fit rounded-xl border border-white/10 bg-[#0c1815] p-1" role="tablist" aria-label="Marketplace perspective">
            {(['hotel', 'farmer'] as const).map((option) => <button key={option} role="tab" aria-selected={view === option} onClick={() => setView(option)} className={`rounded-lg px-6 py-2.5 text-sm font-semibold transition-colors ${view === option ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-white/10'}`}>{option === 'hotel' ? '🏨 Hotel / Buyer' : '🌱 Farmer'}</button>)}
        </div>
        {error && <p role="alert" className="rounded-lg border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-300">{error}</p>}

        {view === 'hotel' ? <div className="space-y-7">
            <form onSubmit={(event) => { event.preventDefault(); void submit('/demo-orders', { buyer_name: buyer, crop, required_quantity_kg: quantity, delivery_date: delivery }); }} className="space-y-5 rounded-2xl border border-white/10 bg-[#12201b] p-6 shadow-xl">
                <div><p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">Step 1 · Buyer</p><h2 className="mt-1 text-xl font-semibold">Post a crop requirement</h2><p className="mt-1 text-sm text-slate-400">Your order becomes visible to eligible demo farmers. No stock is allocated until farmers commit.</p></div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <label className="text-xs font-medium text-slate-300">Hotel / buyer<input required className={inputClass} value={buyer} onChange={(event) => setBuyer(event.target.value)} /></label>
                    <label className="text-xs font-medium text-slate-300">Crop<select className={inputClass} value={crop} onChange={(event) => { setCrop(event.target.value); setQuantity(event.target.value === 'GINGER' ? 500 : event.target.value === 'TOMATOES' ? 600 : 200); }}>{crops.map((item) => <option key={item} value={item}>{human(item)}</option>)}</select></label>
                    <label className="text-xs font-medium text-slate-300">Required quantity (kg)<input required min="1" step="1" type="number" className={inputClass} value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} /></label>
                    <label className="text-xs font-medium text-slate-300">Delivery date<input required type="date" className={inputClass} value={delivery} onChange={(event) => setDelivery(event.target.value)} /></label>
                </div>
                <button disabled={busy} className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50">Post request for farmers</button>
            </form>
            <section className="space-y-4"><h2 className="text-xl font-semibold">Hotel requests <span className="text-sm font-normal text-slate-400">({orders.length})</span></h2>
                {!orders.length && <div className="rounded-xl border border-dashed border-white/15 bg-white/[0.03] px-6 py-12 text-center"><p className="text-lg font-medium">No orders posted yet</p><p className="mt-2 text-sm text-slate-400">Post the hotel's first request, then switch to Farmer to commit supply.</p></div>}
                {orders.map((order) => <article key={order.id} className="rounded-xl border border-white/10 bg-[#12201b] p-5 space-y-4">
                    <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{order.required_quantity_kg} kg {human(order.crop)}</h3><p className="text-sm text-slate-400">{order.buyer_name} · Needed {order.delivery_date}</p></div><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-3 py-1 text-xs font-semibold ${order.remaining_quantity_kg ? 'bg-amber-400/10 text-amber-300' : 'bg-emerald-400/10 text-emerald-300'}`}>{order.remaining_quantity_kg ? 'OPEN FOR FARMERS' : 'FULLY COVERED · SIMULATED'}</span><button type="button" disabled={busy} onClick={() => void deleteRequest(order)} aria-label={`Delete ${human(order.crop)} request`} className="rounded-lg border border-red-400/30 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-400/10 disabled:opacity-50">Delete request</button></div></div>
                    <div className="grid grid-cols-3 gap-3 text-sm"><div><p className="text-slate-400">Requested</p><b>{order.required_quantity_kg} kg</b></div><div><p className="text-slate-400">Farmer committed</p><b className="text-emerald-300">{order.committed_quantity_kg} kg</b></div><div><p className="text-slate-400">Still needed</p><b>{order.remaining_quantity_kg} kg</b></div></div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${100 * order.committed_quantity_kg / order.required_quantity_kg}%` }} /></div>
                    {order.allocations.filter((a) => a.status === 'COMMITTED').length > 0 && <div className="border-t border-white/10 pt-3"><p className="mb-2 text-xs uppercase tracking-wider text-slate-400">Participating farmers</p><div className="flex flex-wrap gap-2">{order.allocations.filter((a) => a.status === 'COMMITTED').map((a) => <span key={a.id} className="rounded-lg bg-white/5 px-3 py-2 text-sm">{a.farmer_name} · {a.quantity_kg} kg</span>)}</div></div>}
                </article>)}
            </section>
        </div> : <div className="space-y-6">
            <section className="rounded-2xl border border-white/10 bg-[#12201b] p-6"><p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">Step 2 · Farmer</p><h2 className="mt-1 text-xl font-semibold">Browse buyer requests</h2>
                <label className="mt-5 block max-w-sm text-xs font-medium text-slate-300">Act as demo farmer<select className={inputClass} value={farmerId} onChange={(event) => setFarmerId(event.target.value)}>{farmers.map((farmer) => <option key={farmer.external_id} value={farmer.external_id}>{farmer.name} ({farmer.external_id})</option>)}</select></label>
                <p className="mt-4 text-sm text-slate-400">{selected?.name ?? 'Farmer'} grows {selected?.crops.join(', ') ?? '—'}. Remaining simulated stock: {stock.map((lot) => `${human(lot.crop)} ${lot.available_quantity_kg} kg`).join(' · ') || 'None'}.</p>
            </section>
            <section className="space-y-4"><h2 className="text-xl font-semibold">Hotel requests <span className="text-sm font-normal text-slate-400">({orders.length})</span></h2>
                <p className="text-sm text-slate-400">All posted requests appear here. Select a farmer who grows the requested crop to offer a commitment.</p>
                {!orders.length && <div className="rounded-xl border border-dashed border-white/15 p-8 text-center text-sm text-slate-400">No hotel requests yet. Switch to Hotel / Buyer to post one.</div>}
                {orders.map((order) => {
                    const cropStock = stock.find((lot) => lot.crop === order.crop); const maximum = Math.min(cropStock?.available_quantity_kg ?? 0, order.remaining_quantity_kg); const mine = order.allocations.filter((a) => a.farmer_id === farmerId && a.status === 'COMMITTED');
                    return <article key={order.id} className="space-y-4 rounded-xl border border-white/10 bg-[#12201b] p-5"><div className="flex flex-wrap justify-between gap-3"><div><h3 className="text-lg font-semibold">{human(order.crop)} · {order.required_quantity_kg} kg requested</h3><p className="text-sm text-slate-400">{order.buyer_name} · Delivery {order.delivery_date}</p></div><span className="text-sm text-amber-300">{order.remaining_quantity_kg} kg still needed</span></div>
                        {!canSupply(order) && <p className="text-sm text-amber-300">{selected?.name ?? 'This farmer'} cannot supply this crop for the requested delivery date. Choose another farmer to commit.</p>}
                        <p className="text-sm text-slate-300">Your remaining simulated stock: <strong>{cropStock?.available_quantity_kg ?? 0} kg</strong>{mine.length > 0 ? ` · You have committed ${mine.reduce((total, a) => total + a.quantity_kg, 0)} kg` : ''}</p>
                        {canSupply(order) && maximum > 0 && <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); void submit(`/demo-orders/${order.id}/commit`, { farmer_id: farmerId, quantity_kg: Math.min(offers[order.id] ?? maximum, maximum) }); }}><label className="text-xs text-slate-300">How much will you commit? (kg)<input type="number" min="1" max={maximum} step="1" className={`${inputClass} w-48`} value={Math.min(offers[order.id] ?? maximum, maximum)} onChange={(event) => setOffers((old) => ({ ...old, [order.id]: Number(event.target.value) }))} /></label><button disabled={busy} className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50">Commit to hotel order</button></form>}
                        {mine.map((a) => <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-3 text-sm"><span className="text-emerald-300">You committed {a.quantity_kg} kg · Simulated</span><button disabled={busy} onClick={() => void submit(`/demo-orders/${order.id}/withdraw/${a.id}`)} className="rounded-lg border border-red-400/30 px-3 py-1.5 text-red-300 hover:bg-red-400/10">Withdraw commitment</button></div>)}
                    </article>;
                })}
            </section>
        </div>}
    </main></AppShell>;
}

export default function Page() { return <AuthGate><Marketplace /></AuthGate>; }
