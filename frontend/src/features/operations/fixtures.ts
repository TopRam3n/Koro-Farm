import type { Escalation } from './types';
export const escalations: Escalation[] = [
    { id: 'ESC-001', type: 'COORDINATOR_HELP', relatedEntityId: 'FR-001', createdAt: '2026-09-01T10:30:00-05:00', priority: 'MEDIUM', status: 'OPEN', contextHref: '/f/requests/FR-001' },
    { id: 'ESC-002', type: 'COMPLIANCE_REVIEW', relatedEntityId: 'REQ-HOTEL-001', createdAt: '2026-09-01T11:00:00-05:00', priority: 'HIGH', owner: 'Ops queue', status: 'ASSIGNED', contextHref: '/b/requirements/REQ-HOTEL-001/fulfilment' },
];
