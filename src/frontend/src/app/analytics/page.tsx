'use client';
import { useQuery } from '@tanstack/react-query';
import { AuthGate } from '@/components/AuthGate';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';

type Requirement = { id: string; buyer_name: string; crop: string; grade: string; status: string;
  requested_kg: string; accepted_kg: string; outstanding_kg: string; delivery_start: string; delivery_end: string };
type Summary = { scope: string; totals: { requirements: number; participating_farmers: number;
  requested_kg: string; accepted_kg: string; outstanding_kg: string }; items: Requirement[]; note: string };
const kg = (value: string) => `${Number(value).toLocaleString('en-JM', {maximumFractionDigits: 3})} kg`;
function Analytics() {
  const query = useQuery({ queryKey: ['marketplace-analytics'], queryFn: () => apiFetch<Summary>('/marketplace/analytics/summary') });
  return <AppShell programme="Analytics"><main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
    <header><p className="section-eyebrow">Marketplace intelligence</p><h1 className="mt-2 text-3xl font-semibold">Analytics</h1><p className="mt-2 text-sm text-muted-foreground">Current buyer demand and accepted farmer commitments, from live records.</p></header>
    {query.isLoading && <p role="status">Loading analytics…</p>}
    {query.isError && <section role="alert" className="operational-panel p-5"><h2 className="font-semibold">Unable to load analytics</h2><p className="mt-2 text-sm text-destructive">{query.error.message}</p></section>}
    {query.data && <><p className="text-xs uppercase tracking-wide text-muted-foreground">Scope: {query.data.scope}</p>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{[
        ['Requirements', String(query.data.totals.requirements)],
        ['Requested', kg(query.data.totals.requested_kg)],
        ['Accepted offers', kg(query.data.totals.accepted_kg)],
        ['Outstanding', kg(query.data.totals.outstanding_kg)],
        ['Participating farmers', String(query.data.totals.participating_farmers)]
      ].map(([label, value]) => <div key={label} className="operational-panel p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 text-xl font-semibold tabular-nums">{value}</p></div>)}</section>
      <section className="operational-panel overflow-x-auto p-5"><h2 className="mb-4 text-lg font-semibold">Requirements and coverage</h2>
        {!query.data.items.length ? <p className="text-sm text-muted-foreground">No buyer requirements are available for this account.</p> :
        <table className="w-full min-w-[650px] text-left text-sm"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-3">Buyer / crop</th><th>Status</th><th className="text-right">Requested</th><th className="text-right">Accepted</th><th className="text-right">Outstanding</th></tr></thead><tbody>{query.data.items.map(item => <tr key={item.id} className="border-b border-border/50"><td className="py-3">{item.buyer_name}<div className="text-xs text-muted-foreground">{item.crop} · Grade {item.grade}</div></td><td>{item.status}</td><td className="text-right tabular-nums">{kg(item.requested_kg)}</td><td className="text-right tabular-nums">{kg(item.accepted_kg)}</td><td className="text-right tabular-nums">{kg(item.outstanding_kg)}</td></tr>)}</tbody></table>}</section>
      <p className="text-xs text-muted-foreground">{query.data.note}</p>
    </>}
  </main></AppShell>;
}
export default function Page() { return <AuthGate><Analytics /></AuthGate>; }
