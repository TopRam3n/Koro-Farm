import { getConversion } from '@/taxonomy/units';
import type { FarmerCapability } from './types';

export function createFarmerCapability(input: Omit<FarmerCapability, 'conversionFactor' | 'conversionSource' | 'conversionVersion' | 'convertedKg'>): FarmerCapability {
    const conversion = getConversion(input.cropId, input.unitId);
    if (!conversion || input.declaredQuantity <= 0) throw new Error('INVALID_CAPABILITY_CONVERSION');
    return { ...input, conversionFactor: conversion.factorToKg, conversionSource: conversion.source, conversionVersion: conversion.version, convertedKg: input.declaredQuantity * conversion.factorToKg };
}
