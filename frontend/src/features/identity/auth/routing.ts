import type { AppMembership, Persona } from './types';

export const personaHome = (persona: Persona) => persona === 'FARMER' ? '/f' : persona === 'BUYER' ? '/b' : '/ops';

export function resolvePostLoginRoute(memberships: AppMembership[]): string {
    const active = memberships.filter(m => m.status === 'ACTIVE');
    if (!active.length) return memberships.some(m => m.status === 'PENDING') ? '/account/pending' : '/account/setup';
    const personas = [...new Set(active.map(m => m.persona))];
    return personas.length === 1 ? personaHome(personas[0]) : '/account/persona';
}

export function activeAlternatePersona(memberships: AppMembership[], requested: Persona): Persona | undefined {
    return memberships.find(m => m.status === 'ACTIVE' && m.persona !== requested)?.persona;
}
