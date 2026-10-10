'use client';

import Link from 'next/link';
import {
    AlertTriangle,
    ArrowRight,
    CalendarClock,
    CheckCircle2,
    ChevronRight,
    CircleDot,
    PackageCheck,
    Scale,
    ShieldAlert,
    Sprout,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useCommandCenter, useRequirements } from '@/hooks/api/useBackend';
import { formatKg, supplyHealthBg, type Requirement, type SupplyHealth } from '@/domain/types';
import { ErrorState, LoadingState } from '@/components/production/PageState';

const attention: SupplyHealth[] = ['ESCALATION_REQUIRED', 'AT_RISK', 'RECOVERING', 'UNPLANNED'];
const healthNames: Record<SupplyHealth, string> = {
    COVERED: 'Covered',
    AT_RISK: 'At risk',
    RECOVERING: 'Recovering',
    ESCALATION_REQUIRED: 'Escalation required',
    UNPLANNED: 'Unplanned',
};
const n = (x: string | number) => Number(x || 0);

export default function Overview() {
    const q = useCommandCenter();
    const reqs = useRequirements({ limit: 50 });
    if (q.isLoading) return <LoadingState label="Loading portfolio health…" />;
    if (!q.data || q.error) return <ErrorState message="KoroFarm could not load the portfolio summary." onRetry={() => void q.refetch()} />;

    const d = q.data;
    const requirements = reqs.data?.items ?? [];
    const exceptions = requirements
        .filter(x => attention.includes(x.supply_health))
        .sort((a, b) => attention.indexOf(a.supply_health) - attention.indexOf(b.supply_health));
    const upcoming = requirements
        .filter(x => !['CLOSED', 'CANCELLED'].includes(x.lifecycle_status))
        .sort((a, b) => a.delivery_window_start.localeCompare(b.delivery_window_start))
        .slice(0, 5);
    const maxParish = Math.max(1, ...d.committed_concentration_by_parish.map(x => n(x.quantity_kg)));
    const receivedPct = n(d.physical_flow_kg.committed) ? n(d.physical_flow_kg.received) / n(d.physical_flow_kg.committed) * 100 : 0;
    const acceptedPct = n(d.physical_flow_kg.received) ? n(d.physical_flow_kg.accepted) / n(d.physical_flow_kg.received) * 100 : 0;

    return <section className="space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
                <p className="text-xs font-semibold uppercase tracking-[.18em] text-emerald-700">Procurement overview</p>
                <h1 className="mt-2 text-3xl font-semibold tracking-tight">Are we covered?</h1>
                <p className="mt-2 text-sm text-muted-foreground">Supply assurance, delivery readiness and the work requiring your attention.</p>
            </div>
            <Button asChild><Link href="/b/requirements/new/crop">New requirement</Link></Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[.9fr_1.6fr]">
            <Card>
                <CardHeader className="pb-3"><CardTitle className="text-sm font-medium">Portfolio health</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-3 gap-2">
                    <MetricLink href="/b" label="Active" value={d.requirements.total} />
                    <MetricLink href="/b?supply_health=COVERED" label="Covered" value={d.requirements.by_supply_health.COVERED ?? 0} tone="good" />
                    <MetricLink href="/b?attention=true" label="Needs attention" value={d.requirements.needs_attention} tone={d.requirements.needs_attention ? 'bad' : 'good'} />
                </CardContent>
            </Card>
            <Card>
                <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                    <div><CardTitle className="text-sm font-medium">Physical flow</CardTitle><p className="mt-1 text-xs text-muted-foreground">Committed → received → accepted</p></div>
                    <Button variant="ghost" size="sm" asChild><Link href="/b/deliveries">View deliveries <ChevronRight className="ml-1 h-4 w-4" /></Link></Button>
                </CardHeader>
                <CardContent>
                    <div className="grid items-center gap-3 sm:grid-cols-[1fr_auto_1fr_auto_1fr]">
                        <FlowMetric icon={Sprout} label="Committed" value={d.physical_flow_kg.committed} />
                        <ArrowRight className="hidden h-4 w-4 text-muted-foreground sm:block" />
                        <FlowMetric icon={PackageCheck} label="Received" value={d.physical_flow_kg.received} detail={`${Math.round(receivedPct)}% of committed`} />
                        <ArrowRight className="hidden h-4 w-4 text-muted-foreground sm:block" />
                        <FlowMetric icon={CheckCircle2} label="Accepted" value={d.physical_flow_kg.accepted} detail={`${Math.round(acceptedPct)}% of received`} good />
                    </div>
                    {n(d.physical_flow_kg.rejected) > 0 && <Link href="/b/deliveries" className="mt-4 flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 hover:bg-red-100"><span className="flex items-center gap-2"><AlertTriangle className="h-4 w-4" /><strong>{formatKg(d.physical_flow_kg.rejected)}</strong> rejected product requires review</span><ChevronRight className="h-4 w-4" /></Link>}
                </CardContent>
            </Card>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.45fr_.75fr]">
            <Card id="attention" className="scroll-mt-24 border-slate-200 shadow-sm">
                <CardHeader className="flex-row items-start justify-between space-y-0">
                    <div><CardTitle className="flex items-center gap-2 text-lg"><ShieldAlert className="h-5 w-5 text-amber-600" />Attention queue</CardTitle><p className="mt-1 text-sm text-muted-foreground">Highest-priority supply exceptions across active requirements.</p></div>
                    {!!exceptions.length && <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">{exceptions.length} open</span>}
                </CardHeader>
                <CardContent>
                    {reqs.isLoading ? <LoadingState label="Checking exceptions…" /> : reqs.error ? <ErrorState message="Could not load requirement exceptions." onRetry={() => void reqs.refetch()} /> : exceptions.length ? <div className="divide-y rounded-xl border">{exceptions.slice(0, 7).map(x => <AttentionRow key={x.id} requirement={x} />)}</div> : <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-6 text-center"><CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600" /><p className="mt-3 font-semibold text-emerald-950">All active requirements are covered</p><p className="mt-1 text-sm text-emerald-800">There are no current supply exceptions requiring buyer attention.</p></div>}
                    {exceptions.length > 7 && <Button variant="ghost" className="mt-3 w-full" asChild><Link href="/b?attention=true">View all {exceptions.length} exceptions</Link></Button>}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle className="flex items-center gap-2 text-base"><CalendarClock className="h-5 w-5 text-slate-600" />Upcoming delivery windows</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                    {reqs.isLoading ? <p className="text-sm text-muted-foreground">Loading delivery windows…</p> : upcoming.length ? upcoming.map(x => <UpcomingRow key={x.id} requirement={x} />) : <p className="rounded-lg bg-muted p-4 text-sm text-muted-foreground">No upcoming active delivery windows.</p>}
                    <Button variant="outline" className="mt-2 w-full" asChild><Link href="/b">View requirements</Link></Button>
                </CardContent>
            </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
            <Card><CardHeader className="flex-row items-center justify-between space-y-0"><div><CardTitle className="flex items-center gap-2 text-base"><Scale className="h-5 w-5" />Supply concentration</CardTitle><p className="mt-1 text-xs text-muted-foreground">Committed quantity by parish</p></div><Link href="/b/supply" className="text-xs font-medium text-emerald-700 hover:underline">Explore supply</Link></CardHeader><CardContent className="space-y-4">{d.committed_concentration_by_parish.length ? d.committed_concentration_by_parish.slice(0, 6).map(x => <div key={x.parish}><div className="mb-1.5 flex justify-between text-sm"><span>{x.parish}</span><span className="font-mono text-xs">{formatKg(x.quantity_kg)}</span></div><Progress value={n(x.quantity_kg) / maxParish * 100} className="h-1.5" /></div>) : <p className="text-sm text-muted-foreground">No committed supply concentration recorded yet.</p>}</CardContent></Card>
            <Card><CardHeader className="flex-row items-center justify-between space-y-0"><div><CardTitle className="text-base">Recent significant activity</CardTitle><p className="mt-1 text-xs text-muted-foreground">Recorded portfolio events</p></div><Link href="/b/activity" className="text-xs font-medium text-emerald-700 hover:underline">View activity</Link></CardHeader><CardContent>{d.recent_activity.length ? <div className="space-y-1">{d.recent_activity.slice(0, 6).map(x => <div key={x.id} className="flex gap-3 border-b py-2.5 last:border-0"><CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /><div className="min-w-0"><p className="truncate text-sm font-medium capitalize">{x.event_type.replace(/[._]/g, ' ')}</p><p className="mt-0.5 text-xs text-muted-foreground">{new Date(x.occurred_at).toLocaleString('en-JM')} · {x.actor_type.replace(/_/g, ' ').toLowerCase()}</p></div></div>)}</div> : <p className="text-sm text-muted-foreground">No recent portfolio activity recorded.</p>}</CardContent></Card>
        </div>
    </section>;
}

