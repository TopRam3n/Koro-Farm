export type VerificationState = 'SELF_DECLARED' | 'VERIFIED' | 'REJECTED';

export interface FarmerProfile { displayName: string; contactVerified: boolean; parishId?: string; phone?: string; }
export interface Farm { id: string; name: string; parishId: string; district?: string; notes?: string; }
export interface FarmCrop { id: string; farmId: string; cropId: string; gradeId: string; status: 'ACTIVE' | 'PAUSED'; }
export interface CropCapability { id: string; farmCropId: string; declaredQuantity: number; declaredUnit: string; unitId: string; conversionFactor: number; conversionSource: string; conversionVersion: number; convertedKg: number; frequency: 'WEEKLY' | 'MONTHLY' | 'SEASONAL'; activeHarvestMonths: number[]; logisticsContext: string; }
export interface AvailabilityWindow { id: string; farmCropId: string; startDate: string; endDate: string; availableKg: number; note?: string; }
export interface ProductionLot { id: string; farmCropId: string; quantityKg: number; harvestDate: string; verification: VerificationState; createdAt: string; }
export interface Forecast { farmCropId: string; periodStart: string; periodEnd: string; forecastKg: number; basis: 'FARMER_ESTIMATE'; updatedAt: string; }
export interface FarmerPreferences { postHarvest: string[]; logistics: string[]; certificationIds: string[]; standbyOptIn?: boolean; paymentMethod?: 'CASH' | 'MOBILE_MONEY' | 'BANK_TRANSFER' | 'CHEQUE'; }

export interface FarmerSupplyState { profile: FarmerProfile; farms: Farm[]; farmCrops: FarmCrop[]; capabilities: CropCapability[]; availability: AvailabilityWindow[]; lots: ProductionLot[]; forecasts: Forecast[]; preferences: FarmerPreferences; }
