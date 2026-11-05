import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FulfilmentSection } from '@/components/trade/FulfilmentSection';
import { BuyerDeliveries } from '@/components/trade/BuyerDeliveries';
import { BuyerPortal } from '@/components/trade/BuyerPortal';
import { FulfilmentOverview } from '@/components/trade/FulfilmentOverview';
import type { BuyerDelivery, FulfilmentRecord } from '@/hooks/useFulfilment';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

afterEach(() => { vi.unstubAllGlobals(); });

const figures = {
  required_kg: '730', committed_kg: '730', received_kg: '725', accepted_kg: '705', rejected_kg: '20', ungraded_receipts: 0,
  dispatched_kg: '705', delivered_kg: '705', buyer_confirmed_kg: '0', legacy_unquantified_confirmation_kg: '0',
  unconfirmed_deliveries: 1, deliveries_with_discrepancy: 0, open_disputes: 0, disputed_kg: '0', released_kg: '0',
};
const delivery = { id: 'del-1', shipment_id: 'sh-1', recorded_quantity_kg: '705', delivered_quantity_kg: '705', delivered_at: '2026-10-30T10:00:00Z',
  evidence_reference: 'pod', adjustments: [], confirmation: null, confirmation_history: 0 };

function record(overrides: Partial<FulfilmentRecord> = {}): FulfilmentRecord {
  return {
    requirement_id: 'req-1', lifecycle_status: 'RECONCILED', figures, variances: { required_minus_accepted_kg: '25', required_minus_confirmed_kg: '730' },
    completion: { can_complete: false, blockers: ['buyer-confirmed 0 kg of 730 kg required', "1 delivery(ies) without the buyer's confirmation"] },
    receivable_allocations: [],
    receipts: [{ id: 'sub-1', allocation_id: 'al-1', farmer_name: 'Ena Gordon', fulfilment_node_id: 'n-1', received_kg: '725', accepted_kg: '705', rejected_kg: '20',
      graded: true, assigned_grade: 'A', rejection_reason: 'soft fruit', received_at: '2026-10-29T10:00:00Z', corrections: 0, shipment_id: 'sh-1' }],
    shipments: [{ id: 'sh-1', reference: 'SHIP-1', status: 'DELIVERED', dispatched_at: '2026-10-29T12:00:00Z', cancellation_reason: null, delivery }],
    disputes: [], effective_reconciliation_version: 1, unconfirmed_deliveries: ['del-1'],
    reconciliations: [{ id: 'rec-1', version: 1, status: 'EFFECTIVE', figures, variances: {}, reason: null, material_change: false, legacy: false,
      created_by_user_id: 'u-1', reviewed_by_user_id: null, created_at: '2026-10-30T11:00:00Z' }],
    ...overrides,
  };
}

function renderWith(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

/** Permissions per role exactly as the API's ROLE_PERMISSIONS grants them (identity/domain/permissions.py). */
const COORDINATOR = ['requirement.view', 'requirement.create', 'requirement.update', 'supply.view', 'supply.manage', 'recovery.view',
  'recovery.propose', 'recovery.approve', 'receiving.view', 'compliance.view', 'audit.view', 'fulfilment_site.manage', 'trade.reconcile',
  'buyer_confirmation.relay', 'dispute.raise'];
const WAREHOUSE = ['requirement.view', 'supply.view', 'receiving.view', 'receiving.record', 'grading.record', 'shipment.create', 'shipment.dispatch',
  'delivery.confirm', 'dispute.raise'];
const AUDITOR = ['requirement.view', 'supply.view', 'recovery.view', 'receiving.view', 'trade_evidence.view', 'compliance.view', 'user.view',
  'audit.view', 'approval_policy.view', 'audit.flag'];
const MANAGER = ['requirement.view', 'requirement.create', 'requirement.update', 'supply.view', 'recovery.view', 'recovery.propose', 'recovery.approve',
  'recovery.approve_elevated', 'trade_evidence.view', 'compliance.view', 'audit.view', 'approval_policy.view', 'receiving.view', 'trade.reconcile',
  'trade.accept_variance', 'buyer_confirmation.relay', 'dispute.raise'];
const me = (permissions: string[]) => ({ id: 'u-1', email: 'x@example.test', name: 'X', active_organization_id: 'o-1', active_role: 'X',
  active_farmer_id: null, active_buyer_id: null, permissions });

function serve(routes: Record<string, unknown>, permissions: string[] = COORDINATOR) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith('/me')) return new Response(JSON.stringify(me(permissions)), { status: 200 });
    const match = Object.entries(routes).find(([path]) => url.includes(path));
    return new Response(JSON.stringify(match ? match[1] : []), { status: 200 });
  }));
  return calls;
}

