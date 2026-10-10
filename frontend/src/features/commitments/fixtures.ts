import type { FarmerCommitment } from './types';

export const farmerCommitments: FarmerCommitment[] = [{
    id: 'COM-008', requirementId: 'REQ-HOTEL-001', allocationId: 'A-008', farmerId: 'F-008',
    crop: 'Fresh ginger', grade: 'Grade A', quantityKg: 80, lotId: 'LOT-HAN-01',
    scheduledAt: '2026-09-02T08:00:00-05:00', location: 'St. James Collection Hub',
    pricePerKgJmd: 270, paymentTerms: 'Net 7 days after accepted grading', role: 'COMMITTED', state: 'COMMITTED',
}];
