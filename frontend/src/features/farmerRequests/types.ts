import type { RequestState } from '@/domain/types';

export interface FarmerRequest {
    id: string;
    requirementId: string;
    farmerId: string;
    crop: string;
    grade: string;
    requestedKg: number;
    pricePerKgJmd: number;
    destination: string;
    collectionAt: string;
    responseExpiresAt: string;
    paymentTerms: string;
    role: 'COMMITTED' | 'STANDBY';
    state: RequestState;
}

export type FarmerRequestDecision =
    | { type: 'ACCEPT'; acceptedKg: number; remainderKg: number }
    | { type: 'DECLINE'; reason?: string }
    | { type: 'COORDINATOR_HELP' };
