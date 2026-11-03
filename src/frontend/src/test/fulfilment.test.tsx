import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FulfilmentSection } from '@/components/trade/FulfilmentSection';
import { BuyerDeliveries } from '@/components/trade/BuyerDeliveries';
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

function serve(routes: Record<string, unknown>) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
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
    expect(within(screen.getByRole('list', { name: 'Why it cannot be completed' })).getAllByRole('listitem')).toHaveLength(2);
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
