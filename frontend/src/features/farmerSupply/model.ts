import { getConversion } from '@/taxonomy/units';
import type { CropCapability, FarmerSupplyState, ProductionLot } from './types';

export const FARMER_SUPPLY_KEY = 'korofarm.farmer-supply-v1';

export const emptyFarmerSupplyState = (): FarmerSupplyState => ({ profile: { displayName: '', contactVerified: false }, farms: [], farmCrops: [], capabilities: [], availability: [], lots: [], forecasts: [], preferences: { postHarvest: [], logistics: [], certificationIds: [] } });

export function createCapability(input: Omit<CropCapability, 'conversionFactor' | 'conversionSource' | 'conversionVersion' | 'convertedKg'>, cropId: string): CropCapability {
    const conversion = getConversion(cropId, input.unitId);
    if (!conversion || input.declaredQuantity <= 0) throw new Error('INVALID_CAPABILITY_CONVERSION');
    return { ...input, conversionFactor: conversion.factorToKg, conversionSource: conversion.source, conversionVersion: conversion.version, convertedKg: input.declaredQuantity * conversion.factorToKg };
}

export function generateLotId(farmCropId: string, now = new Date()): string { return `LOT-${now.toISOString().slice(0, 10).replace(/-/g, '')}-${farmCropId.slice(-6).toUpperCase()}-${now.getTime().toString(36).toUpperCase()}`; }
export function createProductionLot(input: Omit<ProductionLot, 'id' | 'verification' | 'createdAt'>, now = new Date()): ProductionLot { if (input.quantityKg <= 0) throw new Error('INVALID_LOT_QUANTITY'); return { ...input, id: generateLotId(input.farmCropId, now), verification: 'SELF_DECLARED', createdAt: now.toISOString() }; }

export interface ReadinessProjection { ready: boolean; completed: string[]; missing: string[]; }
export function projectActivationReadiness(state: FarmerSupplyState): ReadinessProjection { const checks = [{ label: 'verified contact', ok: state.profile.contactVerified }, { label: 'parish', ok: Boolean(state.profile.parishId) }, { label: 'farm', ok: state.farms.length > 0 }, { label: 'primary crop', ok: state.farmCrops.length > 0 }, { label: 'quantified capability', ok: state.capabilities.some(c => c.convertedKg > 0) }]; return { ready: checks.every(c => c.ok), completed: checks.filter(c => c.ok).map(c => c.label), missing: checks.filter(c => !c.ok).map(c => c.label) }; }

export interface PlanningEligibility { eligible: boolean; reasons: string[]; eligibleFarmCropIds: string[]; }
export function projectPlanningEligibility(state: FarmerSupplyState, today = new Date()): PlanningEligibility {
    const readiness = projectActivationReadiness(state); const day = today.toISOString().slice(0, 10); const ids = state.farmCrops.filter(fc => fc.status === 'ACTIVE' && state.capabilities.some(c => c.farmCropId === fc.id && c.convertedKg > 0) && state.availability.some(a => a.farmCropId === fc.id && a.availableKg > 0 && a.startDate <= day && a.endDate >= day)).map(fc => fc.id); const reasons = [...readiness.missing]; if (!ids.length) reasons.push('no currently available eligible crop'); return { eligible: readiness.ready && ids.length > 0, reasons, eligibleFarmCropIds: ids };
}
