'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bell, ChevronDown, ClipboardList, Home, LandPlot, Leaf, Menu, PackageOpen, UserRound } from 'lucide-react';
import { PersonaGuard } from '@/components/auth/PersonaGuard';
import { useAuth } from '@/hooks/useAuth';

const nav = [
    { href: '/f', label: 'Overview', icon: Home, exact: true },
    { href: '/f/farms', label: 'My farms', icon: LandPlot },
    { href: '/f/lots', label: 'Production lots', icon: Leaf },
    { href: '/f/commitments', label: 'Commitments', icon: ClipboardList },
];

export function FarmerLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const { user } = useAuth();
    const name = String(user?.user_metadata?.display_name || user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'Farmer');
    const initials = name.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase();

    return <PersonaGuard persona="FARMER">
        <div className="min-h-screen bg-[#f4f8f5] text-foreground">
            <header className="sticky top-0 z-30 border-b border-emerald-950/10 bg-white/95 backdrop-blur">
                <div className="flex h-[72px] items-center px-4 lg:px-7">
                    <Link href="/f" className="flex w-56 items-center gap-3 font-semibold tracking-tight text-emerald-950">
                        <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-700 text-white"><Leaf className="h-5 w-5" /></span>
                        <span className="text-lg">KoroFarm</span>
                    </Link>
                    <button className="hidden rounded-md p-2 text-muted-foreground hover:bg-muted lg:block" aria-label="Toggle navigation"><Menu className="h-5 w-5" /></button>
                    <div className="ml-auto flex items-center gap-2 sm:gap-4">
                        <nav className="hidden items-center gap-1 border-r pr-4 md:flex">
                            <Link href="/f/commitments" className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-emerald-50 hover:text-emerald-800">Commitments</Link>
                            <Link href="/f/lots" className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-emerald-50 hover:text-emerald-800">Supply</Link>
                            <button className="rounded-lg p-2 text-muted-foreground hover:bg-emerald-50 hover:text-emerald-800" aria-label="Notifications"><Bell className="h-5 w-5" /></button>
                        </nav>
                        <Link href="/f/profile" className="flex items-center gap-3 rounded-xl p-1.5 transition-colors hover:bg-emerald-50">
                            <span className="grid h-9 w-9 place-items-center rounded-full bg-emerald-100 text-xs font-bold text-emerald-800">{initials}</span>
                            <span className="hidden text-left sm:block"><span className="block max-w-32 truncate text-sm font-medium">{name}</span><span className="block text-[11px] text-muted-foreground">Farmer account</span></span>
                            <ChevronDown className="hidden h-4 w-4 text-muted-foreground sm:block" />
                        </Link>
                    </div>
                </div>
            </header>

            <div className="flex">
                <aside className="fixed bottom-0 left-0 top-[72px] hidden w-64 overflow-y-auto border-r border-emerald-950/10 bg-white px-4 py-7 lg:block">
                    <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Farmer workspace</p>
                    <nav className="space-y-1">{nav.map(item => { const active = item.exact ? pathname === item.href : pathname.startsWith(item.href); const Icon = item.icon; return <Link key={item.href} href={item.href} className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? 'bg-emerald-50 font-medium text-emerald-800' : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'}`}><Icon className="h-4 w-4" />{item.label}</Link>; })}</nav>
                    <div className="my-6 border-t" />
                    <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Account</p>
                    <nav className="space-y-1"><Link href="/f/profile" className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${pathname === '/f/profile' ? 'bg-emerald-50 font-medium text-emerald-800' : 'text-muted-foreground hover:bg-muted/60'}`}><UserRound className="h-4 w-4" />Profile & readiness</Link><Link href="/f/lots/new" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted/60"><PackageOpen className="h-4 w-4" />Declare supply</Link></nav>
                </aside>

                <main className="min-w-0 flex-1 p-4 sm:p-6 lg:ml-64 lg:p-9"><div className="mx-auto max-w-6xl">{children}</div></main>
            </div>

            <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t bg-white px-2 py-2 lg:hidden">{nav.slice(0, 4).map(item => { const active = item.exact ? pathname === item.href : pathname.startsWith(item.href); const Icon = item.icon; return <Link key={item.href} href={item.href} className={`flex min-w-16 flex-col items-center gap-1 rounded-md p-1 text-[10px] ${active ? 'text-emerald-700' : 'text-muted-foreground'}`}><Icon className="h-5 w-5" />{item.label}</Link>; })}</nav>
        </div>
    </PersonaGuard>;
}
