import type { RequirementDraft, RequirementPortfolioItem, RequirementStep } from './types';

export function sortRequirementPortfolio(items: RequirementPortfolioItem[]) {
    return [...items].sort((a, b) => {
        const riskA = a.uncoveredKg > 0 || a.health === 'AT_RISK' ? 0 : 1;
        const riskB = b.uncoveredKg > 0 || b.health === 'AT_RISK' ? 0 : 1;
        return riskA - riskB || Date.parse(a.targetAt) - Date.parse(b.targetAt) || Date.parse(b.lastEventAt) - Date.parse(a.lastEventAt);
    });
}

export function validateRequirementStep(step: RequirementStep, draft: Partial<RequirementDraft>) {
    switch (step) {
        case 'crop': return Boolean(draft.cropTaxonomyId);
        case 'grade': return Boolean(draft.gradeId);
        case 'volume': return Number(draft.quantityKg) > 0;
        case 'window': return Boolean(draft.earliestAt && draft.latestAt && Date.parse(draft.earliestAt) <= Date.parse(draft.latestAt));
        case 'destination': return Boolean(draft.destinationSiteId);
        case 'commercial': return draft.priceCeilingJmd === undefined || draft.priceCeilingJmd > 0;
        case 'review': return ['crop', 'grade', 'volume', 'window', 'destination', 'commercial'].every(item => validateRequirementStep(item as RequirementStep, draft));
    }
}
