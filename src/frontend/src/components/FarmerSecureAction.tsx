'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import { CheckCircle2, Loader2, Sprout } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
type Action = { purpose: string; request_reference: string; farmer_name: string; crop: string; expires_at: string; constraints: Record<string, unknown> };

export function FarmerSecureAction() {
  const { token } = useParams<{ token: string }>();
  const [action, setAction] = useState<Action>();
  const [quantity, setQuantity] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [state, setState] = useState<'loading'|'ready'|'saving'|'done'|'error'>('loading');
  const [message, setMessage] = useState('');
  const idempotencyKey = useRef(typeof crypto !== 'undefined' ? crypto.randomUUID() : `secure-${Date.now()}`);

  useEffect(() => {
    fetch(`${API_URL}/v1/secure-actions/${encodeURIComponent(token)}`)
      .then(async response => { if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? 'This action is unavailable.'); return response.json(); })
      .then(data => { setAction(data); setState('ready'); })
      .catch(error => { setMessage(error.message); setState('error'); });
  }, [token]);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setState('saving');
    const body = action?.purpose === 'CONFIRM_HARVEST_DATE'
      ? { harvest_start: start, harvest_end: end }
      : { available_quantity_kg: quantity };
    const response = await fetch(`${API_URL}/v1/secure-actions/${encodeURIComponent(token)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey.current },
      body: JSON.stringify(body),
    });
    if (!response.ok) { const error = await response.json().catch(() => null); setMessage(error?.detail ?? 'Your response could not be recorded.'); setState('error'); return; }
    setState('done');
  };

  return <main className="grid min-h-screen place-items-center bg-background p-4"><section className="w-full max-w-md rounded-2xl border border-white/[0.1] bg-card p-6 shadow-2xl sm:p-8"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Sprout className="h-5 w-5" /></span><div><strong>KoroFarm</strong><p className="text-xs text-muted-foreground">Secure farmer response</p></div></div>
    {state === 'loading' && <div className="grid place-items-center py-16"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>}
    {state === 'error' && <div role="alert" className="mt-8 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm"><strong>Response unavailable</strong><p className="mt-2 text-muted-foreground">{message}</p></div>}
    {state === 'done' && <div className="py-12 text-center"><CheckCircle2 className="mx-auto h-8 w-8 text-success" /><h1 className="mt-4 text-xl font-semibold">Response recorded</h1><p className="mt-2 text-sm text-muted-foreground">Your self-reported response is timestamped and awaiting the applicable verification process. This link cannot be reused.</p></div>}
    {(state === 'ready' || state === 'saving') && action && <form onSubmit={submit} className="mt-8 space-y-5"><div><p className="text-xs uppercase tracking-wider text-muted-foreground">Request</p><h1 className="mt-2 text-xl font-semibold">{action.request_reference}</h1><p className="mt-2 text-sm text-muted-foreground">{action.farmer_name} · {action.crop} · expires {new Date(action.expires_at).toLocaleString()}</p></div>
      {action.purpose === 'CONFIRM_HARVEST_DATE' ? <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Harvest start<input required type="date" value={start} onChange={e => setStart(e.target.value)} className="mt-2 h-11 w-full rounded-md border border-white/[0.1] bg-background px-3" /></label><label className="text-sm">Harvest end<input required type="date" value={end} onChange={e => setEnd(e.target.value)} className="mt-2 h-11 w-full rounded-md border border-white/[0.1] bg-background px-3" /></label></div> : <label className="block text-sm">Available quantity (kg)<input required inputMode="decimal" type="number" min="0" step="0.001" value={quantity} onChange={e => setQuantity(e.target.value)} className="mt-2 h-12 w-full rounded-md border border-white/[0.1] bg-background px-3 text-lg" /></label>}
      <button disabled={state === 'saving'} className="h-12 w-full rounded-md bg-primary font-semibold text-primary-foreground disabled:opacity-60">{state === 'saving' ? 'Recording…' : 'Confirm response'}</button><p className="text-center text-[11px] leading-5 text-muted-foreground">This single-purpose link cannot open unrelated KoroFarm records. Your response is recorded as self-reported, not automatically verified.</p>
    </form>}
  </section></main>;
}
