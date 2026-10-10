import type { AppMembership } from './types';

export function hasActiveMembership(memberships: AppMembership[], persona: AppMembership['persona'], role?: AppMembership['role']) {
    return memberships.some(membership => membership.status === 'ACTIVE' && membership.persona === persona && (!role || membership.role === role));
}
