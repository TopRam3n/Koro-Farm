import { describe, expect, it } from 'vitest';
import { hasActiveMembership } from './authorization';

describe('authorization membership checks', () => {
    const memberships = [{ id: 'm-1', userId: 'u-1', organizationId: 'org-1', persona: 'BUYER' as const, role: 'ADMIN' as const, status: 'ACTIVE' as const }];
    it('permits matching active persona and role', () => { expect(hasActiveMembership(memberships, 'BUYER')).toBe(true); expect(hasActiveMembership(memberships, 'BUYER', 'ADMIN')).toBe(true); });
    it('rejects other personas and roles', () => { expect(hasActiveMembership(memberships, 'FARMER')).toBe(false); expect(hasActiveMembership(memberships, 'BUYER', 'MEMBER')).toBe(false); });
    it('rejects inactive membership', () => { expect(hasActiveMembership([{ ...memberships[0], status: 'SUSPENDED' }], 'BUYER')).toBe(false); });
});
