import type { RequirementPortfolioItem } from './types';

export const requirementPortfolio: RequirementPortfolioItem[] = [
    { id: 'REQ-HOTEL-001', crop: 'Fresh ginger', grade: 'Grade A', requiredKg: 500, committedKg: 500, standbyKg: 120, uncoveredKg: 0, health: 'COVERED', targetAt: '2026-09-02T08:00:00-05:00', destination: 'St. James Collection Hub', lastEvent: 'Coverage restored', lastEventAt: '2026-08-31T14:05:01-05:00' },
    { id: 'REQ-REST-004', crop: 'Scotch bonnet pepper', grade: 'Grade A', requiredKg: 200, committedKg: 120, standbyKg: 30, uncoveredKg: 80, health: 'AT_RISK', targetAt: '2026-09-04T09:00:00-05:00', destination: 'Kingston Collection Point', lastEvent: 'Partial acceptance recorded', lastEventAt: '2026-09-01T09:00:00-05:00' },
];
