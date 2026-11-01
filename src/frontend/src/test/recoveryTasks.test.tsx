import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RecoveryTasks } from '@/components/trade/RecoveryTasks';
import type { Proposal, RecoveryTask } from '@/hooks/useRecovery';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));

afterEach(() => { vi.unstubAllGlobals(); });

const HASH = 'a'.repeat(64);
const cost = { known: true, replacement_kg: '110', total_landed_cost_jmd: '66000.00', baseline_cost_per_kg_jmd: '600.00', increase_jmd: '0.00', increase_pct: '0.0000', unknown_cost_lots: [] };

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: 'prop-1', version: 1, status: 'PENDING', tier: 'ORDINARY', content_hash: HASH, expires_at: '2026-11-01T12:00:00Z',
    created_at: '2026-10-31T12:00:00Z', decided_at: null, status_reason: null, approvals: [], executions: [],
    viewer: { can_approve: true, elevated: false, already_decided: false },
    content: {
      version: 1, created_at: '2026-10-31T12:00:00Z', expires_at: '2026-11-01T12:00:00Z',
      basis: { required_kg: '730', committed_cover_kg: '730', exposed_kg: '110', assured_kg: '620', gap_kg: '110', in_flight_kg: '0', net_need_kg: '110' },
      incidents: [{ kind: 'CAPACITY_SHORTFALL', quantity_kg: '110', note: 'Reported capacity cut' }],
      chosen_option_id: 'A', escalation_kg: '30', cost,
      actions: [
        { type: 'RELEASE_EXPOSED', farmer_name: 'Ena Gordon', supplier_label: 'S1', parish: 'St. Ann', quantity_kg: '110', production_lot_id: 'lot-1', allocation_id: 'al-1' },
        { type: 'ACTIVATE_STANDBY', farmer_name: 'Paul Reid', supplier_label: 'S2', parish: 'St. Ann', quantity_kg: '80', production_lot_id: 'lot-2', allocation_id: 'al-2', activation_conditions: 'only to replace lost supply', authorization_valid_until: '2026-12-20' },
        { type: 'SOLICIT_SUPPLY', farmer_name: 'Mia Brown', supplier_label: 'S3', parish: 'Manchester', quantity_kg: '30', production_lot_id: 'lot-3', respond_within_hours: 24, message: 'Could you supply 30 kg?' },
      ],
      options: [
        { id: 'A', title: 'Activate authorized standby, then ask new suppliers for the rest', actions: [], standby_activated_kg: '80', requested_kg: '30', escalation_kg: '0', cost },
        { id: 'D', title: 'Escalate the whole shortfall to a coordinator', actions: [], standby_activated_kg: '0', requested_kg: '0', escalation_kg: '110', cost },
      ],
      approval: { tier: 'ORDINARY', reasons: ['no landed-cost increase'], required: 'one approver with recovery.approve', policy: { version: 0 } },
      decision: { mode: 'model', model: 'Qwen/Qwen3-30B-A3B-Instruct-2507', provider: 'nebius', latency_ms: 2400, call_outcome: 'partially_withheld',
        estimated_cost: { usd: '0.000660', price_version: 'list-prices-2026-10-31', basis: 'standard list price; estimate, not an account charge' },
        rationale: 'Standby already authorized covers most of the need.', recommend_escalation: false,
        information_requests: [], violations: ['buyer draft discarded: commercial (guarantee)'], fallback_reason: null },
      drafts: { buyer: 'A recovery plan is awaiting approval.', status: 'Draft only. Not sent to anyone; external messages are not sent automatically.' },
    },
    ...overrides,
  };
}

function task(overrides: Partial<RecoveryTask> = {}): RecoveryTask {
  return { id: 'task-1', requirement_id: 'req-1', requirement_label: 'SCOTCH BONNET for Sauce Works', status: 'AWAITING_APPROVAL', escalated_kg: '30',
    terminal_reason: null, last_error: null, created_at: '2026-10-31T12:00:00Z', updated_at: '2026-10-31T12:00:00Z', closed_at: null,
    current_proposal: proposal(), ...overrides };
}

function renderTasks(props: Partial<React.ComponentProps<typeof RecoveryTasks>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><RecoveryTasks empty="No recovery in progress." {...props} /></QueryClientProvider>);
}

