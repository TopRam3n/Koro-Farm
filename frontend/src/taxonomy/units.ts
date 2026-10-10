export interface UnitConversion { id: string; label: string; cropId: string; factorToKg: number; source: string; version: number; }
export const units: UnitConversion[] = [
    { id: 'kg', label: 'Kilograms', cropId: '*', factorToKg: 1, source: 'SI', version: 1 },
    { id: 'lb', label: 'Pounds', cropId: '*', factorToKg: 0.45359237, source: 'NIST', version: 1 },
    { id: 'ginger-crate-demo', label: 'Ginger crate (demo)', cropId: 'crop-ginger', factorToKg: 20, source: 'KoroFarm demo fixture only', version: 1 },
];
export function getConversion(cropId: string, unitId: string) { return units.find(unit => unit.id === unitId && (unit.cropId === '*' || unit.cropId === cropId)); }
