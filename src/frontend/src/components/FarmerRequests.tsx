'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BellRing, CircleAlert } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { LIVE_REFRESH_MS } from '@/hooks/useTrade';

export type FarmerRequest = {
  allocation_id: string; role: 'COMMITTED' | 'STANDBY'; quantity_kg: string; crop: string; grade: string;
  delivery_window_start: string; delivery_window_end: string; buyer_name: string; production_lot_id: string;
  solicited_at: string | null; response_due_at: string | null; reminder_sent_at: string | null;
};

const due = (value: string) => new Date(value).toLocaleString('en-JM', { dateStyle: 'medium', timeStyle: 'short' });

/** Requests awaiting this farmer's own answer, with the reply deadline and the half-way reminder. */
export function FarmerRequests() {
  const requests = useQuery({
    queryKey: ['farmer', 'requests'],
    queryFn: () => apiFetch<FarmerRequest[]>('/allocations/solicitations/mine'),
    refetchInterval: LIVE_REFRESH_MS,
  });
  if (requests.isLoading) return <p className="py-4 text-sm text-muted-foreground">Loading requests…</p>;
  if (requests.error) return <p role="alert" className="py-4 text-sm text-destructive">Your requests are unavailable.</p>;
  if (!requests.data?.length) return <p className="py-4 text-sm text-muted-foreground">No requests are waiting for your answer.</p>;
  return <ul className="divide-y divide-white/[0.07] border-y border-white/[0.07]" aria-label="Requests awaiting your answer">
    {requests.data.map(request => <RequestItem key={request.allocation_id} request={request} />)}
  </ul>;
}

function RequestItem({ request }: { request: FarmerRequest }) {
  const queryClient = useQueryClient();
  const [key] = useState(() => `farmer-response-${crypto.randomUUID()}`);
  const standby = request.role === 'STANDBY';
  const respond = useMutation({
    mutationFn: (body: Record<string, string>) => apiFetch(`/allocations/${request.allocation_id}/responses`, {
      method: 'POST', body: JSON.stringify({ attestation_method: 'farmer portal', ...body }), headers: { 'Idempotency-Key': key },
    }),
    onSuccess: async () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ['farmer', 'requests'] }), queryClient.invalidateQueries({ queryKey: ['farmer', 'lots'] }),
    ]),
  });

  function answer(form: HTMLFormElement, decision: 'ACCEPTED' | 'DECLINED') {
    const conditions = String(new FormData(form).get('activation_conditions') ?? '').trim();
    respond.mutate({ decision, ...(decision === 'ACCEPTED' && standby ? { activation_conditions: conditions } : {}) });
  }

  return <li className="grid gap-3 py-4" data-request={request.allocation_id}>
    <div>
      <h3 className="text-sm font-semibold">{request.buyer_name} asks for {Number(request.quantity_kg).toLocaleString('en-JM')} kg of {request.crop.replace(/_/g, ' ').toLowerCase()} · Grade {request.grade}{standby ? ' as standby' : ''}</h3>
      <p className="mt-1 text-xs text-muted-foreground">Delivery {request.delivery_window_start} to {request.delivery_window_end}.{standby ? ' Standby means you agree to be called on if another supplier falls short; it is not a firm order.' : ''}</p>
      {request.response_due_at && <p className="mt-1 text-xs">Please reply by <strong>{due(request.response_due_at)}</strong>. If you do not reply, the request lapses; it is never taken as a yes or a no.</p>}
      {request.reminder_sent_at && <p role="status" className="mt-2 inline-flex items-center gap-1.5 rounded border border-warning/50 px-2 py-1 text-xs text-warning"><BellRing className="h-3.5 w-3.5" />Reminder: half of your reply time has passed.</p>}
    </div>
    <form className="grid gap-2" onSubmit={event => { event.preventDefault(); answer(event.currentTarget, 'ACCEPTED'); }} aria-label={`Answer ${request.buyer_name}`}>
      {standby && <label className="grid gap-1 text-[10px] font-medium text-muted-foreground">When may you be called on?<textarea name="activation_conditions" required minLength={3} className="min-h-16 rounded-md border border-white/10 bg-background px-3 py-2 text-sm text-foreground" placeholder="e.g. only if another farmer drops out, with 2 days' notice" /></label>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={respond.isPending} className="min-h-10 rounded-md bg-primary px-3 text-xs font-semibold text-primary-foreground disabled:opacity-60">{standby ? 'I agree to standby' : 'I can supply this'}</button>
        <button type="button" disabled={respond.isPending} onClick={event => answer(event.currentTarget.form!, 'DECLINED')} className="min-h-10 rounded-md border border-white/10 px-3 text-xs font-semibold disabled:opacity-60">I cannot supply this</button>
      </div>
    </form>
    {respond.error && <p role="alert" className="flex gap-2 text-sm text-destructive"><CircleAlert className="h-4 w-4 shrink-0" />{respond.error.message}</p>}
  </li>;
}
