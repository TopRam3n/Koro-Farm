'use client';

import { Activity, AlertTriangle, BarChart3, Bell, Building2, CheckCircle2, ClipboardCheck, Command, FileCheck2, FlaskConical, GitBranch, LayoutDashboard, ListTodo, Menu, Network, PackageCheck, Search, Settings, ShieldCheck, ShoppingBasket, SlidersHorizontal, Tractor, Unplug, UserRoundCog, Workflow, X, ClipboardList, Store, Sprout } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useIdentity } from '@/hooks/useIdentity';
import { useExceptions } from '@/hooks/useTrade';
import { reasonText, useSystemStatus } from '@/hooks/useSystemStatus';

type NavItem = readonly [string, string, typeof LayoutDashboard];
type NavGroup = { label: string; items: readonly NavItem[] };

const groups: readonly NavGroup[] = [
  { label: 'My Work', items: [['My Work', '/', ListTodo], ['Needs attention', '/exceptions', AlertTriangle], ['Command Center', '/command-center', LayoutDashboard]] },
  { label: 'Operations', items: [['Orders', '/orders', ClipboardList], ['Buyers', '/buyers', Store], ['Suppliers & lots', '/suppliers', Sprout], ['Programmes', '/programmes', Building2], ['Demand', '/demand', ClipboardCheck], ['Supply Network', '/supply', Tractor], ['Assurance', '/assurance', ShieldCheck], ['Fulfilment', '/fulfilment', PackageCheck], ['Fulfilment sites', '/fulfilment/sites', Building2]] },
  { label: 'Intelligence', items: [['Scenario Lab', '/scenario-lab', FlaskConical], ['Network', '/network', Network], ['Analytics', '/analytics', BarChart3]] },
  { label: 'Trust', items: [['Compliance', '/compliance', FileCheck2], ['Traceability', '/traceability', GitBranch], ['Trade Evidence', '/trade-evidence', CheckCircle2]] },
  { label: 'System', items: [['Agent Operations', '/agent-operations', Workflow], ['Activity & Audit', '/activity', Activity], ['Integrations', '/integrations', Unplug]] },
  { label: 'Administration', items: [['Users & Access', '/admin/users', UserRoundCog], ['Organization', '/admin/organization', Building2], ['Approval Policies', '/admin/approval-policies', SlidersHorizontal], ['Settings', '/settings', Settings]] },
] as const;

const farmerGroups: readonly NavGroup[] = [
  { label: 'My farm', items: [['My harvest', '/farmer', Tractor]] },
  { label: 'Account', items: [['Notifications', '/notifications', Bell], ['Profile', '/profile', UserRoundCog]] },
];

const buyerGroups: readonly NavGroup[] = [
  { label: 'My orders', items: [['Orders and deliveries', '/buyer', PackageCheck]] },
  { label: 'Shop', items: [['Available produce', '/marketplace', ShoppingBasket], ['Marketplace orders', '/marketplace#orders', ClipboardCheck], ['Food alerts', '/marketplace#alerts', Bell], ['My deliveries', '/deliveries', PackageCheck]] },
  { label: 'Account', items: [['Profile', '/profile', UserRoundCog]] },
];

const adminWorkspaceGroup: NavGroup = { label: 'Partner workspaces', items: [['Farmer portal', '/farmer', Tractor], ['Customer marketplace', '/marketplace', ShoppingBasket]] };