function MetricLink({ href, label, value, tone }: { href: string; label: string; value: number; tone?: 'good' | 'bad' }) {
    return <Link href={href} className="group rounded-lg border bg-slate-50/70 p-3 transition-colors hover:bg-slate-100"><p className="text-[11px] text-muted-foreground">{label}</p><div className="mt-1 flex items-end justify-between"><p className={`font-mono text-2xl font-semibold ${tone === 'good' ? 'text-emerald-700' : tone === 'bad' ? 'text-red-700' : ''}`}>{value}</p><ChevronRight className="mb-1 h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" /></div></Link>;
}

function FlowMetric({ icon: Icon, label, value, detail, good }: { icon: typeof Sprout; label: string; value: string; detail?: string; good?: boolean }) {
    return <div className="rounded-lg bg-slate-50 p-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Icon className={`h-4 w-4 ${good ? 'text-emerald-600' : ''}`} />{label}</div><p className={`mt-2 font-mono text-lg font-semibold ${good ? 'text-emerald-700' : ''}`}>{formatKg(value)}</p>{detail && <p className="mt-1 text-[10px] text-muted-foreground">{detail}</p>}</div>;
}

function AttentionRow({ requirement: x }: { requirement: Requirement }) {
    const urgency = deliveryUrgency(x.delivery_window_start, x.delivery_window_end);
    return <Link href={`/b/requirements/${x.id}`} className="group grid gap-3 p-4 transition-colors hover:bg-slate-50 sm:grid-cols-[1fr_auto] sm:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold">{x.crop} · Grade {x.grade}</p><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${supplyHealthBg[x.supply_health]}`}>{healthNames[x.supply_health]}</span></div><p className="mt-1 text-xs text-muted-foreground">Req {x.id.slice(0, 8)} · {formatKg(x.required_quantity_kg)} · {formatDateRange(x.delivery_window_start, x.delivery_window_end)}</p><p className={`mt-2 flex items-center gap-1.5 text-xs font-medium ${urgency.urgent ? 'text-amber-700' : 'text-muted-foreground'}`}><CalendarClock className="h-3.5 w-3.5" />{urgency.label}</p></div><div className="flex items-center gap-2 text-sm font-medium text-emerald-700">Review requirement <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" /></div></Link>;
}

function UpcomingRow({ requirement: x }: { requirement: Requirement }) {
    const urgency = deliveryUrgency(x.delivery_window_start, x.delivery_window_end);
    return <Link href={`/b/requirements/${x.id}`} className="block rounded-lg border p-3 transition-colors hover:bg-muted/50"><div className="flex items-start justify-between gap-2"><div><p className="text-sm font-medium">{x.crop} · Grade {x.grade}</p><p className="mt-1 text-xs text-muted-foreground">{formatKg(x.required_quantity_kg)}</p></div><span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${supplyHealthBg[x.supply_health]}`}>{healthNames[x.supply_health]}</span></div><p className={`mt-2 text-xs ${urgency.urgent ? 'font-medium text-amber-700' : 'text-muted-foreground'}`}>{urgency.label}</p></Link>;
}

function formatDateRange(start: string, end: string) {
    const fmt = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('en-JM', { month: 'short', day: 'numeric' });
    return `${fmt(start)}–${fmt(end)}`;
}

function deliveryUrgency(start: string, end: string) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const startDate = new Date(`${start}T00:00:00`), endDate = new Date(`${end}T23:59:59`);
    const days = Math.ceil((startDate.getTime() - today.getTime()) / 86_400_000);
    if (endDate < today) return { label: `Delivery window ended ${formatDateRange(start, end)}`, urgent: true };
    if (startDate <= today) return { label: `Delivery window open · ends ${formatDateRange(end, end).split('–')[0]}`, urgent: true };
    if (days === 1) return { label: 'Delivery window starts tomorrow', urgent: true };
    if (days <= 7) return { label: `Delivery window starts in ${days} days`, urgent: true };
    return { label: `Starts ${formatDateRange(start, end)}`, urgent: false };
}
