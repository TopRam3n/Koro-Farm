import type { AllocationState } from '@/domain/types';

export interface FarmerCommitment {
    id: string; requirementId: string; allocationId: string; farmerId: string;
    crop: string; grade: string; quantityKg: number; lotId: string;
    scheduledAt: string; location: string; pricePerKgJmd: number; paymentTerms: string;
    role: 'COMMITTED' | 'STANDBY'; state: AllocationState;
}

export interface ShortfallReport {
    commitmentId: string; expectedKg: number; lostKg: number;
    reason: 'CROP_LOSS' | 'WEATHER' | 'LABOUR' | 'TRANSPORT' | 'OTHER';
    note?: string; expectedResolution?: string;
}
