export type PassportHistory = 'BUILDING_HISTORY' | 'ESTABLISHED_HISTORY';
export type PassportAssessment = 'NOT_ASSESSED' | 'ASSESSED';

export function passportEligibility(completedTrades: number): { history: PassportHistory; assessment: PassportAssessment; showReliabilityIndex: boolean } {
    if (completedTrades < 3) return { history: 'BUILDING_HISTORY', assessment: 'NOT_ASSESSED', showReliabilityIndex: false };
    return { history: 'ESTABLISHED_HISTORY', assessment: 'ASSESSED', showReliabilityIndex: true };
}
