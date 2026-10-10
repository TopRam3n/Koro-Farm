import { describe, expect, it } from 'vitest';
import { ginger500Allocations } from '@/domain/fixtures/ginger-500kg';
import { selectCoverage, selectRecoveryEconomics, selectRequirementHealth } from '@/domain/selectors';

describe('supply assurance selectors', () => {
    it('models the deterministic 500 -> 420 -> 500 recovery', () => {
        expect(selectCoverage(500, ginger500Allocations).committedKg).toBe(500);
        const disrupted = ginger500Allocations.map(a => a.id === 'A-008' ? { ...a, state: 'LOST' as const } : a);
        expect(selectCoverage(500, disrupted).committedKg).toBe(420);
        expect(selectRequirementHealth(500, 420)).toBe('AT_RISK');
        const recovered = disrupted.map(a => a.id === 'A-009' ? { ...a, state: 'STANDBY_ACTIVATED' as const } : a);
        expect(selectCoverage(500, recovered).committedKg).toBe(500);
        expect(selectRequirementHealth(500, 500)).toBe('COVERED');
    });

    it('leaves the unaccepted remainder uncovered on partial acceptance', () => {
        const allocation = { ...ginger500Allocations[0], quantityKg: 120 };
        expect(selectCoverage(200, [allocation])).toMatchObject({ committedKg: 120, uncoveredKg: 80 });
    });

    it('calculates recovery economics', () => {
        const result = selectRecoveryEconomics({ originalCost: 186800, recoveredCost: 191400 });
        expect(result.premium).toBe(4600);
        expect(result.premiumPercent).toBeCloseTo(2.46, 2);
    });
});
