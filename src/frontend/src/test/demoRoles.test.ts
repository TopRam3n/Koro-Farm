import { afterEach, describe, expect, it, vi } from 'vitest';
import { demoApiFetch } from '@/lib/demoApi';

afterEach(() => vi.unstubAllEnvs());

describe('offline role workflows', () => {
  it('lets a buyer watch a crop, receive an alert, and place a quantity-safe order', async () => {
    vi.stubEnv('NEXT_PUBLIC_DEMO_ROLE', 'BUYER');
    const profile = await demoApiFetch<{ active_role: string }>('/me');
    expect(profile.active_role).toBe('BUYER');

    const availability = await demoApiFetch<{ items: Array<{ production_lot_id: string; crop: string }> }>('/marketplace/availability?crop=YAM');
    expect(availability.items).toHaveLength(1);
    const lotId = availability.items[0].production_lot_id;

    await demoApiFetch('/marketplace/watches', {
      method: 'POST', body: JSON.stringify({ crop: 'YAM', minimum_quantity_kg: '100' }),
    });
    const alerts = await demoApiFetch<{ items: Array<{ production_lot_id: string; available_quantity_kg: string }> }>('/marketplace/alerts');
    expect(alerts.items[0].production_lot_id).toBe(lotId);
    expect(alerts.items[0].available_quantity_kg).toBe('120.000');

    await demoApiFetch('/marketplace/orders', {
      method: 'POST', body: JSON.stringify({ production_lot_id: lotId, quantity_kg: '15' }),
    });
    const remaining = await demoApiFetch<{ items: Array<{ available_quantity_kg: string }> }>('/marketplace/availability?crop=YAM');
    expect(remaining.items[0].available_quantity_kg).toBe('105.000');
    const refreshedAlerts = await demoApiFetch<{ items: Array<{ available_quantity_kg: string }> }>('/marketplace/alerts');
    expect(refreshedAlerts.items[0].available_quantity_kg).toBe('105.000');
  });

  it('limits farmer demo accounts to their own harvest reporting workflow', async () => {
    vi.stubEnv('NEXT_PUBLIC_DEMO_ROLE', 'FARMER');
    const created = await demoApiFetch<{ production_lot_id: string; verification_status: string }>('/v1/ingestion/farmer-production-lots', {
      method: 'POST',
      body: JSON.stringify({ crop: 'MANGO', harvest_start: '2026-12-01', harvest_end: '2026-12-15', expected_quantity_kg: '42', quality_grade_estimate: 'A' }),
    });
    expect(created.verification_status).toBe('SELF_REPORTED');
    let lots = await demoApiFetch<Array<{ id: string; crop: string; quality_grade_estimate: string; available_quantity_kg: string; status: string }>>('/production-lots');
    expect(lots).toHaveLength(1);
    expect(lots[0]).toMatchObject({ id: created.production_lot_id, crop: 'MANGO', quality_grade_estimate: 'A', available_quantity_kg: '0.000', status: 'UNAVAILABLE' });
    vi.stubEnv('NEXT_PUBLIC_DEMO_ROLE', 'BUYER');
    let marketplace = await demoApiFetch<{ items: Array<{ production_lot_id: string }> }>('/marketplace/availability');
    expect(marketplace.items.some(lot => lot.production_lot_id === created.production_lot_id)).toBe(false);
    vi.stubEnv('NEXT_PUBLIC_DEMO_ROLE', 'FARMER');
    await demoApiFetch(`/v1/ingestion/farmer-production-lots/${created.production_lot_id}/availability`, {
      method: 'POST', body: JSON.stringify({ available_quantity_kg: '20' }),
    });
    lots = await demoApiFetch('/production-lots');
    expect(lots[0].available_quantity_kg).toBe('20.000');
    vi.stubEnv('NEXT_PUBLIC_DEMO_ROLE', 'BUYER');
    marketplace = await demoApiFetch('/marketplace/availability');
    expect(marketplace.items.some(lot => lot.production_lot_id === created.production_lot_id)).toBe(true);
  });

  it('does not expose the customer marketplace to staff demo roles', async () => {
    vi.stubEnv('NEXT_PUBLIC_DEMO_ROLE', 'SUPPLY_COORDINATOR');
    await expect(demoApiFetch('/marketplace/availability')).rejects.toThrow('not available');
  });
});
