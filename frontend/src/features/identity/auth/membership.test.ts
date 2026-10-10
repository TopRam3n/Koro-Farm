import { describe, expect, it } from 'vitest';
import { toMembership } from './membership';
import { activeAlternatePersona, resolvePostLoginRoute } from './routing';

const farmer = toMembership({ id: 'm-f', user_id: 'u', organization_id: 'individual-u', persona: 'FARMER', role: 'PRODUCER', status: 'ACTIVE' });
const buyer = toMembership({ id: 'm-b', user_id: 'u', organization_id: 'org-b', persona: 'BUYER', role: 'MEMBER', status: 'ACTIVE' });

describe('membership access path', () => {
    it('normalizes protected membership rows', () => expect(farmer).toMatchObject({ id: 'm-f', userId: 'u', persona: 'FARMER', role: 'PRODUCER', status: 'ACTIVE' }));
    it('routes farmer and buyer login to persona homes', () => { expect(resolvePostLoginRoute([farmer])).toBe('/f'); expect(resolvePostLoginRoute([buyer])).toBe('/b'); });
    it('redirects a buyer away from farmer persona', () => expect(activeAlternatePersona([buyer], 'FARMER')).toBe('BUYER'));
    it('routes no membership, pending and multiple personas safely', () => { expect(resolvePostLoginRoute([])).toBe('/account/setup'); expect(resolvePostLoginRoute([{ ...farmer, status: 'PENDING' }])).toBe('/account/pending'); expect(resolvePostLoginRoute([farmer, buyer])).toBe('/account/persona'); });
    it('rejects malformed authorization rows', () => expect(() => toMembership({ id: 'x', user_id: 'u', organization_id: 'o', persona: 'FARMER', role: 'SUPERUSER', status: 'ACTIVE' })).toThrow('INVALID_MEMBERSHIP_ROW'));
});
