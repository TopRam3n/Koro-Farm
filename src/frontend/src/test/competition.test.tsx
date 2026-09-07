import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { demoApiFetch, resetDemoState } from '@/lib/demoApi';
import { EconomicsPanel } from '@/components/EconomicsPanel';
import { FulfilmentPanel } from '@/components/FulfilmentPanel';

describe('competition demo contract', () => {
  beforeEach(() => resetDemoState());

  it('keeps standby distinct and exposes the 500/80 risk transition', async () => {
    const initial = await demoApiFetch<any>('/requirements/demo/assurance');
    expect(initial.committed_quantity_kg).toBe('500.000');
    expect(initial.standby_quantity_kg).toBe('100.000');
    await demoApiFetch('/allocations/demo-c1/dropout', { method: 'POST' });
    const risk = await demoApiFetch<any>('/requirements/demo/assurance');
    expect(risk.committed_quantity_kg).toBe('420.000');
    expect(risk.unfilled_quantity_kg).toBe('80.000');
    expect(risk.supply_health).toBe('AT_RISK');
  });

  it('restores committed coverage without inventing delivery', async () => {
    await demoApiFetch('/allocations/demo-c1/dropout', { method: 'POST' });
    await demoApiFetch('/requirements/demo/recovery', { method: 'POST' });
    const restored = await demoApiFetch<any>('/requirements/demo/assurance');
    expect(restored.committed_quantity_kg).toBe('500.000');
    expect(restored.supply_health).toBe('COVERED');
    expect(restored.latest_recovery.remaining_shortfall_kg).toBe('0.000');
  });
});

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
