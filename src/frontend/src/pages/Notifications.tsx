'use client';

import { Activity, Check, Clock3 } from 'lucide-react';
import { useEvents } from '@/hooks/useAssurance';
import { SubpageShell } from '@/components/SubpageShell';

const requirementId = process.env.NEXT_PUBLIC_REQUIREMENT_ID ?? (process.env.NEXT_PUBLIC_APP_MODE === 'demo' ? '00000000-0000-0000-0000-000000000500' : '');

export default function Notifications() {
  const events = useEvents(requirementId);
  return <SubpageShell eyebrow="Activity" title="Operational notifications" description="Material programme events from the authoritative audit stream.">
    <section className="operational-panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4"><h2 className="text-sm font-semibold">Recent activity</h2><span className="text-xs text-muted-foreground">{events.data?.length ?? 0} events</span></div>
      {events.isLoading ? <div className="space-y-3 p-5" aria-label="Loading activity">{[1, 2, 3].map(item => <div key={item} className="h-16 animate-pulse rounded-md bg-white/[0.04]" />)}</div> : events.error ? <div role="alert" className="p-8 text-center"><Activity className="mx-auto h-5 w-5 text-warning" /><p className="mt-3 text-sm font-medium">Activity is temporarily unavailable.</p><p className="mt-1 text-xs text-muted-foreground">No substitute events have been generated.</p></div> : events.data?.length ? <ol className="divide-y divide-white/[0.06]">{[...events.data].reverse().map(event => <li key={event.id} className="grid gap-3 px-5 py-5 sm:grid-cols-[32px_minmax(0,1fr)_120px]"><span className="grid h-8 w-8 place-items-center rounded-md border border-success/25 bg-success/10 text-success"><Check className="h-4 w-4" /></span><div><p className="text-sm font-medium">{event.event_type.replace(/\./g, ' ')}</p><p className="mt-1 text-xs text-muted-foreground">Initiated by {event.actor_type} · verified audit event</p></div><time className="flex items-center gap-1.5 text-xs text-muted-foreground sm:justify-end"><Clock3 className="h-3.5 w-3.5" />{new Date(event.occurred_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</time></li>)}</ol> : <div className="p-8 text-center"><Activity className="mx-auto h-5 w-5 text-muted-foreground" /><p className="mt-3 text-sm font-medium">No material programme activity yet.</p><p className="mt-1 text-xs text-muted-foreground">Planning and recovery events will appear here.</p></div>}
    </section>
  </SubpageShell>;
}
