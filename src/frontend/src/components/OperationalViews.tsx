'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

type Lot = { id:string; farmer_name:string; parish:string; crop:string; grade:string; available_kg:string; reserved_kg:string; unreserved_kg:string; status:string; confidence:string; harvest_start:string; harvest_end:string; last_verified_at:string|null };
type Trace = { id:string; status:string; quantity_kg:string; created_at:string|null; farmer_name:string; buyer_name:string; parish:string; crop:string; grade:string; requirement_id:string; production_lot_id:string; delivery_window_start:string; delivery_window_end:string; fulfilment_status:string };
type Rule = { id:string; name:string; issuing_body:string; description:string; source_citation:string; source_version:string; required_before:string; verified_at:string };
type Check = { requirement_id:string; buyer_name:string; crop:string; grade:string; status:string; corridor_supported:boolean; rules:Rule[] };
type SupplyData = { scope:string; items:Lot[]; totals:{lots:number; available_kg:string; reserved_kg:string; unreserved_kg:string}; note:string };
type TraceData = { scope:string; items:Trace[]; note:string };
type ComplianceData = { scope:string; items:Check[]; note:string };
type ViewKind = 'supply'|'traceability'|'compliance';
const human=(s:string)=>s.replace(/_/g,' ');
const kg=(s:string)=>`${Number(s).toLocaleString('en-JM',{maximumFractionDigits:3})} kg`;
const date=(s:string|null)=>s ? s.slice(0,10) : 'Unavailable';
const badge=(status:string)=>status==='ACCEPTED'||status==='VERIFIED_RULES_ON_FILE' ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25' : 'text-amber-300 bg-amber-500/10 border-amber-500/25';

