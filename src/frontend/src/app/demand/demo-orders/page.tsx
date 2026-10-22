'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { AuthGate } from '@/components/AuthGate';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

type Me = { active_role: string; active_buyer_id: string | null; active_farmer_id: string | null; name: string };
type Offer = { id: string; farmer_name: string | null; farmer_id: string; production_lot_id: string; quantity_kg: string; status: string };
type Request = {
  id: string; buyer_name: string; buyer_id: string; crop: string; grade: string;
  required_quantity_kg: string; committed_quantity_kg: string; remaining_quantity_kg: string;
  delivery_window_start: string; delivery_window_end: string; lifecycle_status: string;
  offers: Offer[];
};
type Lot = { id: string; crop: string; grade: string; harvest_start: string; harvest_end: string; available_quantity_kg: string };
type NewOffer = { lotId: string; quantity: string };

const label = (value: string) => value.replace(/_/g, ' ');
const field = 'mt-1 w-full rounded-md border border-white/15 bg-background px-3 py-2.5 text-sm';
const initialOffer: NewOffer = { lotId: '', quantity: '' };

function MarketplaceRequests() {
  const [me, setMe] = useState<Me | null>(null);
  const [requests, setRequests] = useState<Request[]>([]);
  const [lots, setLots] = useState<Lot[]>([]);
  const [offers, setOffers] = useState<Record<string, NewOffer>>({});
  const [crop, setCrop] = useState('GINGER');
  const [grade, setGrade] = useState('A');
  const [quantity, setQuantity] = useState('500');
  const [start, setStart] = useState('2026-11-16');
  const [end, setEnd] = useState('2026-11-30');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async () => {
    const identity = await apiFetch<Me>('/me');
    const [data, available] = await Promise.all([
      apiFetch<{ items: Request[] }>('/marketplace/requests'),
      identity.active_role === 'FARMER'
        ? apiFetch<{ items: Lot[] }>('/marketplace/requests/my-lots')
        : Promise.resolve({ items: [] as Lot[] }),
    ]);
    setMe(identity);
    setRequests(data.items);
    setLots(available.items);
  }, []);

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const identity = await apiFetch<Me>('/me');
        const [data, available] = await Promise.all([
          apiFetch<{ items: Request[] }>('/marketplace/requests'),
          identity.active_role === 'FARMER'
            ? apiFetch<{ items: Lot[] }>('/marketplace/requests/my-lots')
            : Promise.resolve({ items: [] as Lot[] }),
        ]);
        if (active) { setMe(identity); setRequests(data.items); setLots(available.items); }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause));
      } finally { if (active) setLoading(false); }
    }
    void init();
    return () => { active = false; };
  }, []);

  async function act(message: string, path: string, body?: object) {
    setBusy(true); setError(''); setNotice('');
    try {
      await apiFetch(path, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) });
      await refresh();
      setNotice(message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void act('Draft created. Publish it to make it visible to farmers.', '/marketplace/requests', {
      crop, grade, required_quantity_kg: quantity,
      delivery_window_start: start, delivery_window_end: end,
    });
  }

  const buyer = me?.active_role === 'BUYER';
  const farmer = me?.active_role === 'FARMER';

  return <AppShell programme="KoroFarm · Buyer–Farmer Marketplace">
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <header>
        <p className="section-eyebrow">Marketplace</p>
        <h1 className="mt-2 text-3xl font-bold">{buyer ? 'My Procurement Requests' : farmer ? 'Buyer Opportunities' : 'Procurement Requests'}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{buyer ? 'Publish crop requirements and review farmer offers.' : 'Browse published requests and offer produce from your own production lots.'}</p>
      </header>
      {loading && <p>Loading marketplace…</p>}
      {error && <p role="alert" className="rounded-lg border border-red-500/30 p-4 text-red-400">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-emerald-500/30 p-4 text-emerald-400">{notice}</p>}
      {!loading && buyer && <form onSubmit={create} className="operational-panel space-y-4 p-5">
        <h2 className="text-xl font-semibold">New buyer request</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-sm">Crop<select className={field} value={crop} onChange={e => setCrop(e.target.value)}><option value="GINGER">Ginger</option></select></label>
          <label className="text-sm">Grade<select className={field} value={grade} onChange={e => setGrade(e.target.value)}><option>A</option><option>B</option></select></label>
          <label className="text-sm">Quantity (kg)<input className={field} required type="number" min="0.001" step="0.001" value={quantity} onChange={e => setQuantity(e.target.value)} /></label>
          <label className="text-sm">Delivery from<input className={field} required type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
          <label className="text-sm">Delivery until<input className={field} required type="date" min={start} value={end} onChange={e => setEnd(e.target.value)} /></label>
        </div>
        <button disabled={busy} className="rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50">Create draft request</button>
      </form>}
      {!loading && (buyer || farmer) && <section className="space-y-4">
        <h2 className="text-xl font-semibold">{buyer ? 'Your requirements' : 'Published opportunities'} ({requests.length})</h2>
        {requests.length === 0 && <p className="operational-panel p-6 text-muted-foreground">{buyer ? 'No requests yet. Create your first draft.' : 'No published buyer requests available yet.'}</p>}
        {requests.map(request => {
          const remaining = Number(request.remaining_quantity_kg);
          const required = Number(request.required_quantity_kg);
          const eligible = lots.filter(lot => lot.crop === request.crop && lot.grade === request.grade &&
            lot.harvest_end >= request.delivery_window_start && lot.harvest_start <= request.delivery_window_end && Number(lot.available_quantity_kg) > 0);
          const form = offers[request.id] ?? initialOffer;
          const own = request.offers;
          return <article key={request.id} className="operational-panel space-y-4 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="text-lg font-semibold">{required.toLocaleString()} kg · Grade {request.grade} {label(request.crop)}</h3>
                <p className="text-sm text-muted-foreground">{request.buyer_name} · {request.delivery_window_start} to {request.delivery_window_end}</p></div>
              <span className="rounded-md border border-white/15 px-3 py-1 text-xs">{request.lifecycle_status}</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div><p className="text-muted-foreground">Requested</p><strong>{required.toLocaleString()} kg</strong></div>
              <div><p className="text-muted-foreground">Accepted</p><strong>{Number(request.committed_quantity_kg).toLocaleString()} kg</strong></div>
              <div><p className="text-muted-foreground">Remaining</p><strong>{remaining.toLocaleString()} kg</strong></div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${required > 0 ? Math.min(100, (Number(request.committed_quantity_kg) / required) * 100) : 0}%` }} /></div>
            {buyer && request.lifecycle_status === 'DRAFT' && <button type="button" disabled={busy} onClick={() => void act('Request published.', `/marketplace/requests/${request.id}/publish`)} className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">Publish for farmers</button>}
            {buyer && request.offers.length > 0 && <section className="space-y-2 border-t border-white/10 pt-3"><h4 className="font-medium">Farmer offers</h4>
              {request.offers.map(offer => <div key={offer.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/10 p-3 text-sm">
                <span>{offer.farmer_name} · {Number(offer.quantity_kg).toLocaleString()} kg · {offer.status}</span>
                {offer.status === 'PENDING' && <div className="flex gap-2">
                  <button disabled={busy} type="button" onClick={() => void act('Offer accepted and lot stock reserved.', `/marketplace/requests/offers/${offer.id}/accept`)} className="rounded-md bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50">Accept</button>
                  <button disabled={busy} type="button" onClick={() => void act('Offer declined.', `/marketplace/requests/offers/${offer.id}/decline`)} className="rounded-md border border-white/20 px-3 py-2 disabled:opacity-50">Decline</button>
                </div>}
              </div>)}
            </section>}
            {farmer && <div className="space-y-3 border-t border-white/10 pt-3">
              <h4 className="font-medium">Your offers</h4>
              {own.length === 0 && <p className="text-sm text-muted-foreground">You have not offered produce for this request.</p>}
              {own.map(offer => <div key={offer.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
                <span>{Number(offer.quantity_kg).toLocaleString()} kg · {offer.status}</span>
                {offer.status === 'PENDING' && <button disabled={busy} type="button" onClick={() => void act('Offer withdrawn.', `/marketplace/requests/offers/${offer.id}/withdraw`)} className="rounded-md border border-white/20 px-3 py-2 disabled:opacity-50">Withdraw offer</button>}
              </div>)}
              {remaining > 0 && eligible.length > 0 && <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px_auto] sm:items-end" onSubmit={event => {
                event.preventDefault();
                if (!form.lotId) { setError('Select an eligible production lot.'); return; }
                void act('Offer submitted to the buyer for review.', `/marketplace/requests/${request.id}/offers`, { production_lot_id: form.lotId, quantity_kg: form.quantity });
              }}>
                <label className="text-sm">Your eligible lot<select required className={field} value={form.lotId} onChange={event => setOffers(old => ({ ...old, [request.id]: { ...form, lotId: event.target.value } }))}>
                  <option value="">Select lot</option>
                  {eligible.map(lot => <option key={lot.id} value={lot.id}>{lot.harvest_start}–{lot.harvest_end} · {Number(lot.available_quantity_kg).toLocaleString()} kg available · {lot.id.slice(0, 8)}</option>)}
                </select></label>
                <label className="text-sm">Offer quantity (kg)<input className={field} required type="number" min="0.001" step="0.001" max={Math.min(remaining, Number(eligible.find(lot => lot.id === form.lotId)?.available_quantity_kg ?? 0)) || undefined} value={form.quantity} onChange={event => setOffers(old => ({ ...old, [request.id]: { ...form, quantity: event.target.value } }))} /></label>
                <button disabled={busy} className="rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50">Submit offer</button>
              </form>}
              {remaining > 0 && eligible.length === 0 && <p className="text-sm text-muted-foreground">No available production lot matches the requested crop, grade and delivery window.</p>}
            </div>}
          </article>;
        })}
      </section>}
      {!loading && !buyer && !farmer && <p role="alert">A linked Farmer or Buyer account is required.</p>}
    </main>
  </AppShell>;
}

export default function Page() { return <AuthGate><MarketplaceRequests /></AuthGate>; }
