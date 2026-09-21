'use client';

import { Activity, BarChart3, Bell, Building2, CheckCircle2, ClipboardCheck, Command, FileCheck2, FlaskConical, GitBranch, LayoutDashboard, ListTodo, Menu, Network, PackageCheck, Search, Settings, ShieldCheck, SlidersHorizontal, Sprout, Tractor, Unplug, UserRoundCog, Workflow, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

type NavItem = readonly [string, string, typeof LayoutDashboard];
type NavGroup = { label: string; items: readonly NavItem[] };

const groups: readonly NavGroup[] = [
  { label: 'My Work', items: [['My Work', '/', ListTodo], ['Command Center', '/command-center', LayoutDashboard]] },
  { label: 'Operations', items: [['Programmes', '/programmes', Building2], ['Demand', '/demand', ClipboardCheck], ['Supply Network', '/supply', Tractor], ['Assurance', '/assurance', ShieldCheck], ['Fulfilment', '/fulfilment', PackageCheck]] },
  { label: 'Intelligence', items: [['Scenario Lab', '/scenario-lab', FlaskConical], ['Network', '/network', Network], ['Analytics', '/analytics', BarChart3]] },
  { label: 'Trust', items: [['Compliance', '/compliance', FileCheck2], ['Traceability', '/traceability', GitBranch], ['Trade Evidence', '/trade-evidence', CheckCircle2]] },
  { label: 'System', items: [['Agent Operations', '/agent-operations', Workflow], ['Activity & Audit', '/activity', Activity], ['Integrations', '/integrations', Unplug]] },
  { label: 'Administration', items: [['Users & Access', '/admin/users', UserRoundCog], ['Organization', '/admin/organization', Building2], ['Approval Policies', '/admin/approval-policies', SlidersHorizontal], ['Settings', '/settings', Settings]] },
] as const;

export function AppShell({ children, programme = 'Harbour View Hotel (Synthetic) · Ginger' }: { children: React.ReactNode; programme?: string }) {
  const [open, setOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const [query, setQuery] = useState('');
  const pathname = usePathname();
  const flatItems = useMemo(() => groups.flatMap(group => group.items), []);
  const results = flatItems.filter(([label]) => label.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPalette(value => !value); } if (event.key === 'Escape') setPalette(false); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return <div data-app-mode={process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? 'demo' : 'live'} className="min-h-screen xl:grid xl:grid-cols-[256px_minmax(0,1fr)]">
    {open && <button aria-label="Close navigation" className="fixed inset-0 z-40 bg-black/70 xl:hidden" onClick={() => setOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-white/[0.07] bg-[#07110e] transition-transform xl:sticky xl:top-0 xl:h-screen ${open ? 'translate-x-0' : '-translate-x-full xl:translate-x-0'}`}>
      <div className="flex h-[72px] items-center justify-between border-b border-white/[0.07] px-5"><Link href="/" className="flex items-center gap-3" onClick={() => setOpen(false)}><span className="grid h-9 w-9 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary"><Sprout className="h-5 w-5" /></span><span><strong className="block text-[17px] tracking-tight">KoroFarm</strong><span className="block text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Supply assurance OS</span></span></Link><button className="text-muted-foreground xl:hidden" onClick={() => setOpen(false)} aria-label="Close navigation"><X className="h-5 w-5" /></button></div>
      <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto px-3 py-4">{groups.map(group => <details key={group.label} open className="group mb-3"><summary className="cursor-pointer list-none px-3 pb-1.5 text-[9px] font-semibold uppercase tracking-[0.17em] text-muted-foreground/65">{group.label}</summary><ul className="space-y-0.5">{group.items.map(([label, href, Icon]) => { const active = href === '/' ? pathname === '/' : pathname.startsWith(href); return <li key={href}><Link href={href} onClick={() => setOpen(false)} className={`flex h-8.5 items-center gap-3 rounded-md px-3 text-[12px] transition-colors hover:bg-white/[0.05] hover:text-foreground ${active ? 'bg-primary/10 text-primary' : 'text-muted-foreground'}`}><Icon className="h-3.5 w-3.5" />{label}</Link></li>; })}</ul></details>)}</nav>
      <div className="border-t border-white/[0.07] p-4"><div className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-3"><div className="flex items-center justify-between text-xs"><span className="text-muted-foreground">Environment</span><span className="flex items-center gap-1.5 font-medium text-success"><span className="h-1.5 w-1.5 rounded-full bg-success" />{process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? 'DEMO' : 'LIVE'}</span></div><p className="mt-2 truncate text-[10px] text-muted-foreground">System operational</p></div></div>
    </aside>
    <div className="min-w-0"><header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-white/[0.07] bg-background/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8"><div className="flex min-w-0 items-center gap-3"><button className="text-muted-foreground xl:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button><button className="flex min-w-0 items-center gap-2 text-left"><Building2 className="hidden h-4 w-4 text-muted-foreground sm:block" /><span className="min-w-0"><span className="block truncate text-sm font-medium">{programme}</span><span className="block text-[10px] text-muted-foreground">Jamaica institutional procurement</span></span></button></div><div className="flex items-center gap-2 sm:gap-3"><button onClick={() => setPalette(true)} className="hidden h-9 w-60 items-center justify-between rounded-md border border-white/[0.08] bg-white/[0.025] px-3 text-xs text-muted-foreground hover:border-white/[0.14] lg:flex"><span className="flex items-center gap-2"><Search className="h-3.5 w-3.5" />Search or jump to</span><kbd className="rounded border border-white/[0.1] px-1.5 py-0.5 text-[9px]">Ctrl K</kbd></button><span className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-success" />Synced now</span><Link href="/activity" className="relative grid h-9 w-9 place-items-center rounded-md text-muted-foreground hover:bg-white/[0.05] hover:text-foreground" aria-label="View exceptions"><Bell className="h-4 w-4" /><span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-warning" /></Link><Link href="/profile" className="grid h-8 w-8 place-items-center rounded-full bg-primary/15 text-xs font-semibold text-primary" aria-label="Open account">KF</Link></div></header>{children}</div>
    {palette && <div className="fixed inset-0 z-[80] grid place-items-start bg-black/70 px-4 pt-[12vh] backdrop-blur-sm" onMouseDown={() => setPalette(false)}><div role="dialog" aria-modal="true" aria-label="Command palette" className="w-full max-w-xl overflow-hidden rounded-xl border border-white/[0.12] bg-popover shadow-2xl" onMouseDown={event => event.stopPropagation()}><div className="flex items-center gap-3 border-b border-white/[0.08] px-4"><Search className="h-4 w-4 text-muted-foreground" /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Search workspaces, requirements, farmers, or lots…" className="h-14 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" /><button onClick={() => setPalette(false)} aria-label="Close command palette"><X className="h-4 w-4 text-muted-foreground" /></button></div><div className="max-h-80 overflow-y-auto p-2"><p className="px-3 py-2 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Workspaces</p>{results.map(([label, href, Icon]) => <Link key={href} href={href} onClick={() => setPalette(false)} className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm hover:bg-white/[0.05]"><Icon className="h-4 w-4 text-muted-foreground" />{label}</Link>)}{!results.length && <p className="px-3 py-8 text-center text-sm text-muted-foreground">No supported workspace matches that search.</p>}</div><div className="flex items-center gap-2 border-t border-white/[0.08] px-4 py-3 text-[10px] text-muted-foreground"><Command className="h-3 w-3" />Entity search is limited to data available in the configured requirement.</div></div></div>}
  </div>;
}
