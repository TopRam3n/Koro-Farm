'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { AuthGate } from '@/components/AuthGate';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

type Me = { active_role: string; active_buyer_id: string | null; active_farmer_id: string | null; name: string };
type Request = {
  id: string; buyer_name: string; buyer_id: string; crop: string; grade: string;
  required_quantity_kg: string; delivery_window_start: string;
  delivery_window_end: string; lifecycle_status: string; supply_health: string;
};

function DemoOrders() {
  const [me, setMe] = useState<Me | null>(null);
  const [requests, setRequests] = useState<Request[]>([]);
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
    const [identity, result] = await Promise.all([
      apiFetch<Me>('/me'),
      apiFetch<{ items: Request[] }>('/marketplace/requests'),
    ]);
    setMe(identity);
    setRequests(result.items);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([apiFetch<Me>('/me'), apiFetch<{ items: Request[] }>('/marketplace/requests')])
      .then(([identity, result]) => {
        if (active) { setMe(identity); setRequests(result.items); }
      })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      await apiFetch('/marketplace/requests', {
        method: 'POST',
        body: JSON.stringify({
          crop, grade, required_quantity_kg: quantity,
          delivery_window_start: start, delivery_window_end: end
        }),
      });
      await refresh();
      setNotice('Draft created. Publish it to make it visible to farmers.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function publish(id: string) {
    setBusy(true); setError(''); setNotice('');
    try {
      await apiFetch(`/marketplace/requests/${id}/publish`, { method: 'POST' });
      await refresh();
      setNotice('Request published. Farmers can now view this opportunity.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  const buyer = me?.active_role === 'BUYER';
  const farmer = me?.active_role === 'FARMER';
  const field = 'mt-1 w-full rounded-md border border-white/15 bg-background px-3 py-2 text-sm';
  return <AppShell programme="KoroFarm · Buyer–Farmer Requests">
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <header><p className="section-eyebrow">Marketplace</p>
        <h1 className="mt-2 text-3xl font-bold">{buyer ? 'My Procurement Requests' : farmer ? 'Buyer Opportunities' : 'Procurement Requests'}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{buyer ? 'Create and publish requests for your hotel.' : 'Browse requests published by buyers in your organization.'}</p>
      </header>
      {loading && <p>Loading requests…</p>}
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
        <button disabled={busy} className="rounded-md bg-primary px-5 py-2.5 font-medium text-primary-foreground disabled:opacity-50">Create draft request</button>
      </form>}
      {!loading && (buyer || farmer) && <section className="space-y-3">
        <h2 className="text-xl font-semibold">{buyer ? 'Your requests' : 'Published requests'} ({requests.length})</h2>
        {requests.length === 0 && <p className="operational-panel p-6 text-muted-foreground">{buyer ? 'No requests yet. Create your first draft above.' : 'No published buyer opportunities are available yet.'}</p>}
        {requests.map(request => <article key={request.id} className="operational-panel space-y-3 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div>
            <h3 className="text-lg font-semibold">{request.required_quantity_kg} kg · Grade {request.grade} {request.crop.replace(/_/g, ' ')}</h3>
            <p className="text-sm text-muted-foreground">{request.buyer_name} · {request.delivery_window_start} to {request.delivery_window_end}</p>
          </div><span className="rounded-md border border-white/15 px-3 py-1 text-xs">{request.lifecycle_status}</span></div>
          {buyer && request.lifecycle_status === 'DRAFT' && <button type="button" disabled={busy} onClick={() => void publish(request.id)} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">Publish for farmers</button>}
          {farmer && <p className="text-sm text-muted-foreground">Farmer commitments are coming in phase 2. You can currently browse published requests.</p>}
        </article>)}
      </section>}
      {!loading && !buyer && !farmer && <p role="alert">A Buyer or Farmer membership is required for this workspace.</p>}
    </main>
  </AppShell>;
}
export default function Page() { return <AuthGate><DemoOrders /></AuthGate>; }