describe('order fulfilment', () => {
  it('keeps received, accepted, delivered and confirmed apart and never shows an unconfirmed delivery as completed', async () => {
    serve({ '/fulfilment-record': record(), '/fulfilment-nodes': [] });
    renderWith(<FulfilmentSection orderId="req-1" />);
    const quantities = await screen.findByLabelText('Fulfilment quantities');
    const value = (name: string) => within(quantities).getByText((_, el) => el?.getAttribute('data-fulfilment-figure') === name).textContent;
    expect([value('Required'), value('Received'), value('Accepted'), value('Rejected'), value('Delivered'), value('Buyer-confirmed')])
      .toEqual(['730 kg', '725 kg', '705 kg', '20 kg', '705 kg', '0 kg']);
    expect(screen.getByText('Reconciled, not closed')).toBeInTheDocument();
    expect(screen.queryByText('Completed')).not.toBeInTheDocument();
    expect(screen.getByText(/Not confirmed by the buyer/)).toBeInTheDocument();
    expect(within(await screen.findByRole('list', { name: 'Why it cannot be completed' })).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Close as completed' })).not.toBeInTheDocument();
  });

  it('shows a variance permanently once an order is closed with one', async () => {
    serve({ '/fulfilment-record': record({ lifecycle_status: 'CLOSED_WITH_VARIANCE', reconciliations: [{ ...record().reconciliations[0], variances: { required_minus_accepted_kg: '25', required_minus_confirmed_kg: '25' } }] }) });
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByText('Closed with variance')).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('25 kg short of the order');
    expect(screen.queryByRole('form', { name: 'Close with an accepted variance' })).not.toBeInTheDocument();
  });

  it('labels a staff-relayed confirmation as relayed, never as the buyer’s own', async () => {
    const relayed = { ...delivery, confirmation: { id: 'c-1', confirmed_quantity_kg: '705', outcome: 'CONFIRMED' as const, channel: 'STAFF_RELAYED' as const,
      buyer_representative: 'Receiving clerk', communication_channel: 'phone call', attestation: 'call log 12', stated_at: '2026-10-30T12:00:00Z', note: null, created_at: '2026-10-30T12:05:00Z' } };
    serve({ '/fulfilment-record': record({ shipments: [{ ...record().shipments[0], delivery: relayed }] }) });
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByText(/Relayed by staff: Receiving clerk via phone call/)).toBeInTheDocument();
    expect(screen.queryByText(/Confirmed by the buyer in their account/)).not.toBeInTheDocument();
  });
});

describe('physical event times', () => {
  it('says how a dispatch time was recorded and lists impossible sequences for review without hiding them', async () => {
    const stated = { ...record().shipments[0], dispatch_time_basis: 'STATED' as const, dispatched_at: '2026-10-31T08:00:00Z', dispatch_recorded_at: '2026-11-01T09:00:00Z' };
    const flags = [{ key: 'delivered_before_dispatch:del-1', kind: 'DELIVERED_BEFORE_DISPATCH' as const, message: 'shipment SHIP-1 is stated to have arrived before it left',
      delivery_id: 'del-1', reviewed: false, review_note: null, reviewed_by_user_id: null }];
    serve({ '/fulfilment-record': record({ shipments: [stated], sequence_flags: flags }) });
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByText(/\(stated; recorded/)).toBeInTheDocument();
    const list = screen.getByRole('list', { name: 'Event times to review' });
    expect(list).toHaveTextContent('Needs review');
    expect(list).toHaveTextContent('stated to have arrived before it left');
    expect(await within(list).findByRole('form', { name: 'What did you find?' })).toBeInTheDocument();
  });
});

