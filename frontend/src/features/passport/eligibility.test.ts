import { describe, expect, it } from 'vitest';
import { passportEligibility } from './eligibility';

describe('farmer passport eligibility', () => {
    it('does not assess fewer than three completed trades', () => expect(passportEligibility(2)).toEqual({ history: 'BUILDING_HISTORY', assessment: 'NOT_ASSESSED', showReliabilityIndex: false }));
    it('establishes history at three completed trades', () => expect(passportEligibility(3)).toEqual({ history: 'ESTABLISHED_HISTORY', assessment: 'ASSESSED', showReliabilityIndex: true }));
});
