import type { LegacyAllocation as Allocation, Economics, Fulfilment } from '@/domain/types';
import type { KoroFarmDomainEvent } from '@/domain/events';
import { createRecoveryEvents } from '@/features/commitments/recovery';

const requirementId = 'REQ-HOTEL-001';

export const ginger500Requirement = {
    id: requirementId,
    buyer: 'Blue Mountain Lodge',
    buyerType: 'Institutional hotel',
    destination: 'Montego Bay, Jamaica',
    crop: 'Fresh ginger',
    grade: 'Grade A',
    requiredKg: 500,
    deliveryWindow: '01-02 Sep 2026',
    state: 'COVERED',
};

export const ginger500Allocations: Allocation[] = [
    ['A-001', 'Mavis Thompson', 'F-001', 'Manchester', 'LOT-MAN-01', 50],
    ['A-002', 'Leon Reid', 'F-002', 'St. Elizabeth', 'LOT-STE-04', 72],
    ['A-003', 'Owen Campbell', 'F-003', 'Clarendon', 'LOT-CLA-02', 64],
    ['A-004', 'Renee Brown', 'F-004', 'St. Ann', 'LOT-STA-08', 58],
    ['A-005', 'Damian Grant', 'F-005', 'St. Mary', 'LOT-STM-03', 55],
    ['A-006', 'Althea Morgan', 'F-006', 'Portland', 'LOT-POR-05', 61],
    ['A-007', 'Curtis Hall', 'F-007', 'Westmoreland', 'LOT-WES-02', 60],
    ['A-008', 'Nadine Ellis', 'F-008', 'Hanover', 'LOT-HAN-01', 80],
].map(([id, farmer, farmerId, parish, lotId, quantityKg]) => ({
    id: id as string, requirementId, farmer: farmer as string, farmerId: farmerId as string,
    parish: parish as string, lotId: lotId as string, quantityKg: quantityKg as number,
    role: 'COMMITTED', state: 'COMMITTED', verificationState: 'NOT_PROVIDED',
}));

ginger500Allocations.push(
    { id: 'A-009', requirementId, farmer: 'Peter Wallace', farmerId: 'F-009', parish: 'St. Catherine', lotId: 'LOT-STC-06', quantityKg: 80, role: 'STANDBY', state: 'STANDBY', verificationState: 'NOT_PROVIDED' },
    { id: 'A-010', requirementId, farmer: 'Shanice Forbes', farmerId: 'F-010', parish: 'Trelawny', lotId: 'LOT-TRE-02', quantityKg: 40, role: 'STANDBY', state: 'STANDBY', verificationState: 'NOT_PROVIDED' },
);

export const ginger500Economics: Economics = { currency: 'JMD', originalCost: 186800, recoveredCost: 191400, premium: 4600, premiumPercent: 2.46 };
export const ginger500Fulfilment: Fulfilment = { node: 'St. James Collection Hub', state: 'AWAITING_RECEIPT', requiredKg: 500, receivedKg: 0, acceptedKg: 0, rejectedKg: 0 };

export const ginger500RecoveryEvents: KoroFarmDomainEvent[] = createRecoveryEvents({ commitmentId: 'COM-008', expectedKg: 0, lostKg: 80, reason: 'CROP_LOSS' });
