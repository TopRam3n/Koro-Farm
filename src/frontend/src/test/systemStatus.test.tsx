import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '@/components/AppShell';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }) } } }));
vi.mock('next/navigation', () => ({ usePathname: () => '/orders' }));

afterEach(() => { vi.unstubAllGlobals(); });

const identity = (role: string) => ({ id: 'u', email: 'c@example.test', name: 'C', active_organization_id: 'o', active_role: role, active_farmer_id: null, active_buyer_id: null });

function shell(role: string, status: unknown, statusCode = 200) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/me')) return new Response(JSON.stringify(identity(role)), { status: 200 });
    if (url.includes('/system/status')) return new Response(JSON.stringify(status), { status: statusCode });
    return new Response('[]', { status: 200 });
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AppShell>content</AppShell></QueryClientProvider>);
}

const degraded = { status: 'DEGRADED', reasons: ['worker_not_running', 'dead_letters'], checked_at: '', worker: { state: 'STOPPED', last_beat_at: null, live_workers: 0 }, processing: { overdue_messages: 0, dead_letters: 2, overdue_deadlines: 0 } };

describe('monitoring status is never assumed', () => {
  it('warns staff when the exception worker is not running, with the reasons', async () => {
    shell('SUPPLY_COORDINATOR', degraded);
    expect(await screen.findByRole('alert')).toHaveTextContent('Exception monitoring is degraded');
    expect(screen.getByRole('alert')).toHaveTextContent('The exception worker has stopped.');
    expect(screen.getByRole('alert')).toHaveTextContent('could not be processed');
    expect(screen.queryByText(/System operational|Synced now|Exception monitoring running/)).not.toBeInTheDocument();
  });

  it('says the status is unavailable rather than operational when it cannot be read', async () => {
    shell('SUPPLY_COORDINATOR', { detail: 'down' }, 503);
    expect((await screen.findAllByText('Monitoring status unavailable')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Exception monitoring running')).not.toBeInTheDocument();
  });

  it('shows farmers no staff monitoring status', async () => {
    shell('FARMER', degraded);
    await screen.findAllByText('My harvest');  // identity loaded: farmer navigation is shown
    expect(screen.queryByText(/Exception monitoring|Monitoring status/)).not.toBeInTheDocument();
  });
});
