'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useMemo, useState } from 'react';
import { AppShell } from '@/components/AppShell';
import { annualSeries, getFarmerProductionHistory, getFarmerProfile, quarterlySeries } from '@/lib/farmerHistory';

const readableCrop = (crop: string) => crop.replace(/_/g, ' ');
const formatKg = (value: number) => `${value.toLocaleString('en-JM', { maximumFractionDigits: 3 })} kg`;

export function FarmerHistoryProfile({ farmerId }: { farmerId: string }) {
  const [crop, setCrop] = useState('ALL');
  const [period, setPeriod] = useState<'quarterly' | 'annual'>('quarterly');
  const profile = useQuery({ queryKey: ['farmer-profile', farmerId], queryFn: () => getFarmerProfile(farmerId) });
  const history = useQuery({ queryKey: ['farmer-history', farmerId], queryFn: () => getFarmerProductionHistory(farmerId) });
  const records = history.data ?? [];
  const filteredCrop = crop === 'ALL' ? undefined : crop;
  const series = useMemo(() => period === 'annual' ? annualSeries(records, filteredCrop) : quarterlySeries(records, filteredCrop), [records, filteredCrop, period]);
  const total = series.reduce((sum, item) => sum + item.kilograms, 0);
  const cropOptions = Array.from(new Set([...((profile.data?.crops ?? []).map(c => c.crop)), ...records.map(record => record.crop)])).sort();
  const simulated = records.some(record => record.is_simulated);

  return <AppShell programme="Farmer production history"><main className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-6">
    <Link href="/demo-supply-network" className="text-sm text-muted-foreground hover:text-foreground">← Supply network</Link>
    {profile.isLoading ? <p role="status" className="py-12 text-sm text-muted-foreground">Loading farmer profile…</p>
      : profile.error ? <section role="alert" className="operational-panel p-6"><h1 className="text-xl font-semibold">Unable to load farmer profile</h1><p className="mt-2 text-sm text-destructive">{profile.error.message}</p><p className="mt-2 text-xs text-muted-foreground">Check that the backend history router is deployed and you have an active organization membership.</p></section>
      : !profile.data ? <p role="alert">Farmer profile not found.</p>
      : <>
        <header className="space-y-2"><p className="section-eyebrow">Farmer profile</p><h1 className="text-3xl font-semibold">{profile.data.name}</h1><p className="text-sm text-muted-foreground">{profile.data.parish} · {profile.data.active ? 'Active farmer' : 'Inactive farmer'}</p></header>
        <section className="grid gap-4 md:grid-cols-2"><div className="operational-panel p-5"><h2 className="font-semibold">Registered farms</h2>{profile.data.farms.length ? <ul className="mt-3 space-y-3">{profile.data.farms.map(farm => <li key={farm.id}><p className="font-medium">{farm.name}</p><p className="text-sm text-muted-foreground">{farm.parish}{farm.active ? '' : ' · Inactive'}</p></li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No farms registered.</p>}</div>
          <div className="operational-panel p-5"><h2 className="font-semibold">Registered crops</h2><div className="mt-3 flex flex-wrap gap-2">{profile.data.crops.length ? profile.data.crops.map(crop => <span key={crop.crop} className="rounded-full border border-white/10 px-3 py-1 text-xs">{readableCrop(crop.crop)}{crop.active ? '' : ' · Inactive'}</span>) : <p className="text-sm text-muted-foreground">No crops registered.</p>}</div></div></section>
        <section className="operational-panel space-y-5 p-5 sm:p-6" aria-labelledby="history-title">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="section-eyebrow">Historical reporting</p><h2 id="history-title" className="mt-1 text-xl font-semibold">Production history, 2023–2025</h2></div>{simulated && <span className="rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs text-amber-600">Simulated data</span>}</div>
          <div className="flex flex-wrap items-end gap-3"><label className="grid gap-1 text-xs text-muted-foreground">Crop<select value={crop} onChange={event => setCrop(event.target.value)} className="min-h-10 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground"><option value="ALL">All crops</option>{cropOptions.map(value => <option key={value} value={value}>{readableCrop(value)}</option>)}</select></label><label className="grid gap-1 text-xs text-muted-foreground">View<select value={period} onChange={event => setPeriod(event.target.value as 'quarterly' | 'annual')} className="min-h-10 rounded-md border border-white/10 bg-background px-3 text-sm text-foreground"><option value="quarterly">By quarter</option><option value="annual">By year</option></select></label></div>
          {history.isLoading ? <p role="status" className="py-10 text-sm text-muted-foreground">Loading production history…</p> : history.error ? <p role="alert" className="py-5 text-sm text-destructive">{history.error.message}</p> : !series.length ? <p className="py-10 text-sm text-muted-foreground">No historical production records for this selection.</p> : <>
            <div><p className="text-xs text-muted-foreground">Total production shown</p><p className="mt-1 text-2xl font-semibold tabular-nums">{formatKg(total)}</p></div>
            <div className="h-72 w-full" role="img" aria-label={`${period} production quantities for ${crop === 'ALL' ? 'all crops' : readableCrop(crop)}`}><ResponsiveContainer width="100%" height="100%"><BarChart data={series} margin={{ top: 10, right: 12, bottom: 12, left: 12 }}><CartesianGrid strokeDasharray="3 3" opacity={0.18} vertical={false} /><XAxis dataKey={period === 'annual' ? 'year' : 'quarter'} tick={{ fontSize: 11 }} angle={period === 'quarterly' ? -35 : 0} textAnchor={period === 'quarterly' ? 'end' : 'middle'} height={period === 'quarterly' ? 60 : 35} /><YAxis tick={{ fontSize: 11 }} tickFormatter={value => Number(value).toLocaleString('en-JM', { notation: 'compact' })}/><Tooltip formatter={value => formatKg(Number(value))}/><Bar dataKey="kilograms" name="Production" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]}/></BarChart></ResponsiveContainer></div>
            <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b border-white/10 text-xs text-muted-foreground"><tr><th className="py-2">{period === 'annual' ? 'Year' : 'Quarter'}</th><th className="py-2 text-right">Production (kg)</th></tr></thead><tbody>{series.map(item => <tr key={period === 'annual' ? 'year' in item ? item.year : '' : 'quarter' in item ? item.quarter : ''} className="border-b border-white/[0.06]"><td className="py-2">{'year' in item ? item.year : item.quarter}</td><td className="py-2 text-right tabular-nums">{formatKg(item.kilograms)}</td></tr>)}</tbody></table></div>
          </>}
          
        </section>
      </>}
  </main></AppShell>;
}
