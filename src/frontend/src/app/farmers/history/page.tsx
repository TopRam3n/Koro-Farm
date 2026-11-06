'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, History, Search, Users } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { AuthGate } from '@/components/AuthGate';
import { FarmerHistoryProfile } from '@/components/FarmerHistoryProfile';
import { useIdentity } from '@/hooks/useIdentity';
import { getFarmerHistoryDirectory } from '@/lib/farmerHistory';

const STAFF_ROLES = new Set([
  'PLATFORM_ADMIN', 'ORGANIZATION_ADMIN', 'PROCUREMENT_MANAGER',
  'SUPPLY_COORDINATOR', 'WAREHOUSE_OPERATOR', 'AUDITOR',
]);
const PAGE_SIZE = 24;

function HistoricalProductionLanding() {
  const identity = useIdentity();
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const role = identity.data?.active_role ?? '';
  const isStaff = STAFF_ROLES.has(role);

  const directory = useQuery({
    queryKey: ['farmer-history-directory', search, offset],
    queryFn: () => getFarmerHistoryDirectory({ q: search, offset, limit: PAGE_SIZE }),
    enabled: !identity.isLoading && isStaff,
    staleTime: 30_000,
  });

  if (identity.isLoading) return <div role="status" className="p-10 text-sm text-muted-foreground">Loading your farmer workspace…</div>;
  if (identity.error || !identity.data) return <div role="alert" className="p-10 text-sm text-destructive">Unable to load your account: {identity.error?.message ?? 'No linked account'}</div>;

  if (role === 'FARMER') {
    if (identity.data.active_farmer_id) {
      // Use the same authenticated farmer ID returned by /me. Never accept an arbitrary ID from the browser.
      return <FarmerHistoryProfile farmerId={identity.data.active_farmer_id} />;
    }
    return <AppShell programme="Farmer production history"><main className="mx-auto max-w-3xl px-5 py-12"><section className="operational-panel p-6" role="alert"><AlertTriangle className="mb-3 h-5 w-5 text-amber-500" /><h1 className="text-2xl font-semibold">Farmer account not linked</h1><p className="mt-3 text-sm text-muted-foreground">Your active membership does not have a farmer profile ID. An organization administrator must link your account to the correct farmer record. Production history cannot be inferred from your name or email.</p></section></main></AppShell>;
  }

  if (!isStaff) return <AppShell programme="Production history"><main className="mx-auto max-w-3xl px-5 py-12"><section className="operational-panel p-6" role="alert"><h1 className="text-2xl font-semibold">Farmer history is not available to this role</h1><p className="mt-3 text-sm text-muted-foreground">Only linked farmers and authorized supply staff can view farmer production histories.</p></section></main></AppShell>;

  const result = directory.data;
  const canPrev = offset > 0;
  const canNext = !!result && offset + result.items.length < result.total;

  return <AppShell programme="KoroFarm · Farmer History"><main className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
    <header className="space-y-2"><p className="section-eyebrow">Supply network / historical reporting</p><h1 className="text-3xl font-semibold tracking-tight">Farmer History</h1><p className="max-w-3xl text-sm text-muted-foreground">Explore registered farmers and historical production in your organization. Historical yields are not available-to-sell inventory or accepted procurement commitments.</p></header>
    <section className="operational-panel p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4"><div className="flex items-center gap-3"><Users className="h-5 w-5 text-primary"/><div><h2 className="font-semibold">Farmer directory</h2><p className="text-xs text-muted-foreground">{result ? `${result.total} farmers found` : 'Scoped to your organization'}</p></div></div>
        <label className="relative block w-full sm:w-80"><span className="sr-only">Search farmers or parishes</span><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"/><input className="w-full rounded-md border border-white/15 bg-background py-2 pl-10 pr-3 text-sm" value={search} onChange={event => {setSearch(event.target.value); setOffset(0);}} placeholder="Search farmer or parish" /></label>
      </div>
      {directory.isLoading && <p role="status" className="mt-6 text-sm text-muted-foreground">Loading farmer directory…</p>}
      {directory.error && <p role="alert" className="mt-6 text-sm text-destructive">Unable to load farmer directory: {directory.error.message}</p>}
      {!directory.isLoading && result?.items.length === 0 && <div className="mt-6 rounded-lg border border-dashed border-white/15 px-5 py-10 text-center"><History className="mx-auto h-5 w-5 text-muted-foreground"/><p className="mt-3 text-sm font-medium">No matching farmers found</p><p className="mt-1 text-xs text-muted-foreground">Check the search term or verify that farmers have been registered in this organization.</p></div>}
      {result && result.items.length > 0 && <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[690px] text-left text-sm"><thead className="border-b border-white/10 text-xs text-muted-foreground"><tr><th className="px-3 py-3">Farmer</th><th className="px-3 py-3">Parish</th><th className="px-3 py-3">History</th><th className="px-3 py-3">Account</th><th className="px-3 py-3 text-right">Open</th></tr></thead><tbody>{result.items.map(farmer => <tr key={farmer.id} className="border-b border-white/[0.06]"><td className="px-3 py-4 font-medium">{farmer.name}</td><td className="px-3 py-4">{farmer.parish}</td><td className="px-3 py-4 text-muted-foreground">{farmer.history_record_count ? `${farmer.history_record_count} records · ${farmer.first_year}–${farmer.last_year}` : 'No records imported'}</td><td className="px-3 py-4">{farmer.active ? 'Active' : 'Inactive'}</td><td className="px-3 py-4 text-right"><Link className="inline-flex items-center gap-1 text-primary hover:underline" href={`/farmers/${farmer.id}`}>View profile <ArrowRight className="h-4 w-4"/></Link></td></tr>)}</tbody></table></div>}
      {result && result.total > PAGE_SIZE && <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/10 pt-4"><p className="text-xs text-muted-foreground">Showing {Math.min(offset + 1, result.total)}–{Math.min(offset + result.items.length, result.total)} of {result.total}</p><div className="flex gap-2"><button type="button" disabled={!canPrev} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="rounded-md border border-white/15 px-3 py-2 text-xs disabled:opacity-40">Previous</button><button type="button" disabled={!canNext} onClick={() => setOffset(offset + PAGE_SIZE)} className="rounded-md border border-white/15 px-3 py-2 text-xs disabled:opacity-40">Next</button></div></div>}
    </section>
  </main></AppShell>;
}

export default function Page() { return <AuthGate><HistoricalProductionLanding /></AuthGate>; }
