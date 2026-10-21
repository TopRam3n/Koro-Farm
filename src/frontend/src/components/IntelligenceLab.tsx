'use client';

import { useQuery } from '@tanstack/react-query';
import { AreaChart, Area, CartesianGrid, LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { AgriculturalIntelligence, modelNames } from '@/lib/agriculturalIntelligence';
import { validateIntelligence } from '@/lib/intelligenceValidation';

const number = (v: number | null | undefined, decimals = 0) => v == null ? 'Unavailable' : v.toLocaleString('en-JM', { maximumFractionDigits: decimals, minimumFractionDigits: decimals });

export function IntelligenceLab() {
  const query = useQuery({ queryKey: ['agricultural-intelligence', 'iceberg_lettuce'], queryFn: async () => validateIntelligence(await apiFetch<unknown>('/agricultural-intelligence')), retry: false, staleTime: 60_000 });
  return <AppShell programme="Jamaica · National agricultural statistics"><main className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
    <header><p className="section-eyebrow">KoroFarm — Agricultural Intelligence & Coordination Infrastructure for the Caribbean</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Intelligence Lab</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">Understand production. Anticipate risk. Coordinate action. Strengthen economic resilience across the Caribbean.</p></header>
    {query.isLoading ? <p role="status">Loading official agricultural statistics…</p> : query.isError ? <div role="alert" className="operational-panel p-6"><h2 className="font-semibold">Agricultural intelligence unavailable</h2><p className="mt-2 text-sm text-muted-foreground">{query.error.message}</p><button onClick={() => query.refetch()} className="mt-4 min-h-11 rounded border px-4 text-sm">Retry data request</button></div> : query.data ? <IntelligenceContent data={query.data} /> : <p>Forecast unavailable — insufficient validated historical data</p>}
  </main></AppShell>;
}

export function IntelligenceContent({ data }: { data: AgriculturalIntelligence }) {
  try { validateIntelligence(data); } catch { return <div role="alert"><h2>Agricultural intelligence unavailable</h2><p>The cached artifact is incomplete or invalid. Restore the verified snapshot or retry the data request.</p></div>; }
  const { series, experiment, quality } = data;
  const latest = series.at(-1);
  const forecast = experiment.forecast;
  return <>
    <section aria-label="Selected national dataset" className="operational-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="section-eyebrow">Observed national estimates</p><h2 className="mt-2 text-xl font-semibold">{data.country} · {data.crop_label}</h2></div><p className="text-sm text-muted-foreground">Latest reporting period: <strong className="text-foreground">{latest?.period ?? 'Unavailable'}</strong></p></div>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">Ministry of Agriculture, Fisheries and Mining. National estimates are separate from farmer stock, buyer commitments and the synthetic ginger demonstration.</p>
      <p className="mt-2 text-xs text-muted-foreground">Last ingestion: {data.last_ingested_at.slice(0,10)} · {process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? 'Cached official-data snapshot in demo mode' : 'Validated offline artifact served by the authenticated API'}</p>
    </section>
    <section className="grid gap-4 sm:grid-cols-3" aria-label="Latest historical observations">
      <Stat label={`Production · ${latest?.period ?? 'no period'}`} value={`${number(latest?.production_tonnes)} tonnes`} />
      <Stat label={`Farmgate price · ${latest?.period ?? 'no period'}`} value={`J$${number(latest?.farmgate_price_jmd_kg,2)}/kg`} />
      <Stat label="Validated quarterly coverage · 2016–2025" value={`${quality.validated_counts.production} / 40 production records`} />
    </section>
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="operational-panel min-w-0 p-5" aria-label="Historical production chart"><h2 className="text-lg font-semibold">Observed production</h2><p className="mt-1 text-xs text-muted-foreground">Tonnes · 2016 Q1–2025 Q4 · Ministry national estimates</p><div className="mt-5 h-64 min-w-0" role="img" aria-label="Quarterly iceberg lettuce production, with a gap for disputed 2016 Q3">
        <ResponsiveContainer width="100%" height="100%"><AreaChart data={series} margin={{ left: 0, right: 10 }}><CartesianGrid stroke="#ffffff12" vertical={false} /><XAxis dataKey="period" tick={{ fontSize: 10, fill: '#9ca3af' }} minTickGap={45} /><YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} width={45} /><Tooltip contentStyle={{ backgroundColor: '#15201d', borderColor: '#33443e', color: '#fff' }} /><Area name="Observed tonnes" dataKey="production_tonnes" type="linear" connectNulls={false} stroke="#82ba77" fill="#82ba7720" isAnimationActive={false} /></AreaChart></ResponsiveContainer>
      </div><p className="mt-2 text-xs text-muted-foreground">2016 Q3 is quarantined; the chart leaves a gap.</p></section>
      <section className="operational-panel min-w-0 p-5" aria-label="Historical farmgate price chart"><h2 className="text-lg font-semibold">Observed farmgate prices</h2><p className="mt-1 text-xs text-muted-foreground">JMD/kg · 2016 Q1–2025 Q4 · historical prices, not delivered prices</p><div className="mt-5 h-64 min-w-0" role="img" aria-label="Quarterly observed farmgate prices in Jamaican dollars per kilogram">
        <ResponsiveContainer width="100%" height="100%"><LineChart data={series} margin={{ left: 0, right: 10 }}><CartesianGrid stroke="#ffffff12" vertical={false} /><XAxis dataKey="period" tick={{ fontSize: 10, fill: '#9ca3af' }} minTickGap={45} /><YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} width={45} /><Tooltip contentStyle={{ backgroundColor: '#15201d', borderColor: '#33443e', color: '#fff' }} /><Line name="Observed JMD/kg" dataKey="farmgate_price_jmd_kg" type="linear" stroke="#d5b976" dot={false} connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer>
      </div><p className="mt-2 text-xs text-muted-foreground">Production and price movements do not establish causation.</p></section>
    </div>
    <section aria-label="Experimental forecast" className="operational-panel border-l-4 border-l-warning p-5 sm:p-6">
      <p className="section-eyebrow">Experimental forecast — not a verified shortage prediction</p>
      <h2 className="mt-3 text-xl font-semibold">{forecast.status === 'available' && forecast.value_tonnes != null ? `${forecast.period}: ${number(forecast.value_tonnes)} tonnes` : 'Forecast unavailable — insufficient validated historical data'}</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{forecast.label}</p>
      <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3"><div><dt className="text-muted-foreground">Forecast horizon</dt><dd className="mt-1">{forecast.horizon_quarters} quarter ahead</dd></div><div><dt className="text-muted-foreground">Data cutoff</dt><dd className="mt-1">{forecast.data_cutoff ?? 'Unavailable'}</dd></div><div><dt className="text-muted-foreground">Reference model</dt><dd className="mt-1">{modelNames[forecast.model] ?? forecast.model}</dd></div></dl>
      <p className="mt-4 text-xs leading-5 text-muted-foreground">No calibrated uncertainty interval is available. Generated {data.generated_at.slice(0,10)}. This forecast does not establish demand-adjusted shortages and does not trigger operational actions.</p>
    </section>
    <section className="operational-panel p-5"><h2 className="text-lg font-semibold">Backtesting against seasonality</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Expanding training windows start in 2016. All models are evaluated on the same 20 one-quarter-ahead targets, 2021 Q1–2025 Q4. Bias is forecast minus observed production; negative means underprediction.</p>
      <MetricTable metrics={experiment.metrics.all} selected={experiment.selected_model} />
      <p className="mt-4 text-sm leading-6 text-warning">Preliminary retrospective evidence only. The 2024–2025 evaluation window was used in release selection; it is not an untouched independent holdout.</p>
      <details className="mt-5"><summary className="min-h-11 cursor-pointer text-sm font-medium">Selection and later evaluation windows</summary><p className="text-sm leading-6 text-muted-foreground">{experiment.selection_rule}</p><h3 className="mt-4 text-sm font-semibold">2021–2023 · selection window</h3><MetricTable metrics={experiment.metrics.selection} /><h3 className="mt-4 text-sm font-semibold">2024–2025 · later evaluation used in release selection</h3><MetricTable metrics={experiment.metrics.holdout} /></details>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">{experiment.availability_assumption}</p>
    </section>
    <section className="operational-panel p-5"><h2 className="text-lg font-semibold">Data quality & limitations</h2><ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-muted-foreground">{data.limitations.map(note => <li key={note}>{note}</li>)}</ul>
      {quality.conflicts.map(conflict => <div key={conflict.id} className="mt-4 rounded border border-warning/30 p-4 text-sm"><h3 className="font-semibold">Quarantined: {conflict.period} {conflict.measurement}</h3><p className="mt-1 text-muted-foreground">{conflict.reason}</p><ul className="mt-2 space-y-2">{conflict.values.map((v,i) => <li key={i}><a className="text-primary underline" href={v.url} target="_blank" rel="noreferrer">Original PDF, page {v.page}: {number(v.value)} tonnes</a></li>)}</ul></div>)}
    </section>
    <section className="operational-panel p-5"><h2 className="text-lg font-semibold">Provenance & methodology</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Original PDF text layers are parsed with explicit crop aliases, period and unit checks. Overlapping sources are reconciled and conflicting cells quarantined. Missing values remain missing. No national statistics are allocated to fictional farmers.</p><dl className="mt-4 space-y-2 text-xs text-muted-foreground"><div><dt>Dataset version</dt><dd className="break-all font-mono">{data.dataset_version}</dd></div><div><dt>Model artifact version</dt><dd className="break-all font-mono">{data.artifact_version}</dd></div><div><dt>Source publication dates</dt><dd>Unknown; HTTP modification times are preserved but do not establish historical availability.</dd></div></dl>
      <details className="mt-4"><summary className="min-h-11 cursor-pointer text-sm font-medium">Original sources ({data.sources.length} PDFs)</summary><ul className="space-y-3 text-xs">{data.sources.map(source => <li key={source.sha256}><a href={source.url} className="text-primary underline" target="_blank" rel="noreferrer">{source.year} · {source.kind} · {source.label}</a><p className="mt-1 break-all text-muted-foreground">{source.local_path}</p></li>)}</ul></details>
      <details className="mt-4"><summary className="min-h-11 cursor-pointer text-sm font-medium">Accessible historical observation table</summary><div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="sr-only">Observed quarterly national iceberg lettuce statistics</caption><thead><tr><th className="py-3">Quarter</th><th>Production (tonnes)</th><th>Farmgate (JMD/kg)</th><th>Area (hectares)</th></tr></thead><tbody>{series.map(row => <tr key={row.period} className="border-t border-white/[0.07]"><th className="py-3 font-normal">{row.period}</th><td>{number(row.production_tonnes)}</td><td>{number(row.farmgate_price_jmd_kg,2)}</td><td>{number(row.area_hectares)}</td></tr>)}</tbody></table></div></details>
    </section>
    <section aria-label="Separate FAOSTAT annual context" className="operational-panel p-5"><p className="section-eyebrow">FAOSTAT · Annual national context</p><h2 className="mt-2 text-lg font-semibold">{data.annual_context?.item_label ?? 'FAOSTAT annual observations'}</h2>
      {data.annual_context?.status === 'available' ? <>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">The Jamaica QCL dataset contains {number(data.annual_context.validation?.observations)} annual production and harvested-area observations across {data.annual_context.validation?.items.length} source item categories, including aggregates. Coverage: {data.annual_context.validation?.years[0]}–{data.annual_context.validation?.years.at(-1)}. Requested 2025 observations were not returned.</p>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Lettuce and chicory is a broader FAOSTAT category. It is not mapped to Ministry iceberg lettuce, not divided into quarters and not used in this forecasting experiment. Source estimates, imputations and official-value flags are preserved; validation checks the import, not independent measurement accuracy.</p>
        <a className="mt-3 inline-flex min-h-11 items-center text-sm text-primary underline" href="https://www.fao.org/faostat/en/#data/QCL" target="_blank" rel="noreferrer">Official FAOSTAT QCL dataset</a>
        <details className="mt-3"><summary className="min-h-11 cursor-pointer text-sm font-medium">Inspect separate annual lettuce/chicory observations</summary><div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="py-3">Year</th><th>Source measurement</th><th>Value</th><th>Original unit</th><th>Source classification</th></tr></thead><tbody>{data.annual_context.records.map(row => <tr key={row.id} className="border-t border-white/[0.07]"><th className="py-3 font-normal">{row.year}</th><td>{row.measurement}</td><td>{number(row.value,2)}</td><td>{row.unit}</td><td>{row.flag}: {row.flag_description}</td></tr>)}</tbody></table></div></details>
        <p className="mt-3 break-all text-xs text-muted-foreground">Annual dataset version: {data.annual_context.dataset_version} · Retrieved {data.annual_context.retrieved_at?.slice(0,10)}. Historical publication vintages remain unknown.</p>
      </> : <p className="mt-3 text-sm text-muted-foreground">{data.annual_context?.reason ?? 'No validated FAOSTAT annual dataset is available.'}</p>}
    </section>
    <section className="operational-panel p-5"><p className="section-eyebrow">Value Pathways · Concept / Planned</p><h2 className="mt-2 text-lg font-semibold">From production intelligence to economic opportunity</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Future work could combine production signals with verified processing capacity, prices, quality requirements and transport costs to compare fresh sales, storage and processing. This capability is planned; no processing optimization service is implemented.</p></section>
  </>;
}

function MetricTable({ metrics, selected }: { metrics: Record<string, AgriculturalIntelligence['experiment']['metrics']['all'][string]>; selected?: string }) {
  return <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs sm:text-sm"><thead><tr><th className="min-w-44 py-3 pr-4">Model</th><th className="min-w-24 pr-4">MAE (tonnes)</th><th className="min-w-20 pr-4">WAPE</th><th className="min-w-24 pr-4">Bias (tonnes)</th><th>Forecasts</th></tr></thead><tbody>{Object.entries(metrics).map(([model,m]) => <tr key={model} className="border-t border-white/[0.07]"><th className="py-3 pr-4 font-normal">{modelNames[model] ?? model}{model === selected && <span className="ml-2 text-primary">Selected</span>}</th><td>{number(m.mae_tonnes,1)}</td><td>{number(m.wape_pct,2)}%</td><td>{number(m.bias_tonnes,1)}</td><td>{m.n}</td></tr>)}</tbody></table></div>;
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="operational-panel p-5"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>;
}
