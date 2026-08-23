 'use client';

import Link from 'next/link';
import { ArrowLeft, CheckCircle2, CircleAlert, FileCheck2, Sprout } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const notifications = [
	{ icon: CheckCircle2, tone: 'text-success', title: 'Buyer SLA preserved', detail: 'The 80 kg disruption was recovered from standby capacity. Final committed supply is 500 kg.', time: 'Today, 09:42', badge: 'Recovered' },
	{ icon: CircleAlert, tone: 'text-warning', title: 'Disruption recorded', detail: 'Nadine Ellis dropped 80 kg from the original committed plan. A recovery run was opened.', time: 'Today, 09:36', badge: 'Audit event' },
	{ icon: FileCheck2, tone: 'text-primary', title: 'Fulfilment checkpoint pending', detail: 'Receive and grade the farmer sublots at St. James Collection Hub before reconciliation.', time: 'Today, 09:30', badge: 'Action pending' },
];

export default function Notifications() {
	return <div className="min-h-screen bg-background"><header className="border-b border-border/70 px-5 py-4"><div className="mx-auto flex max-w-4xl items-center justify-between"><Button asChild variant="ghost" size="sm"><Link href="/"><ArrowLeft className="mr-2 h-4 w-4" />Dashboard</Link></Button><div className="flex items-center gap-2 text-sm font-semibold"><Sprout className="h-4 w-4 text-primary" />KoroFarm</div></div></header><main className="mx-auto max-w-4xl px-5 py-10"><div className="mb-8 flex items-end justify-between gap-4"><div><p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Activity feed</p><h1 className="mt-2 text-4xl font-semibold tracking-tight">Notifications</h1><p className="mt-2 text-muted-foreground">Material programme events and next checkpoints.</p></div><Badge variant="outline">3 updates</Badge></div><Card><CardHeader><CardTitle className="text-lg">Recent activity</CardTitle></CardHeader><CardContent className="divide-y divide-border/60 p-0">{notifications.map(({ icon: Icon, tone, title, detail, time, badge }) => <div className="flex gap-4 px-6 py-5" key={title}><div className={`mt-0.5 rounded-md bg-muted p-2 ${tone}`}><Icon className="h-5 w-5" /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-start justify-between gap-2"><h2 className="font-medium">{title}</h2><span className="text-xs text-muted-foreground">{time}</span></div><p className="mt-1 text-sm leading-6 text-muted-foreground">{detail}</p><Badge variant="outline" className="mt-3 text-xs">{badge}</Badge></div></div>)}</CardContent></Card></main></div>;
}
