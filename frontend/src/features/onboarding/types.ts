export interface FarmerCapability {
    cropId: string; declaredQuantity: number; declaredUnit: string; unitId: string;
    conversionFactor: number; conversionSource: string; conversionVersion: number; convertedKg: number;
    frequency: 'WEEKLY' | 'MONTHLY' | 'SEASONAL'; activeHarvestMonths: number[]; gradeId: string; logisticsContext: string;
}
export type SignupPersona = 'FARMER' | 'BUYER';
