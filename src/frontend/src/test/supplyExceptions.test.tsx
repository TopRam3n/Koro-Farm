import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExceptionList } from '@/components/trade/ExceptionList';
import { localToIso } from '@/components/trade/OrderDetail';
import { FarmerRequests } from '@/components/FarmerRequests';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));

afterEach(() => { vi.unstubAllGlobals(); });

const shortfall = {
  id: 'exc-1', requirement_id: 'req-1', requirement_label: 'GINGER for Harbour View', kind: 'CAPACITY_SHORTFALL', status: 'OPEN',
  shortfall_kg: '120.000', summary: 'Confirmed commitments exceed reported capacity by 120 kg.', details: {},
  opened_at: '2026-10-31T12:00:00Z', updated_at: '2026-10-31T12:00:00Z', acknowledged_at: null, resolved_at: null, resolved_by: null, resolution: null,
};

function withClient(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function renderList(props: Partial<React.ComponentProps<typeof ExceptionList>> = {}) {
  return withClient(<ExceptionList empty="No open supply exceptions." {...props} />);
}

describe('supply exceptions', () => {
  it('lists open exceptions for one order with the shortfall', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify([shortfall]), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    renderList({ requirementId: 'req-1' });
    expect(await screen.findByText('Capacity shortfall')).toBeInTheDocument();
    expect(screen.getByText('120 kg')).toBeInTheDocument();
    expect(String((fetchMock.mock.calls[0] as unknown as [string])[0])).toContain('/exceptions?status=OPEN&requirement_id=req-1');
  });

  it('says plainly when nothing needs attention', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200 })));
    renderList();
    expect(await screen.findByText('No open supply exceptions.')).toBeInTheDocument();
  });

  it('acknowledges through the API and shows the refusal to resolve while exposure remains', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`);
      if (url.endsWith('/resolve')) return new Response(JSON.stringify({ detail: 'exposure remains; cover it or record new capacity' }), { status: 409 });
      return new Response(JSON.stringify(url.endsWith('/acknowledge') ? { ...shortfall, acknowledged_at: '2026-10-31T12:05:00Z' } : [shortfall]), { status: 200 });
    }));
    renderList({ showOrder: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Acknowledge' }));
    await waitFor(() => expect(calls.some(c => c.startsWith('POST') && c.endsWith('/exceptions/exc-1/acknowledge'))).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: 'Resolve…' }));
    fireEvent.change(screen.getByLabelText(/What was done/), { target: { value: 'Called the buyer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('exposure remains');
    expect(screen.getByRole('link', { name: 'GINGER for Harbour View' })).toHaveAttribute('href', '/orders/req-1');
  });
});

describe('reply deadlines', () => {
  it('sends a local wall-clock deadline as an absolute instant', () => {
    const iso = localToIso('2026-11-02T09:30');
    expect(iso).toMatch(/Z$/);
    expect(new Date(iso).getTime()).toBe(new Date('2026-11-02T09:30').getTime());
  });
});

describe('farmer requests', () => {
  const request = {
    allocation_id: 'alloc-1', role: 'COMMITTED', quantity_kg: '300.000', crop: 'GINGER', grade: 'A', delivery_window_start: '2026-12-01',
    delivery_window_end: '2026-12-12', buyer_name: 'Ocho Rios Spice Traders', production_lot_id: 'lot-1', solicited_at: '2026-10-31T00:00:00Z',
    response_due_at: '2026-11-01T00:00:00Z', reminder_sent_at: '2026-10-31T12:00:00Z',
  };

  it('shows the reply deadline and the half-way reminder, and answers through the farmer channel', async () => {
    const posts: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { posts.push({ url, body: JSON.parse(String(init.body)) }); return new Response('{}', { status: 200 }); }
      return new Response(JSON.stringify([request]), { status: 200 });
    }));
    withClient(<FarmerRequests />);
    expect(await screen.findByText(/Please reply by/)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Reminder: half of your reply time has passed.');
    fireEvent.click(screen.getByRole('button', { name: 'I cannot supply this' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toContain('/allocations/alloc-1/responses');
    expect(posts[0].body).toEqual({ attestation_method: 'farmer portal', decision: 'DECLINED' });
  });

  it('asks for activation conditions before agreeing to standby', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([{ ...request, role: 'STANDBY', reminder_sent_at: null }]), { status: 200 })));
    withClient(<FarmerRequests />);
    expect(await screen.findByLabelText('When may you be called on?')).toBeRequired();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
