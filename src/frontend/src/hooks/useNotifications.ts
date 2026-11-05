'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { LIVE_REFRESH_MS } from '@/hooks/useTrade';

/** R1 WP5 (M3): consent to be contacted and the record of outbound messages. Addresses arrive masked. */
export interface ContactConsent {
  id: string; subject_type: 'FARMER' | 'BUYER'; subject_id: string; channel: 'SMS' | 'WHATSAPP' | 'EMAIL'; address: string;
  state: 'GRANTED' | 'WITHDRAWN'; purposes: string[]; wording_version: string; how_given: string; evidence_reference: string | null;
  supersedes_id: string | null; recorded_by_user_id: string; created_at: string;
}
export interface OutboundNotification {
  id: string; template_key: string; template_version: number; purpose: string; recipient_type: string; recipient_id: string;
  recipient_name: string | null; channel: string | null; address: string | null; requirement_id: string | null; body: string;
  status: 'QUEUED' | 'SENT' | 'DELIVERED' | 'FAILED' | 'BLOCKED_NO_CONSENT' | 'NOT_SENT_PROVIDER_DISABLED';
  provider: string | null; attempts: number; last_error: string | null; sent_at: string | null; created_at: string;
}
export interface NotificationList { provider: string; provider_sends_messages: boolean; notifications: OutboundNotification[] }

type Subject = 'farmers' | 'buyers';

export const useConsents = (subject: Subject, id: string | null) => useQuery({
  queryKey: ['contact-consents', subject, id], queryFn: () => apiFetch<ContactConsent[]>(`/${subject}/${id}/contact-consents`), enabled: Boolean(id),
});

export function useRecordConsent(subject: Subject, id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => apiFetch<ContactConsent>(`/${subject}/${id}/contact-consents`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['contact-consents', subject, id] }),
  });
}

export const useOutboundNotifications = (enabled = true) => useQuery({
  queryKey: ['notifications'], queryFn: () => apiFetch<NotificationList>('/notifications'), enabled, refetchInterval: LIVE_REFRESH_MS,
});
