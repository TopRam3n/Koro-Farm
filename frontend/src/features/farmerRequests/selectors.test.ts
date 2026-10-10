import { describe, expect, it } from 'vitest';
import { farmerRequests } from './fixtures';
import { decideRequest, isRequestExpired, selectActionableRequests } from './selectors';

const beforeExpiry = new Date('2026-09-01T12:00:00-05:00');

describe('farmer request workflow', () => {
    it('orders actionable requests by earliest expiration', () => { expect(selectActionableRequests([...farmerRequests].reverse(), beforeExpiry).map(r => r.id)).toEqual(['FR-001', 'FR-002']); });
    it('preserves partial acceptance remainder', () => { expect(decideRequest(farmerRequests[0], 50, beforeExpiry)).toEqual({ type: 'ACCEPT', acceptedKg: 50, remainderKg: 30 }); });
    it('blocks stale requests based on absolute expiry', () => { const now = new Date('2026-09-01T18:00:01-05:00'); expect(isRequestExpired(farmerRequests[0], now)).toBe(true); expect(() => decideRequest(farmerRequests[0], 80, now)).toThrow('REQUEST_EXPIRED'); });
    it('rejects invalid accepted quantities', () => { expect(() => decideRequest(farmerRequests[0], 81, beforeExpiry)).toThrow('INVALID_ACCEPTED_QUANTITY'); });
});
