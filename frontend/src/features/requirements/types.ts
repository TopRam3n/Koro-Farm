import type { SupplyHealth } from '@/domain/types';

export interface RequirementPortfolioItem {
    id: string; crop: string; grade: string; requiredKg: number; committedKg: number;
    standbyKg: number; uncoveredKg: number; health: SupplyHealth; targetAt: string;
    destination: string; lastEvent: string; lastEventAt: string;
}

export interface RequirementDraft {
    cropTaxonomyId: string; cropLabel: string; gradeId: string; gradeLabel: string;
    quantityKg: number; enteredUnit: 'kg'; earliestAt: string; latestAt: string;
    destinationSiteId: string; destinationLabel: string; receivingConstraints: string;
    complianceRequirements: string; priceCeilingJmd?: number;
}

export const requirementSteps = ['crop', 'grade', 'volume', 'window', 'destination', 'commercial', 'review'] as const;
export type RequirementStep = typeof requirementSteps[number];
