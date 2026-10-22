'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import type { AgriculturalIntelligence } from '@/lib/agriculturalIntelligence';
import { modelNames } from '@/lib/agriculturalIntelligence';
import { validateIntelligence } from '@/lib/intelligenceValidation';

const fmt = (v: number, digits = 0) => v.toLocaleString('en-JM', { maximumFractionDigits: digits });
const scenarios = [
  { value: 'drought', label: 'Drought / rainfall shortfall' },
  { value: 'storm', label: 'Storm damage' },
  { value: 'disease', label: 'Crop disease pressure' },
  { value: 'improvement', label: 'Improved growing conditions' },
];

export function ScenarioLab() {
  const [kind, setKind] = useState('drought');
  const [impact, setImpact] = useState(15);
  const intel = useQuery({
    queryKey: ['agricultural-intelligence', 'iceberg_lettuce'],
    queryFn: async () => validateIntelligence(await apiFetch<unknown>('/agricultural-intelligence')),
    retry: false,
    staleTime: 60_000,
  });
  const data: AgriculturalIntelligence | undefined = intel.data;
  const forecast = data?.experiment.forecast;
  const usable = forecast?.status === 'available' && typeof forecast.value_tonnes === 'number';
  const baseline = usable ? forecast.value_tonnes! : null;
  const multiplier = kind === 'improvement' ? 1 + impact / 100 : 1 - impact / 100;
  const adjusted = baseline === null ? null : Math.max(0, baseline * multiplier);
  const change = baseline === null || adjusted === null ? null : adjusted - baseline;
  const latest = data?.series[data.series.length - 1];
  const history = data?.series.slice(-16).map(p => ({ period: p.period, production_tonnes: p.production_tonnes })) ?? [];

  return <AppShell programme="Jamaica · Agricultural forecasting scenarios">
    <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <header>
        <p className="section-eyebrow">KoroFarm · Forecasting / What-if analysis</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Scenario Lab</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">Explore hypothetical production changes relative to the validated agricultural forecasting artifact. Scenarios are sensitivity calculations, not model-generated forecasts.</p>
        <div className="mt-4 flex flex-wrap gap-3 text-sm"><span className="rounded border border-warning/30 bg-warning/10 px-3 py-2 text-warning">SIMULATION · No live writes</span><Link className="rounded border border-white/20 px-3 py-2 underline underline-offset-4" href="/intelligence-lab">Open Intelligence Lab →</Link></div>
      </header>

      {intel.isLoading && <section role="status" className="operational-panel p-6">Loading validated forecasting data…</section>}
      {intel.isError && <section role="alert" className="operational-panel p-6"><h2 className="font-semibold">Forecast data unavailable</h2><p className="mt-2 text-sm text-muted-foreground">{intel.error.message}</p><p className="mt-2 text-xs text-muted-foreground">Confirm the backend exposes GET /agricultural-intelligence and its validated artifact is present.</p><button type="button" onClick={() => void intel.refetch()} className="mt-4 rounded border border-white/20 px-4 py-2 text-sm">Retry</button></section>}
      {data && <>
        <section className="operational-panel p-5">
          <p className="section-eyebrow">Verified dataset scope</p>
          <h2 className="mt-2 text-xl font-semibold">{data.country} · {data.crop_label}</h2>
          <p className="mt-2 text-sm text-muted-foreground">National estimates, not farm-level output. Latest historical period: {latest?.period ?? 'Unavailable'}. Historical data and experimental model results come from the same validated artifact used in Intelligence Lab.</p>
          <p className="mt-2 text-xs text-muted-foreground">Dataset version: <span className="break-all font-mono">{data.dataset_version}</span></p>
        </section>
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="operational-panel p-5">
            <h2 className="text-lg font-semibold">Scenario inputs</h2>
            <label htmlFor="scenario-kind" className="mt-5 block text-sm font-medium">Hypothetical condition</label>
            <select id="scenario-kind" className="mt-2 h-11 w-full rounded border border-white/20 bg-secondary px-3 text-sm" value={kind} onChange={e => setKind(e.target.value)}>{scenarios.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
            <label htmlFor="impact" className="mt-6 flex justify-between text-sm font-medium"><span>Assumed production impact</span><strong>{impact}%</strong></label>
            <input id="impact" className="mt-3 w-full accent-primary" type="range" min="0" max="50" step="5" value={impact} onChange={e => setImpact(Number(e.target.value))}/>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">The percentage is a user-selected assumption. It is not estimated from weather, disease, or farm sensor data.</p>
            <div className="mt-6 rounded border border-white/10 p-3 text-xs text-muted-foreground">Read-only. No buyer requirements, farmer commitments or production lots are modified.</div>
          </aside>
          <div className="space-y-5">
            <section className="grid gap-4 sm:grid-cols-3" aria-label="Scenario comparison">
              <Metric label="Model baseline" value={baseline === null ? 'Unavailable' : `${fmt(baseline, 1)} tonnes`} />
              <Metric label="Hypothetical output" value={adjusted === null ? 'Unavailable' : `${fmt(adjusted, 1)} tonnes`} />
              <Metric label="Difference" value={change === null ? 'Unavailable' : `${change >= 0 ? '+' : ''}${fmt(change, 1)} tonnes`} />
            </section>
            <section className="operational-panel p-5">
              <h2 className="text-lg font-semibold">Forecast basis</h2>
              <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="text-muted-foreground">Reference model</dt><dd className="mt-1">{forecast ? (modelNames[forecast.model] ?? forecast.model) : 'Unavailable'}</dd></div><div><dt className="text-muted-foreground">Forecast target</dt><dd className="mt-1">{forecast?.period ?? 'Unavailable'}</dd></div><div><dt className="text-muted-foreground">Data cutoff</dt><dd className="mt-1">{forecast?.data_cutoff ?? 'Unavailable'}</dd></div><div><dt className="text-muted-foreground">Horizon</dt><dd className="mt-1">{forecast?.horizon_quarters ?? 'Unavailable'} quarter ahead</dd></div></dl>
              {!usable && <p className="mt-4 text-sm text-warning">{forecast?.unavailable_reason || 'Forecast unavailable — insufficient validated data.'} Scenario results are intentionally withheld.</p>}
              <p className="mt-4 text-xs leading-5 text-muted-foreground">The selected model is not retrained or rerun when you move the slider. The hypothetical output equals model baseline × (1 ± assumed impact). This does not estimate probability, farm availability, demand shortfall or revenue loss.</p>
            </section>
            <section className="operational-panel p-5">
              <h2 className="text-lg font-semibold">Recent observed production</h2>
              <p className="mt-1 text-xs text-muted-foreground">Tonnes · most recent 16 quarterly observations; gaps remain gaps</p>
              <div className="mt-4 h-64 min-w-0"><ResponsiveContainer width="100%" height="100%"><AreaChart data={history}><CartesianGrid stroke="#ffffff15" vertical={false}/><XAxis dataKey="period" tick={{ fontSize: 10, fill: '#9ca3af' }} minTickGap={25}/><YAxis tick={{ fontSize: 10, fill: '#9ca3af' }}/><Tooltip contentStyle={{backgroundColor:'#15201d',color:'#fff'}}/><Area type="linear" dataKey="production_tonnes" connectNulls={false} stroke="#82ba77" fill="#82ba7720" name="Observed production (tonnes)" isAnimationActive={false}/></AreaChart></ResponsiveContainer></div>
            </section>
          </div>
        </div>
      </>}
    </main>
  </AppShell>;
}

function Metric({label,value}:{label:string;value:string}) {
  return <section className="operational-panel p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 text-xl font-semibold tabular-nums">{value}</p></section>;
}
