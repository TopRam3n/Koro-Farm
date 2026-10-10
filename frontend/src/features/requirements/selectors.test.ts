import { describe, expect, it } from 'vitest';
import { requirementPortfolio } from './fixtures';
import { sortRequirementPortfolio, validateRequirementStep } from './selectors';

describe('buyer requirements', () => {
    it('prioritizes uncovered/at-risk requirements', () => { expect(sortRequirementPortfolio(requirementPortfolio)[0].id).toBe('REQ-REST-004'); });
    it('validates delivery window ordering', () => { expect(validateRequirementStep('window', { earliestAt: '2026-09-03', latestAt: '2026-09-02' })).toBe(false); expect(validateRequirementStep('window', { earliestAt: '2026-09-02', latestAt: '2026-09-03' })).toBe(true); });
    it('requires canonical taxonomy IDs rather than labels', () => { expect(validateRequirementStep('crop', { cropLabel: 'Fresh ginger' })).toBe(false); expect(validateRequirementStep('crop', { cropTaxonomyId: 'crop-ginger' })).toBe(true); });
    it('requires all mandatory steps before review submission', () => { const draft = { cropTaxonomyId: 'crop-ginger', gradeId: 'grade-a-v1', quantityKg: 500, earliestAt: '2026-09-02', latestAt: '2026-09-03', destinationSiteId: 'site-stjames' }; expect(validateRequirementStep('review', draft)).toBe(true); });
});
