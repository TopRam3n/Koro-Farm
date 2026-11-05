import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SuppliersWorkspace } from '@/components/trade/SuppliersWorkspace';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
afterEach(() => { vi.unstubAllGlobals(); });

describe('suppliers page with the consent panel (WP5 M3)', () => {
  it('renders for a coordinator', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.endsWith('/me') ? { id: 'u', email: 'e', name: 'n', active_organization_id: 'o', active_role: 'SUPPLY_COORDINATOR',
        active_farmer_id: null, active_buyer_id: null, permissions: ['supply.view', 'supply.manage'] }
        : url.includes('/farmers') ? [{ id: 'f-1', name: 'Ena Gordon', parish: 'Manchester', production_lot_count: 0, committed_quantity_kg: '0' }] : [];
      return new Response(JSON.stringify(body), { status: 200 });
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><SuppliersWorkspace /></QueryClientProvider>);
    expect(await screen.findByText('Consent to be contacted')).toBeInTheDocument();
    expect(screen.getByLabelText(/Farmer name/)).toBeInTheDocument();
  });
});
