export type ModelMetrics = { n: number; mae_tonnes: number | null; wape_pct: number | null; bias_tonnes: number | null };
export type AgriculturalIntelligence = {
  schema_version: number;
  status: string;
  country: string;
  crop_label: string;
  dataset_version: string;
  artifact_version: string;
  generated_at: string;
  last_ingested_at: string;
  series: { period: string; year: number; quarter: number; production_tonnes: number | null; farmgate_price_jmd_kg: number | null; area_hectares: number | null }[];
  experiment: {
    method: string;
    availability_assumption: string;
    selected_model: string;
    selection_rule: string;
    candidate_qualifies: boolean;
    metrics: Record<'all' | 'selection' | 'holdout', Record<string, ModelMetrics>>;
    forecast: { status: string; value_tonnes: number | null; period: string | null; horizon_quarters: number; data_cutoff: string | null; model: string; label: string; unavailable_reason: string | null };
  };
  quality: {
    validated_counts: Record<string, number>;
    gaps: string[];
    conflicts: { id: string; period: string; measurement: string; reason: string; values: { value: number; url: string; page: number }[] }[];
    notes: string[];
  };
  sources: { url: string; index_url: string; local_path: string; label: string; kind: string; year: number; sha256: string; publication_date: string | null; http_last_modified: string | null }[];
  limitations: string[];
  annual_context?: {
    status: string; frequency: string; item_label?: string; source_url?: string;
    retrieved_at?: string; dataset_version?: string; reason?: string;
    validation?: { observations: number; years: number[]; missing_requested_years: number[]; items: {code:string;label:string}[]; flags: Record<string,number> };
    records: {id:string; year:number; measurement:string; value:number; unit:string; flag:string; flag_description:string}[];
  };
};

export const modelNames: Record<string, string> = {
  previous_quarter: 'Previous quarter', seasonal_naive: 'Same quarter last year',
  seasonal_average: 'Historical seasonal average', ridge_lags: 'Ridge regression with lags',
};
