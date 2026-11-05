'use client';

import { useOutboundNotifications } from '@/hooks/useNotifications';
import { useCan } from '@/hooks/useIdentity';
import { LoadState, Pill, humanize } from '@/components/trade/TradeUi';

const TONE: Record<string, 'good' | 'warn' | 'bad' | 'info' | 'neutral'> = {
  SENT: 'good', DELIVERED: 'good', QUEUED: 'info', FAILED: 'bad', BLOCKED_NO_CONSENT: 'warn', NOT_SENT_PROVIDER_DISABLED: 'neutral',
};
const LABEL: Record<string, string> = {
  BLOCKED_NO_CONSENT: 'Not sent: no consent', NOT_SENT_PROVIDER_DISABLED: 'Not sent: no provider connected',
};

/** Messages the notification service recorded (R1 WP5, M3). A failed or blocked message is shown, never hidden. */
export function OutboundNotifications() {
  const can = useCan();
  const list = useOutboundNotifications(can('supply.view'));
  if (!can('supply.view')) return null;
  return <section aria-labelledby="outbound" className="operational-panel mt-6 overflow-hidden">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.07] px-5 py-4">
      <h2 id="outbound" className="text-sm font-semibold">Messages to suppliers and buyers</h2>
      {list.data && <span className="text-xs text-muted-foreground" data-notification-provider={list.data.provider}>
        {list.data.provider_sends_messages ? `Provider: ${list.data.provider}` : list.data.provider === 'synthetic' ? 'Synthetic provider: recorded, never sent' : 'No messaging provider connected: nothing is sent'}
      </span>}
    </div>
    <LoadState query={list}>
      {list.data && (list.data.notifications.length === 0
        ? <p className="p-5 text-sm text-muted-foreground">No messages yet. Supply requests, reminders, reply-date changes, release agreements and deliveries create them.</p>
        : <ul className="divide-y divide-white/[0.06]" aria-label="Outbound messages">{list.data.notifications.map(n => <li key={n.id} data-notification-status={n.status} className="px-5 py-4 text-sm">
          <div className="flex flex-wrap items-center gap-2"><Pill tone={TONE[n.status] ?? 'neutral'}>{LABEL[n.status] ?? humanize(n.status)}</Pill>
            <span className="font-medium">{n.recipient_name ?? 'Unknown recipient'}</span>
            <span className="text-xs text-muted-foreground">{humanize(n.template_key)} v{n.template_version}{n.channel ? ` · ${n.channel} ${n.address ?? ''}` : ''} · {new Date(n.created_at).toLocaleString('en-JM')}</span></div>
          <p className="mt-1 text-xs text-muted-foreground">{n.body}</p>
          {n.last_error && <p className="mt-1 text-xs text-destructive">Last error after {n.attempts} attempt(s): {n.last_error}</p>}
        </li>)}</ul>)}
    </LoadState>
  </section>;
}
