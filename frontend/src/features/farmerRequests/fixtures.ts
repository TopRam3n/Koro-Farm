import type { FarmerRequest } from './types';

export const farmerRequests: FarmerRequest[] = [
    { id: 'FR-001', requirementId: 'REQ-HOTEL-001', farmerId: 'F-009', crop: 'Fresh ginger', grade: 'Grade A', requestedKg: 80, pricePerKgJmd: 280, destination: 'St. James Collection Hub', collectionAt: '2026-09-02T08:00:00-05:00', responseExpiresAt: '2026-09-01T18:00:00-05:00', paymentTerms: 'Net 7 days after accepted grading', role: 'STANDBY', state: 'PENDING' },
    { id: 'FR-002', requirementId: 'REQ-REST-004', farmerId: 'F-009', crop: 'Scotch bonnet pepper', grade: 'Grade A', requestedKg: 35, pricePerKgJmd: 650, destination: 'Kingston Collection Point', collectionAt: '2026-09-04T09:00:00-05:00', responseExpiresAt: '2026-09-02T12:00:00-05:00', paymentTerms: 'Net 7 days after accepted grading', role: 'COMMITTED', state: 'PENDING' },
];
