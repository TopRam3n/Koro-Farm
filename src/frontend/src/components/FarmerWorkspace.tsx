'use client';

import { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, CircleAlert, ClipboardPlus, PackageCheck } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { useIdentity } from '@/hooks/useIdentity';

const crops = ['BANANA', 'BREADFRUIT', 'CALLALOO', 'CASSAVA', 'GINGER', 'MANGO', 'PLANTAIN', 'SWEET_POTATO', 'YAM'];

type FarmerLot = {
  id: string;
  crop: string;
  harvest_start: string;
  harvest_end: string;
  expected_quantity_kg: string;
  available_quantity_kg: string;
  reserved_quantity_kg: string;
  quality_grade_estimate: string;
  availability_confidence: string;
  status: 'AVAILABLE' | 'UNAVAILABLE' | 'EXHAUSTED';
};

export function FarmerWorkspace() {
  const identity = useIdentity();
  const queryClient = useQueryClient();
  const lots = useQuery({ queryKey: ['farmer', 'lots'], queryFn: () => apiFetch<FarmerLot[]>('/production-lots') });
  const report = useMutation({
    mutationFn: (payload: Record<string, string>) => apiFetch('/v1/ingestion/farmer-production-lots', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['farmer', 'lots'] }),
  });
  const readyStock = useMutation({
    mutationFn: ({ lotId, quantity }: { lotId: string; quantity: string }) => apiFetch(`/v1/ingestion/farmer-production-lots/${lotId}/availability`, {
      method: 'POST', body: JSON.stringify({ available_quantity_kg: quantity }),
    }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['farmer', 'lots'] }),
  });

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await report.mutateAsync({
      crop: String(values.get('crop')),
      harvest_start: String(values.get('harvest_start')),
      harvest_end: String(values.get('harvest_end')),
      expected_quantity_kg: String(values.get('expected_quantity_kg')),
      quality_grade_estimate: String(values.get('quality_grade_estimate')),
    });
    form.reset();
  }

  async function submitReadyStock(event: FormEvent<HTMLFormElement>, lotId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await readyStock.mutateAsync({ lotId, quantity: String(values.get('available_quantity_kg')) });
    form.reset();
  }

  return <AppShell programme="Farmer workspace"><main className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="mb-7"><p className="section-eyebrow">My farm</p><h1 className="mt-2 text-3xl font-semibold">Harvest and quality</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Share what you expect to harvest and the grade you expect. Reports are marked self-reported until independently confirmed.</p></header>

    <section className="operational-panel max-w-3xl p-5 sm:p-6" aria-labelledby="harvest-form-title">
      <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-md bg-primary/10 text-primary"><ClipboardPlus className="h-5 w-5" /></span><div><p className="section-eyebrow">New report</p><h2 id="harvest-form-title" className="mt-1 text-lg font-semibold">Expected harvest</h2></div></div>
      {identity.data?.active_role === 'PLATFORM_ADMIN' ? <p className="mt-6 rounded-md border border-white/[0.08] p-4 text-sm leading-6 text-muted-foreground">Developer review is read-only here to preserve farmer attribution. Use the organization supply tools for coordinator-recorded observations.</p> : <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={submitReport}>
        <label className="grid gap-2 text-xs font-medium text-muted-foreground">Food<select name="crop" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground">{crops.map(crop => <option key={crop} value={crop}>{crop.replace(/_/g, ' ')}</option>)}</select></label>
        <label className="grid gap-2 text-xs font-medium text-muted-foreground">Expected amount (kg)<input name="expected_quantity_kg" type="number" min="0.001" step="0.001" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" placeholder="e.g. 120" /></label>
        <label className="grid gap-2 text-xs font-medium text-muted-foreground">Harvest begins<input name="harvest_start" type="date" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
        <label className="grid gap-2 text-xs font-medium text-muted-foreground">Harvest ends<input name="harvest_end" type="date" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label>
        <label className="grid gap-2 text-xs font-medium text-muted-foreground sm:col-span-2">Expected item quality<select name="quality_grade_estimate" required className="h-11 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground"><option value="A">Grade A · premium quality</option><option value="B">Grade B · standard quality</option></select></label>
        {report.error && <p role="alert" className="flex gap-2 text-sm text-destructive sm:col-span-2"><CircleAlert className="h-4 w-4 shrink-0" />{report.error.message}</p>}
        {report.isSuccess && <p role="status" className="text-sm text-success sm:col-span-2">Harvest report saved as self-reported.</p>}
        <button type="submit" disabled={report.isPending} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-60 sm:col-span-2">{report.isPending ? 'Saving report…' : 'Save harvest report'}</button>
      </form>}
    </section>

    <section className="mt-8" aria-labelledby="lots-title">
      <div className="mb-4 flex items-end justify-between gap-4"><div><p className="section-eyebrow">My listings</p><h2 id="lots-title" className="mt-1 text-xl font-semibold">Reported harvests</h2></div><span className="text-xs text-muted-foreground">{lots.data?.length ?? 0} listings</span></div>
      {lots.isLoading ? <p className="py-8 text-sm text-muted-foreground">Loading your harvests…</p> : lots.error ? <p role="alert" className="py-8 text-sm text-destructive">Your harvest records are unavailable.</p> : lots.data?.length ? <div className="divide-y divide-white/[0.07] border-y border-white/[0.07]">{lots.data.map(lot => <article key={lot.id} className="grid gap-4 py-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h3 className="text-sm font-semibold">{lot.crop.replace(/_/g, ' ')} · Grade {lot.quality_grade_estimate}</h3><p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground"><CalendarDays className="h-3.5 w-3.5" />{lot.harvest_start} to {lot.harvest_end}</p></div><div className="flex flex-wrap items-center gap-2 text-xs"><PackageCheck className="h-4 w-4 text-primary" /><span className="tabular">{lot.expected_quantity_kg} kg expected</span><span className="text-muted-foreground">· {lot.available_quantity_kg} kg ready · {lot.status.toLowerCase()}</span></div></div>{identity.data?.active_role === 'FARMER' && <form className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end" onSubmit={event => submitReadyStock(event, lot.id)}><label className="grid gap-1 text-[10px] font-medium text-muted-foreground">Kilograms ready for orders<input name="available_quantity_kg" type="number" min={lot.reserved_quantity_kg} max={lot.expected_quantity_kg} step="0.001" defaultValue={lot.available_quantity_kg} required className="h-10 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground" /></label><button type="submit" disabled={readyStock.isPending} className="min-h-10 rounded-md border border-white/10 px-3 text-xs font-semibold hover:bg-white/[0.05] disabled:opacity-60">{readyStock.isPending ? 'Updating…' : 'Update ready stock'}</button></form>}</article>)}</div> : <div className="border-y border-white/[0.07] py-10 text-center"><PackageCheck className="mx-auto h-5 w-5 text-muted-foreground" /><p className="mt-3 text-sm font-medium">No harvests reported</p><p className="mt-1 text-xs text-muted-foreground">Your saved estimates will appear here.</p></div>}
      {readyStock.error && <p role="alert" className="mt-3 text-sm text-destructive">{readyStock.error.message}</p>}
      {readyStock.isSuccess && <p role="status" className="mt-3 text-sm text-success">Ready stock updated. Customers will see available quantities.</p>}
    </section>
  </main></AppShell>;
}
