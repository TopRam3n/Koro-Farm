import { apiFetch } from '@/lib/api';

export type FarmRead = { id: string; name: string; parish: string; active: boolean };
export type FarmerCropRead = { crop: string; active: boolean };
export type FarmerProfile = {
  id: string;
  name: string;
  parish: string;
  active: boolean;
  farms: FarmRead[];
  crops: FarmerCropRead[];
};
export type HistoricalProduction = {
  crop: string;
  production_year: number;
  production_quarter: number;
  production_kg: string;
  data_source: string;
  is_simulated: boolean;
};

export function getFarmerProfile(farmerId: string) {
  return apiFetch<FarmerProfile>(`/farmers/${encodeURIComponent(farmerId)}/profile`);
}

export function getFarmerProductionHistory(farmerId: string, filters: { year?: number; crop?: string } = {}) {
  const query = new URLSearchParams();
  if (filters.year != null) query.set('year', String(filters.year));
  if (filters.crop) query.set('crop', filters.crop);
  return apiFetch<HistoricalProduction[]>(`/farmers/${encodeURIComponent(farmerId)}/production-history${query.size ? `?${query}` : ''}`);
}

export function quarterlySeries(records: HistoricalProduction[], crop?: string) {
  const selected = records.filter(record => !crop || record.crop === crop);
  const keys = new Map<string, { quarter: string; kilograms: number }>();
  for (const record of selected) {
    const quarter = `${record.production_year} Q${record.production_quarter}`;
    const item = keys.get(quarter) ?? { quarter, kilograms: 0 };
    item.kilograms += Number(record.production_kg);
    keys.set(quarter, item);
  }
  return Array.from(keys.values()).sort((a, b) => a.quarter.localeCompare(b.quarter));
}

export function annualSeries(records: HistoricalProduction[], crop?: string) {
  const selected = records.filter(record => !crop || record.crop === crop);
  const keys = new Map<number, { year: string; kilograms: number }>();
  for (const record of selected) {
    const item = keys.get(record.production_year) ?? { year: String(record.production_year), kilograms: 0 };
    item.kilograms += Number(record.production_kg);
    keys.set(record.production_year, item);
  }
  return Array.from(keys.values()).sort((a, b) => a.year.localeCompare(b.year));
}
