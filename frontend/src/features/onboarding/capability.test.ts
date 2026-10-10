import { describe, expect, it } from 'vitest';
import { createFarmerCapability } from './capability';
import { getConversion } from '@/taxonomy/units';

const base = { cropId: 'crop-ginger', declaredQuantity: 10, declaredUnit: 'lb', unitId: 'lb', frequency: 'WEEKLY' as const, activeHarvestMonths: [9], gradeId: 'grade-a-v1', logisticsContext: 'Collection hub' };
describe('farmer capability conversion', () => {
    it('persists conversion metadata and canonical kg', () => { const c = createFarmerCapability(base); expect(c.convertedKg).toBeCloseTo(4.5359237); expect(c).toMatchObject({ conversionFactor: 0.45359237, conversionSource: 'NIST', conversionVersion: 1 }); });
    it('supports crop-specific packaging metadata', () => { const c = createFarmerCapability({ ...base, declaredQuantity: 3, declaredUnit: 'crate', unitId: 'ginger-crate-demo' }); expect(c.convertedKg).toBe(60); expect(c.conversionSource).toContain('demo fixture'); });
    it('does not apply crop-specific packaging universally', () => { expect(getConversion('crop-pepper', 'ginger-crate-demo')).toBeUndefined(); expect(() => createFarmerCapability({ ...base, cropId: 'crop-pepper', unitId: 'ginger-crate-demo' })).toThrow('INVALID_CAPABILITY_CONVERSION'); });
});
