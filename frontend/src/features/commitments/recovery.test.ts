import { describe, expect, it } from 'vitest';
import { createRecoveryEvents, projectCoverage } from './recovery';

describe('cross-persona recovery loop', () => {
    const events = createRecoveryEvents({ commitmentId: 'COM-008', expectedKg: 0, lostKg: 80, reason: 'CROP_LOSS' });
    it('starts from the farmer shortfall domain event', () => { expect(events[0]).toMatchObject({ type: 'allocation.shortfall_reported', actorType: 'FARMER', allocationId: 'A-008', payload: { lostKg: 80, remainingKg: 0 } }); });
    it('projects buyer coverage 500 -> 420 -> 500', () => { expect(projectCoverage(events)).toEqual({ initialKg: 500, disruptedKg: 420, restoredKg: 500 }); });
    it('activates explicit standby capacity before restoring coverage', () => { expect(events.map(event => event.type)).toEqual(['allocation.shortfall_reported', 'allocation.lost', 'requirement.at_risk', 'allocation.standby_activated', 'requirement.coverage_restored', 'recovery.cost_changed']); });
});