describe('buyer deliveries', () => {
  it('lets the buyer confirm part of a delivery and report the difference, never more than delivered', async () => {
    const mine: BuyerDelivery = { ...delivery, order: 'SCOTCH BONNET, 730 kg', requirement_id: 'req-1', shipment_reference: 'SHIP-1' };
    const calls = serve({ '/buyer/deliveries/del-1/confirmation': { outcome: 'DISCREPANCY' }, '/buyer/deliveries': [mine] });
    renderWith(<BuyerDeliveries />);
    expect(await screen.findByText('Waiting for your confirmation.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Report a difference' }));
    const form = screen.getByRole('form', { name: 'Report a difference' });
    const quantity = within(form).getByLabelText(/Quantity you received/) as HTMLInputElement;
    expect(quantity.max).toBe('705');
    fireEvent.change(quantity, { target: { value: '690' } });
    fireEvent.change(within(form).getByLabelText(/What is different/), { target: { value: 'one crate missing' } });
    fireEvent.submit(form);
    await waitFor(() => expect(calls.some(c => c.url.includes('/buyer/deliveries/del-1/confirmation'))).toBe(true));
    const sent = calls.find(c => c.url.includes('/confirmation'))!;
    expect(JSON.parse(String(sent.init?.body))).toEqual({ confirmed_quantity_kg: '690', discrepancy: true, note: 'one crate missing' });
    expect(new Headers(sent.init?.headers).get('Idempotency-Key')).toMatch(/^buyer-confirm-/);
  });
});

describe('role-aware order workspace (WP5 M1)', () => {
  const open = () => record({ lifecycle_status: 'IN_FULFILMENT', effective_reconciliation_version: null, reconciliations: [],
    receivable_allocations: [{ allocation_id: 'al-1', farmer_name: 'Ena Gordon', parish: 'St. Ann', obligation_kg: '730' }],
    receipts: [{ ...record().receipts[0], graded: false, accepted_kg: '0', rejected_kg: '0', shipment_id: null }],
    shipments: [{ ...record().shipments[0], status: 'DISPATCHED', delivery: null }] });

  it('offers a warehouse operator only physical recording', async () => {
    serve({ '/fulfilment-record': open(), '/fulfilment-nodes': [] }, WAREHOUSE);
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByText('Record a receipt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Record grading' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Record delivery' })).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Reconcile' })).not.toBeInTheDocument();
    expect(screen.queryByText('Flag for audit')).not.toBeInTheDocument();
  });

  it('shows an auditor every figure, no action and a way to flag', async () => {
    const calls = serve({ '/fulfilment-record': record(), '/fulfilment-nodes': [], '/audit-flags': { id: 'f-1' } }, AUDITOR);
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByText(/Your role does not change them/)).toBeInTheDocument();
    for (const name of ["Record buyer's confirmation", 'Raise a discrepancy', 'Reconcile', 'Record a corrected version', 'Close as completed'])
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Close the order' })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Flag for audit' }));
    fireEvent.change(screen.getByLabelText(/^Subject/), { target: { value: 'Grading evidence' } });
    fireEvent.change(screen.getByLabelText(/What should be looked at/), { target: { value: 'Check the 20 kg rejected' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record flag' }));
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/audit-flags'))).toBe(true));
    const body = JSON.parse(String(calls.find(c => c.url.endsWith('/audit-flags'))!.init!.body));
    expect(body).toEqual({ subject: 'Grading evidence', note: 'Check the 20 kg rejected', requirement_id: 'req-1' });
  });

  it('offers closing with a variance only to roles that may accept one', async () => {
    serve({ '/fulfilment-record': record(), '/fulfilment-nodes': [] }, COORDINATOR);
    const first = renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByText(/needs a procurement manager or organization administrator/)).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Close with an accepted variance' })).not.toBeInTheDocument();
    first.unmount();
    serve({ '/fulfilment-record': record(), '/fulfilment-nodes': [] }, MANAGER);
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByRole('form', { name: 'Close with an accepted variance' })).toBeInTheDocument();
  });

  it('offers nothing while permissions are unknown (fail closed)', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/me')
      ? new Response(JSON.stringify({ detail: 'down' }), { status: 503 })
      : new Response(JSON.stringify(url.includes('/fulfilment-record') ? open() : []), { status: 200 })));
    renderWith(<FulfilmentSection orderId="req-1" />);
    expect(await screen.findByLabelText('Fulfilment quantities')).toBeInTheDocument();
    expect(screen.queryByText('Record a receipt')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Record grading' })).not.toBeInTheDocument();
  });

  it('marks Fulfilment Center queues actionable only for roles that can act on them', async () => {
    const queue = (items: unknown[], action_permission: string) => ({ items, count: items.length, action_permission });
    const data = { generated_at: '2026-11-05T10:00:00Z', day_start: '2026-11-05T05:00:00Z', open_orders: 1, queues: {
      ungraded_receipts: queue([{ requirement_id: 'req-1', order: 'Ginger for Hotel', supplier: 'Ena Gordon', received_kg: '20', received_at: '2026-11-05T09:00:00Z' }], 'grading.record'),
      awaiting_buyer_confirmation: queue([{ requirement_id: 'req-1', order: 'Ginger for Hotel', reference: 'SHIP-9', delivered_kg: '40', delivered_at: '2026-11-05T09:30:00Z' }], 'buyer_confirmation.relay'),
    } };
    serve({ '/fulfilment-overview': data }, WAREHOUSE);
    const { container } = renderWith(<FulfilmentOverview />);
    expect(await screen.findByText(/Shipment SHIP-9/)).toBeInTheDocument();
    expect(container.querySelector('[data-queue="ungraded_receipts"]')?.getAttribute('data-actionable')).toBe('yes');
    expect(container.querySelector('[data-queue="awaiting_buyer_confirmation"]')?.getAttribute('data-actionable')).toBe('no');
    expect(screen.getAllByRole('link', { name: 'Ginger for Hotel' }).length).toBe(2);
  });
});