export function OperationalViews({kind}:{kind:ViewKind}) {
  const [data,setData]=useState<SupplyData|TraceData|ComplianceData|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const refresh=useCallback(async()=>{
    setLoading(true);setError('');
    try { const response=await apiFetch<SupplyData|TraceData|ComplianceData>(`/marketplace/operations/${kind}`);setData(response); }
    catch(e){setError(e instanceof Error?e.message:String(e));setData(null);}
    finally{setLoading(false);}
  },[kind]);
  useEffect(()=>{void refresh();},[refresh]);
  const titles={supply:'Supply Network',traceability:'Traceability',compliance:'Compliance'};
  const descriptions={supply:'Verified lots, unreserved inventory and stock committed to supply.',traceability:'Follow recorded farmer offers from production lot to procurement request.',compliance:'Inspect verified rules on file for the requests visible to your account.'};
  return <AppShell programme={titles[kind]}><main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-emerald-400">KoroFarm Operations</p><h1 className="mt-2 text-3xl font-semibold">{titles[kind]}</h1><p className="mt-2 text-sm text-slate-400">{descriptions[kind]}</p></div><button type="button" onClick={()=>void refresh()} disabled={loading} className="rounded-lg border border-white/20 px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-50">Refresh</button></div>
    <nav className="flex flex-wrap gap-2 text-sm"><Link href="/supply" className="rounded border border-white/15 px-3 py-2">Supply Network</Link><Link href="/traceability" className="rounded border border-white/15 px-3 py-2">Traceability</Link><Link href="/compliance" className="rounded border border-white/15 px-3 py-2">Compliance</Link></nav>
    {loading && <p role="status" className="text-slate-400">Loading live records…</p>}
    {error && <section role="alert" className="rounded-xl border border-red-500/30 p-5"><strong>Unable to load records</strong><p className="mt-2 text-sm text-red-300">{error}</p></section>}
    {!loading&&!error&&data&&kind==='supply'&&<SupplySection data={data as SupplyData}/>}
    {!loading&&!error&&data&&kind==='traceability'&&<TraceSection data={data as TraceData}/>}
    {!loading&&!error&&data&&kind==='compliance'&&<ComplianceSection data={data as ComplianceData}/>}
  </main></AppShell>;
}
function SupplySection({data}:{data:SupplyData}){return <div className="space-y-5"><div className="grid gap-3 sm:grid-cols-4">{([['Lots',String(data.totals.lots)],['Reported stock',kg(data.totals.available_kg)],['Reserved',kg(data.totals.reserved_kg)],['Unreserved',kg(data.totals.unreserved_kg)]] as const).map(([label,value])=><div key={label} className="rounded-xl border border-white/10 bg-white/[0.03] p-4"><p className="text-xs text-slate-400">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}</div>{!data.items.length&&<Empty text="No production lots found in your permitted scope."/>}<div className="grid gap-3 md:grid-cols-2">{data.items.map(l=><article key={l.id} className="rounded-xl border border-white/10 p-5"><div className="flex justify-between gap-3"><h2 className="font-semibold">{human(l.crop)} · Grade {l.grade}</h2><span className="text-xs text-slate-400">{human(l.status)}</span></div><p className="mt-1 text-sm text-slate-400">{l.farmer_name} · {l.parish}</p><div className="mt-4 grid grid-cols-3 gap-2 text-sm"><div>Reported<br/><b>{kg(l.available_kg)}</b></div><div>Reserved<br/><b>{kg(l.reserved_kg)}</b></div><div>Unreserved<br/><b className="text-emerald-300">{kg(l.unreserved_kg)}</b></div></div><p className="mt-3 text-xs text-slate-400">Harvest {l.harvest_start} – {l.harvest_end} · Confidence: {human(l.confidence)} · Verified: {date(l.last_verified_at)}</p><p className="mt-2 break-all font-mono text-[10px] text-slate-500">Lot {l.id}</p></article>)}</div><p className="text-xs text-slate-400">{data.note}</p></div>}
function TraceSection({data}:{data:TraceData}){return <div className="space-y-3">{!data.items.length&&<Empty text="No linked farmer offers recorded yet."/>}{data.items.map(t=><article key={t.id} className="rounded-xl border border-white/10 p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-lg font-semibold">{human(t.crop)} · {kg(t.quantity_kg)}</h2><p className="text-sm text-slate-400">{t.farmer_name} → {t.buyer_name}</p></div><span className={`h-fit rounded-full border px-3 py-1 text-xs ${badge(t.status)}`}>{human(t.status)}</span></div><p className="mt-3 text-sm text-slate-300">Grade {t.grade} · Origin {t.parish} · Delivery window {t.delivery_window_start} – {t.delivery_window_end}</p><div className="mt-3 space-y-1 break-all font-mono text-[11px] text-slate-500"><p>Production lot: {t.production_lot_id}</p><p>Buyer request: {t.requirement_id}</p><p>Offer: {t.id}</p></div><p className="mt-3 text-xs text-amber-300">Physical fulfilment: not linked; delivery is not confirmed.</p></article>)}<p className="text-xs text-slate-400">{data.note}</p></div>}
function ComplianceSection({data}:{data:ComplianceData}){return <div className="space-y-3">{!data.items.length&&<Empty text="No relevant procurement requests found."/>}{data.items.map(c=><article key={c.requirement_id} className="rounded-xl border border-white/10 p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="font-semibold">{human(c.crop)} · Grade {c.grade}</h2><p className="text-sm text-slate-400">{c.buyer_name}</p></div><span className={`h-fit rounded-full border px-3 py-1 text-xs ${badge(c.status)}`}>{human(c.status)}</span></div>{!c.corridor_supported&&<p className="mt-3 text-sm text-amber-300">Cross-border requirements need corridor-specific verified rules.</p>}{!c.rules.length&&<p className="mt-3 text-sm text-amber-300">No currently verified applicable rule is on file. This does not mean no rules apply.</p>}{c.rules.map(r=><div key={r.id} className="mt-3 rounded-lg border border-white/10 p-3"><h3 className="font-medium">{r.name}</h3><p className="mt-1 text-sm text-slate-400">{r.issuing_body} · Before: {r.required_before}</p><p className="mt-2 text-sm">{r.description}</p><p className="mt-2 break-words text-xs text-slate-400">Source: {r.source_citation} · Version {r.source_version} · Verified {date(r.verified_at)}</p></div>)}</article>)}<p className="text-xs text-slate-400">{data.note}</p></div>}
function Empty({text}:{text:string}){return <div className="rounded-xl border border-dashed border-white/20 p-10 text-center text-sm text-slate-400">{text}</div>}
