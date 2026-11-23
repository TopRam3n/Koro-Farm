import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EconomicsPanel } from '@/components/EconomicsPanel';
import { FulfilmentPanel } from '@/components/FulfilmentPanel';

vi.mock('@/integrations/supabase/client', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: null } }), onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }) } } }));

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

describe('unknown-state rendering', () => {
  it('does not turn missing economics into J$0', () => {
    render(<EconomicsPanel economics={null} />);
    expect(screen.getByText(/unknown, not J\$0/i)).toBeInTheDocument();
  });

  it('does not turn unavailable physical state into zero kilograms', () => {
    render(<FulfilmentPanel summary={null} />);
    expect(screen.getByText(/No quantity is assumed/i)).toBeInTheDocument();
  });
});

describe('retired offline demo replay', () => {
  it('renders only a disabled notice when a build requests demo mode', async () => {
    vi.stubEnv('NEXT_PUBLIC_APP_MODE', 'demo');
    vi.resetModules();
    const { Providers } = await import('@/app/providers');
    render(<Providers><p>application screen</p></Providers>);
    expect(screen.getByRole('alert')).toHaveTextContent('The offline demo replay is disabled');
    expect(screen.queryByText('application screen')).not.toBeInTheDocument();
  });
});