describe('buyer portal (WP5 M2)', () => {
  it('keeps the buyer’s own confirmations, staff relays and outstanding quantities apart', async () => {
    const quantities = { required_kg: '100', delivered_kg: '50', confirmed_by_you_kg: '30', relayed_by_staff_kg: '20', disputed_kg: '0',
      awaiting_your_confirmation_kg: '0', still_to_deliver_kg: '50' };
    const order = { requirement_id: 'req-1', crop: 'GINGER', grade: 'A', delivery_window_start: '2026-12-01', delivery_window_end: '2026-12-12',
      destination: 'Kingston', status: 'IN_FULFILMENT', status_label: 'Being fulfilled', quantities };
    const statement = (source: string, kgValue: string, extra = {}) => ({ id: `s-${source}`, confirmed_quantity_kg: kgValue, outcome: 'CONFIRMED', source,
      source_label: source === 'BUYER_ACCOUNT' ? 'Confirmed by the buyer in their account' : 'Relayed by staff from another channel', note: null,
      created_at: '2026-11-05T10:00:00Z', ...extra });
    const delivery = (ref: string, kgValue: string, s: unknown) => ({ id: `d-${ref}`, shipment_reference: ref, delivered_at: '2026-11-05T09:00:00Z',
      delivered_quantity_kg: kgValue, recorded_quantity_kg: kgValue, corrections: [], current_statement: s, statement_history: [s] });
    serve({ '/buyer/orders/req-1': { ...order, disputes: [], deliveries: [
      delivery('SHIP-a', '30', statement('BUYER_ACCOUNT', '30')),
      delivery('SHIP-b', '20', statement('STAFF_RELAYED', '20', { buyer_representative: 'Receiving clerk', communication_channel: 'phone call', stated_at: '2026-11-05T09:30:00Z' })),
    ] }, '/buyer/orders': [order] }, []);
    const { container } = renderWith(<BuyerPortal />);
    expect(await screen.findByText('Shipment SHIP-b')).toBeInTheDocument();
    const figure = (key: string) => container.querySelector(`[data-buyer-figure="${key}"]`)?.textContent;
    expect([figure('confirmed_by_you_kg'), figure('relayed_by_staff_kg'), figure('still_to_deliver_kg')]).toEqual(['30 kg', '20 kg', '50 kg']);
    expect(container.querySelector('[data-statement-source="STAFF_RELAYED"]')?.textContent).toContain('Relayed by staff from another channel: Receiving clerk via phone call');
    expect(screen.getByRole('button', { name: 'Download delivery record (CSV)' })).toBeInTheDocument();
  });
});
