import type { LegacyAllocation as Allocation, Economics } from '@/domain/types';

const committedStates = new Set(['COMMITTED', 'STANDBY_ACTIVATED']);

export function selectCoverage(requiredKg: number, allocations: Allocation[]) {
    const committedKg = allocations.filter(a => committedStates.has(a.state)).reduce((sum, a) => sum + a.quantityKg, 0);
    const standbyKg = allocations.filter(a => a.state === 'STANDBY').reduce((sum, a) => sum + a.quantityKg, 0);
    const uncoveredKg = Math.max(0, requiredKg - committedKg);
    return { requiredKg, committedKg, standbyKg, uncoveredKg, coveragePercent: requiredKg > 0 ? Math.min(100, committedKg / requiredKg * 100) : 0 };
}

export function selectRequirementHealth(requiredKg: number, committedKg: number, planningComplete = false): string {
    if (committedKg >= requiredKg) return 'COVERED';
    if (planningComplete && committedKg === 0) return 'UNFILLABLE';
    if (committedKg > 0) return 'AT_RISK';
    return 'PARTIALLY_COVERED';
}

export function selectRecoveryEconomics(economics: Pick<Economics, 'originalCost' | 'recoveredCost'>) {
    const premium = economics.recoveredCost - economics.originalCost;
    return { premium, premiumPercent: economics.originalCost > 0 ? premium / economics.originalCost * 100 : 0 };
}
