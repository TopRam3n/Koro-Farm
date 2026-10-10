import type { AppMembership, AppRole, Persona } from './types';

export interface MembershipRow { id: string; user_id: string; organization_id: string; persona: string; role: string; status: string; }

export function toMembership(row: MembershipRow): AppMembership {
    const personas: Persona[] = ['BUYER', 'FARMER', 'OPS'];
    const roles: AppRole[] = ['MEMBER', 'PRODUCER', 'ADMIN', 'COORDINATOR'];
    if (!personas.includes(row.persona as Persona) || !roles.includes(row.role as AppRole) || !['ACTIVE', 'PENDING', 'SUSPENDED'].includes(row.status)) throw new Error('INVALID_MEMBERSHIP_ROW');
    return { id: row.id, userId: row.user_id, organizationId: row.organization_id, persona: row.persona as Persona, role: row.role as AppRole, status: row.status as AppMembership['status'] };
}
