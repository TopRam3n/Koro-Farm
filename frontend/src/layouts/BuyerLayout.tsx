'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Bell, Building2, ChevronDown, ClipboardList, FileCheck2, LayoutDashboard, PackageCheck, Sprout, UserRound } from 'lucide-react';
import { PersonaGuard } from '@/components/auth/PersonaGuard';
import { BackendRoleGuard } from '@/components/auth/BackendRoleGuard';
import { useCommandCenter, useMe, useOrganization } from '@/hooks/api/useBackend';

const primary = [
    { href: '/b/dashboard', label: 'Overview', icon: LayoutDashboard },
    { href: '/b', label: 'Requirements', icon: ClipboardList, exact: true },
    { href: '/b/programmes', label: 'Programmes', icon: Building2 },
    { href: '/b/supply', label: 'Supply', icon: Sprout },
    { href: '/b/deliveries', label: 'Deliveries & Quality', icon: PackageCheck },
    { href: '/b/evidence', label: 'Evidence & Compliance', icon: FileCheck2 },
];

export function BuyerLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname(), me = useMe(), organization = useOrganization(), commandCenter = useCommandCenter(), name = me.data?.display_name || me.data?.email || 'Buyer user';
    const organizationName = typeof organization.data?.name === 'string' ? organization.data.name : 'Buyer organization';
    const attentionCount = commandCenter.data?.requirements.needs_attention ?? 0;
    return <PersonaGuard persona="BUYER"><div className="min-h-screen bg-slate-50/70 text-foreground">
        <header className="sticky top-0 z-40 border-b bg-white/95 backdrop-blur"><div className="mx-auto flex h-16 max-w-[1500px] items-center gap-5 px-4 sm:px-6"><Link href="/b/dashboard" className="flex items-center gap-2 font-semibold text-emerald-950"><span className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-700 text-white">K</span>KoroFarm</Link><div className="hidden border-l pl-5 text-xs text-muted-foreground md:block"><p className="max-w-56 truncate font-medium text-foreground">{organizationName}</p><p>Procurement workspace</p></div><div className="ml-auto flex items-center gap-3"><Link href="/b/dashboard#attention" className="relative rounded-lg p-2 text-muted-foreground transition-colors hover:bg-amber-50 hover:text-amber-800" aria-label={attentionCount ? `${attentionCount} requirements need attention` : 'No requirements need attention'}><Bell className="h-5 w-5" />{attentionCount > 0 && <span className="absolute -right-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-red-600 px-1 text-[9px] font-bold leading-none text-white">{attentionCount > 99 ? '99+' : attentionCount}</span>}</Link><div className="flex items-center gap-2 rounded-lg border px-2.5 py-1.5"><span className="grid h-7 w-7 place-items-center rounded-full bg-emerald-100 text-emerald-800"><UserRound className="h-4 w-4" /></span><span className="hidden sm:block"><span className="block max-w-36 truncate text-xs font-medium">{name}</span><span className="block text-[10px] capitalize text-muted-foreground">{me.data?.role?.replace(/_/g, ' ').toLowerCase() ?? 'Loading role…'}</span></span><ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /></div></div></div></header>
        <div className="flex w-full"><aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-64 shrink-0 border-r bg-white px-3 py-6 lg:block"><p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[.18em] text-muted-foreground">Procurement</p><nav className="space-y-1" aria-label="Buyer workspace">{primary.map(item => <NavItem key={item.href} {...item} pathname={pathname} badge={item.href === '/b' && attentionCount ? attentionCount : undefined} />)}</nav><div className="my-5 border-t" /><p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[.18em] text-muted-foreground">Governance</p><nav className="space-y-1"><NavItem href="/b/activity" label="Activity" icon={Activity} pathname={pathname} /><BackendRoleGuard capability="admin.users"><NavItem href="/b/admin" label="Administration" icon={Building2} pathname={pathname} /></BackendRoleGuard></nav></aside><main className="min-w-0 flex-1 p-4 pb-24 sm:p-6 sm:pb-24 lg:p-8"><div className="mx-auto max-w-6xl">{children}</div></main></div>
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Buyer mobile workspace">{primary.slice(0, 4).map(x => <MobileNavItem key={x.href} {...x} pathname={pathname} badge={x.href === '/b' && attentionCount ? attentionCount : undefined} />)}</nav>
    </div></PersonaGuard>;
}

function NavItem({ href, label, icon: Icon, pathname, exact, badge }: { href: string; label: string; icon: typeof Activity; pathname: string; exact?: boolean; badge?: number }) { const active = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`); return <Link href={href} className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? 'bg-emerald-50 font-medium text-emerald-800' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}><Icon className="h-4 w-4" /><span>{label}</span>{badge ? <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">{badge}</span> : null}</Link> }

function MobileNavItem({ href, label, icon: Icon, pathname, exact, badge }: { href: string; label: string; icon: typeof Activity; pathname: string; exact?: boolean; badge?: number }) { const active = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`); return <Link href={href} className={`relative flex min-h-16 flex-col items-center justify-center gap-1 text-[10px] font-medium ${active ? 'text-emerald-700' : 'text-muted-foreground'}`}><span className="relative"><Icon className="h-5 w-5" />{badge ? <span className="absolute -right-3 -top-2 rounded-full bg-red-600 px-1 text-[8px] text-white">{badge}</span> : null}</span>{label}</Link> }