export function AppShell({ children, programme = 'Harbour View Hotel (Synthetic) · Ginger', className = '', compactNavGroups = false }: { children: React.ReactNode; programme?: string; className?: string; compactNavGroups?: boolean }) {
  const [open, setOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const [query, setQuery] = useState('');
  const paletteRef = useRef<HTMLDivElement>(null);
  const paletteInputRef = useRef<HTMLInputElement>(null);
  const paletteTriggerRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const pathname = usePathname();
  const identity = useIdentity();
  const visibleGroups = useMemo(() => identity.data?.active_role === 'FARMER' ? farmerGroups : identity.data?.active_role === 'BUYER' ? buyerGroups : identity.data?.active_role === 'PLATFORM_ADMIN' ? [...groups, adminWorkspaceGroup] : groups, [identity.data?.active_role]);
  const flatItems = useMemo(() => visibleGroups.flatMap(group => group.items), [visibleGroups]);
  const role = identity.data?.active_role;
  const staff = Boolean(role) && role !== 'FARMER' && role !== 'BUYER';
  const openExceptions = useExceptions({ enabled: staff }).data?.length ?? 0;
  const system = useSystemStatus(staff);
  const degraded = system.data?.status === 'DEGRADED';
  // Never claim monitoring is working without evidence: unknown is shown as unknown.
  const monitoring = !staff ? null : system.data ? (degraded ? 'Exception monitoring degraded' : 'Exception monitoring running') : system.error ? 'Monitoring status unavailable' : 'Checking monitoring…';
  const monitoringTone = degraded || system.error ? 'text-warning' : system.data ? 'text-success' : 'text-muted-foreground';
  const monitoringDot = degraded || system.error ? 'bg-warning' : system.data ? 'bg-success' : 'bg-muted-foreground';
  const results = flatItems.filter(([label]) => label.toLowerCase().includes(query.toLowerCase()));

  const closePalette = () => {
    setPalette(false);
    requestAnimationFrame(() => (previousFocusRef.current ?? paletteTriggerRef.current)?.focus());
  };

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (palette) closePalette();
        else { previousFocusRef.current = document.activeElement as HTMLElement; setPalette(true); }
      }
      if (event.key === 'Escape' && palette) closePalette();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [palette]);

  useEffect(() => {
    if (!palette) return;
    paletteInputRef.current?.focus();
    const dialog = paletteRef.current;
    if (!dialog) return;
    const handleTab = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button, input, a[href]')).filter(element => !element.hasAttribute('disabled'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    dialog.addEventListener('keydown', handleTab);
    return () => dialog.removeEventListener('keydown', handleTab);
  }, [palette]);

  return <div data-app-mode="live" className={`min-h-screen xl:grid xl:grid-cols-[256px_minmax(0,1fr)] ${className}`}>
    {open && <button aria-label="Close navigation" className="fixed inset-0 z-40 bg-black/70 xl:hidden" onClick={() => setOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-white/[0.07] bg-sidebar-background transition-transform xl:sticky xl:top-0 xl:h-screen ${open ? 'translate-x-0' : '-translate-x-full xl:translate-x-0'}`}>
      <div className="flex h-[72px] items-center justify-between border-b border-white/[0.07] px-5"><Link href="/" className="flex items-center gap-3" onClick={() => setOpen(false)} aria-label="KoroFarm home"><Image src="/brand/korofarm-mark.png" alt="" width={36} height={36} className="h-9 w-9 shrink-0 object-contain" priority /><Image src="/brand/korofarm-wordmark.png" alt="KoroFarm — Supply Assurance OS" width={132} height={44} className="h-auto w-[120px] object-contain xl:w-[132px]" priority /></Link><button type="button" className="grid min-h-11 min-w-11 place-items-center text-muted-foreground xl:hidden" onClick={() => setOpen(false)} aria-label="Close navigation"><X className="h-5 w-5" /></button></div>
      <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto px-3 py-4">{visibleGroups.map(group => <details key={group.label} open={!compactNavGroups || group.label === 'My Work' || group.label === 'Operations'} className="group mb-3"><summary className="cursor-pointer list-none px-3 pb-1.5 text-[9px] font-semibold uppercase tracking-[0.17em] text-muted-foreground/65">{group.label}</summary><ul className="space-y-0.5">{group.items.map(([label, href, Icon]) => { const active = href === '/' ? pathname === '/' : pathname.startsWith(href); return <li key={href}><Link href={href} onClick={() => setOpen(false)} className={`flex min-h-10 items-center gap-3 rounded-md px-3 text-[12px] transition-colors hover:bg-white/[0.05] hover:text-foreground ${active ? 'bg-primary/10 text-primary' : 'text-muted-foreground'}`}><Icon className="h-3.5 w-3.5" />{label}</Link></li>; })}</ul></details>)}</nav>
      <div className="border-t border-white/[0.07] p-4"><div className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-3"><div className="flex items-center justify-between text-xs"><span className="text-muted-foreground">Environment</span><span className="font-medium text-muted-foreground">{process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? 'Demo disabled' : 'Live data'}</span></div>{monitoring && <p className={`mt-2 flex items-center gap-1.5 text-[10px] ${monitoringTone}`} data-monitoring={system.data?.status ?? 'UNKNOWN'}><span className={`h-1.5 w-1.5 shrink-0 rounded-full ${monitoringDot}`} />{monitoring}</p>}</div></div>
    </aside>
    <div className="min-w-0"><header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-white/[0.07] bg-background/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8"><div className="flex min-w-0 items-center gap-3"><button type="button" className="grid min-h-11 min-w-11 place-items-center text-muted-foreground xl:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button><div className="flex min-w-0 items-center gap-2 text-left"><Building2 className="hidden h-4 w-4 text-muted-foreground sm:block" /><span className="min-w-0"><span className="block truncate text-sm font-medium">{programme}</span><span className="block text-[10px] text-muted-foreground">Jamaica institutional procurement</span></span></div></div><div className="flex items-center gap-2 sm:gap-3"><button type="button" ref={paletteTriggerRef} onClick={() => { previousFocusRef.current = document.activeElement as HTMLElement; setPalette(true); }} className="hidden h-11 w-60 items-center justify-between rounded-md border border-white/[0.08] bg-white/[0.025] px-3 text-xs text-muted-foreground hover:border-white/[0.14] lg:flex"><span className="flex items-center gap-2"><Search className="h-3.5 w-3.5" />Search or jump to</span><kbd className="rounded border border-white/[0.1] px-1.5 py-0.5 text-[9px]">Ctrl K</kbd></button>{monitoring && <Link href="/exceptions" className={`hidden items-center gap-2 text-xs sm:flex ${monitoringTone}`} title={system.data?.worker.last_beat_at ? `Last worker heartbeat ${new Date(system.data.worker.last_beat_at).toLocaleString('en-JM')}` : 'No worker heartbeat recorded'}><span className={`h-1.5 w-1.5 rounded-full ${monitoringDot}`} />{monitoring}</Link>}{staff && <Link href="/exceptions" className="relative grid min-h-11 min-w-11 place-items-center rounded-md text-muted-foreground hover:bg-white/[0.05] hover:text-foreground" aria-label={openExceptions ? `View ${openExceptions} open supply exceptions` : 'No open supply exceptions'}><Bell className="h-4 w-4" />{openExceptions > 0 && <span className="absolute right-3 top-3 h-1.5 w-1.5 rounded-full bg-warning" />}</Link>}<Link href="/profile" className="grid min-h-11 min-w-11 place-items-center rounded-full bg-primary/15 text-xs font-semibold text-primary" aria-label="Open account">KF</Link></div></header>{degraded && system.data && <div role="alert" className="border-b border-warning/40 bg-warning/10 px-4 py-3 text-sm sm:px-6 lg:px-8"><p className="font-medium text-warning">Exception monitoring is degraded. Supply exceptions and reply deadlines may not be up to date.</p><ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">{system.data.reasons.map(reason => <li key={reason}>{reasonText[reason]}</li>)}</ul></div>}{children}</div>
    {palette && <div className="fixed inset-0 z-[80] grid place-items-start bg-black/70 px-4 pt-[12vh] backdrop-blur-sm" onMouseDown={closePalette}><div ref={paletteRef} role="dialog" aria-modal="true" aria-label="Command palette" className="w-full max-w-xl overflow-hidden rounded-xl border border-white/[0.12] bg-popover shadow-2xl" onMouseDown={event => event.stopPropagation()}><div className="flex items-center gap-3 border-b border-white/[0.08] px-4"><Search className="h-4 w-4 text-muted-foreground" /><input ref={paletteInputRef} value={query} onChange={event => setQuery(event.target.value)} placeholder="Search workspaces, requirements, farmers, or lots…" className="h-14 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" /><button type="button" onClick={closePalette} className="grid min-h-11 min-w-11 place-items-center" aria-label="Close command palette"><X className="h-4 w-4 text-muted-foreground" /></button></div><div className="max-h-80 overflow-y-auto p-2"><p className="px-3 py-2 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Workspaces</p>{results.map(([label, href, Icon]) => <Link key={href} href={href} onClick={closePalette} className="flex min-h-11 items-center gap-3 rounded-md px-3 py-2.5 text-sm hover:bg-white/[0.05]"><Icon className="h-4 w-4 text-muted-foreground" />{label}</Link>)}{!results.length && <p className="px-3 py-8 text-center text-sm text-muted-foreground">No supported workspace matches that search.</p>}</div><div className="flex items-center gap-2 border-t border-white/[0.08] px-4 py-3 text-[10px] text-muted-foreground"><Command className="h-3 w-3" />Entity search is limited to data available in the configured requirement.</div></div></div>}
  </div>;
}