describe('recovery proposals', () => {
  it('shows exactly what will happen, what is left, the cost and that drafts are not sent', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([task()]), { status: 200 })));
    renderTasks({ showOrder: true });
    const card = await screen.findByRole('region', { name: 'Recovery proposal 1' });
    const actions = within(card).getByRole('list', { name: 'Proposed actions' });
    expect(actions).toHaveTextContent('Ena Gordon can no longer supply 110 kg');
    expect(actions).toHaveTextContent('Activate 80 kg of standby that Paul Reid (St. Ann) authorized until 2026-12-20');
    expect(actions).toHaveTextContent('Ask Mia Brown (Manchester) for 30 kg, reply within 24 hours. Not supply until they accept');
    expect(actions).toHaveTextContent('Could you supply 30 kg?');
    expect(card).toHaveTextContent('30 kg is not covered by this proposal and is left for a coordinator.');
    expect(card).toHaveTextContent('Recovery agent with nebius/Qwen/Qwen3-30B-A3B-Instruct-2507');
    expect(card).toHaveTextContent('2.4 s, about US$0.000660 at list price');
    expect(card).toHaveTextContent("Checks applied to the model's answer: buyer draft discarded: commercial (guarantee)");
    expect(card).toHaveTextContent('Draft update for the buyer (not sent)');
    expect(screen.getByRole('link', { name: 'SCOTCH BONNET for Sauce Works' })).toHaveAttribute('href', '/orders/req-1');
  });

  it('approves by sending the hash of the proposal on screen, and shows a refusal', async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        calls.push({ url, body: JSON.parse(String(init.body)) });
        return new Response(JSON.stringify({ detail: 'the proposal you reviewed is not the current version; reload and review it again' }), { status: 409 });
      }
      return new Response(JSON.stringify([task()]), { status: 200 });
    }));
    renderTasks();
    fireEvent.click(await screen.findByRole('button', { name: 'Approve proposal' }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toContain('/recovery-proposals/prop-1/approve');
    expect(calls[0].body).toEqual({ proposal_hash: HASH, note: null });
    expect(await screen.findByRole('alert')).toHaveTextContent('not the current version');
  });

  it('rejects only with a reason', async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { calls.push({ url, body: JSON.parse(String(init.body)) }); return new Response('{}', { status: 200 }); }
      return new Response(JSON.stringify([task()]), { status: 200 });
    }));
    renderTasks();
    fireEvent.click(await screen.findByRole('button', { name: 'Reject proposal' }));
    fireEvent.change(screen.getByLabelText(/Reason for rejecting/), { target: { value: 'Supplier is unreliable' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({ url: expect.stringContaining('/recovery-proposals/prop-1/reject'), body: { proposal_hash: HASH, reason: 'Supplier is unreliable' } });
  });

  it('never offers approval to a role that cannot approve, and explains elevated approval', async () => {
    const elevated = proposal({ tier: 'ELEVATED', viewer: { can_approve: false, elevated: false, already_decided: true },
      approvals: [{ reviewer_user_id: 'u1', reviewer_name: 'Coordinator', reviewer_role: 'SUPPLY_COORDINATOR', decision: 'APPROVED', elevated: false, note: null, decided_at: '2026-10-31T12:01:00Z' }] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([task({ current_proposal: elevated })]), { status: 200 })));
    renderTasks();
    const card = await screen.findByRole('region', { name: 'Recovery proposal 1' });
    expect(within(card).queryByRole('button', { name: 'Approve proposal' })).not.toBeInTheDocument();
    expect(card).toHaveTextContent('Needs procurement manager or admin approval');
    expect(card).toHaveTextContent('It also needs a procurement manager or organization administrator.');
    expect(card).toHaveTextContent('Approved by Coordinator (Supply coordinator).');
  });

  it('shows applied actions and the full timeline on the order page', async () => {
    const executed = proposal({ status: 'EXECUTED', viewer: { can_approve: false, elevated: false, already_decided: true },
      executions: [{ action_index: 0, action_type: 'RELEASE_EXPOSED', outcome: 'APPLIED', detail: {}, executed_at: '2026-10-31T12:05:00Z' },
        { action_index: 1, action_type: 'ACTIVATE_STANDBY', outcome: 'APPLIED', detail: {}, executed_at: '2026-10-31T12:05:00Z' },
        { action_index: 2, action_type: 'SOLICIT_SUPPLY', outcome: 'FAILED', detail: { error: 'lot unavailable' }, executed_at: '2026-10-31T12:05:00Z' }] });
    const done = task({ status: 'AWAITING_SUPPLIER', current_proposal: executed, steps: [
      { sequence: 1, kind: 'INCIDENT', actor: 'recovery-agent', actor_name: 'Recovery agent', summary: 'Recovery task opened', detail: {}, proposal_id: null, created_at: '2026-10-31T12:00:00Z' },
      { sequence: 2, kind: 'APPROVAL', actor: 'u1', actor_name: 'Coordinator', summary: 'Proposal v1 approved by supply coordinator', detail: {}, proposal_id: 'prop-1', created_at: '2026-10-31T12:04:00Z' },
    ] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([done]), { status: 200 })));
    renderTasks({ requirementId: 'req-1' });
    const timeline = await screen.findByRole('list', { name: 'Recovery timeline' });
    expect(timeline).toHaveTextContent('Proposal v1 approved by supply coordinator');
    expect(timeline).toHaveTextContent('Coordinator');
    expect(screen.getAllByText('Applied')).toHaveLength(2);
    expect(screen.getByText('Failed: lot unavailable')).toBeInTheDocument();
  });
});
