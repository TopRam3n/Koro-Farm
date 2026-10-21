import { z } from 'zod';
import type { AgriculturalIntelligence } from './agriculturalIntelligence';

const numeric = z.number().finite();
const count = numeric.int().nonnegative();
const nonnegative = numeric.nonnegative();
const metric = z.object({ n: count, mae_tonnes: nonnegative.nullable(), wape_pct: nonnegative.nullable(), bias_tonnes: numeric.nullable() })
  .refine(m => m.n ? m.mae_tonnes !== null && m.bias_tonnes !== null : m.mae_tonnes === null && m.wape_pct === null && m.bias_tonnes === null);
const models = z.object({ previous_quarter: metric, seasonal_naive: metric, seasonal_average: metric, ridge_lags: metric });
const model = z.enum(['previous_quarter', 'seasonal_naive', 'seasonal_average', 'ridge_lags']);
const forecast = z.object({
  status: z.enum(['available', 'unavailable']), value_tonnes: nonnegative.nullable(),
  period: z.string().nullable(), horizon_quarters: z.literal(1), data_cutoff: z.string().nullable(),
  model, interval: z.null(), label: z.string(), unavailable_reason: z.string().nullable(),
}).refine(f => f.status === 'available' ? f.value_tonnes !== null && !!f.period && !!f.data_cutoff : f.value_tonnes === null && !!f.unavailable_reason);
const annualRecord = z.object({ id: z.string(), year: numeric.int(), frequency: z.literal('annual'), quarter: z.null(), measurement: z.string(), value: nonnegative, unit: z.string(), flag: z.string(), flag_description: z.string() });
const annual = z.discriminatedUnion('status', [
  z.object({ status: z.literal('available'), frequency: z.literal('annual'), item_label: z.string(), source_url: z.string(), retrieved_at: z.string(), dataset_version: z.string(),
    validation: z.object({ observations: count, years: z.array(numeric.int()), missing_requested_years: z.array(numeric.int()), items: z.array(z.object({ code: z.string(), label: z.string() })), flags: z.record(count) }), records: z.array(annualRecord).min(1) }),
  z.object({ status: z.literal('unavailable'), frequency: z.literal('annual'), reason: z.string(), records: z.array(annualRecord).max(0) }),
]);
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const schema = z.object({
  schema_version: z.literal(1), status: z.literal('available'), country: z.literal('Jamaica'), geography: z.literal('national'), crop: z.literal('iceberg_lettuce'), crop_label: z.string(),
  dataset_version: hash, artifact_version: hash, generated_at: z.string(), last_ingested_at: z.string(),
  series: z.array(z.object({ period: z.string(), year: numeric.int(), quarter: numeric.int().min(1).max(4), production_tonnes: nonnegative.nullable(), farmgate_price_jmd_kg: nonnegative.nullable(), area_hectares: nonnegative.nullable() })),
  experiment: z.object({
    config: z.object({ version: z.string(), ridge_alpha: nonnegative, first_test_period: z.string(), selection_end: z.string(), holdout_start: z.string(), min_valid_history: count, min_ridge_rows: count }),
    method: z.string(), availability_assumption: z.string(), evaluation_status: z.literal('retrospective_latest_vintage'), selected_model: model, selection_rule: z.string(), candidate_qualifies: z.boolean(),
    metrics: z.object({ all: models, selection: models, holdout: models }), forecast,
    forecasts: z.array(z.object({ period: z.string(), training_end: z.string(), training_valid_count: count, actual: nonnegative, predictions: z.object({ previous_quarter: nonnegative, seasonal_naive: nonnegative, seasonal_average: nonnegative, ridge_lags: nonnegative }) })),
    skipped_test_periods: z.array(z.string()),
  }),
  quality: z.object({ dataset_version: hash, sanity_checks_passed: z.literal(true), validated_counts: z.object({ production: count, area: count, price: count }), gaps: z.array(z.string()), notes: z.array(z.string()),
    conflicts: z.array(z.object({ id: z.string(), period: z.string(), measurement: z.string(), reason: z.string(), values: z.array(z.object({ value: nonnegative, url: z.string(), page: count.min(1) })) })) }),
  sources: z.array(z.object({ url: z.string(), index_url: z.string(), local_path: z.string(), label: z.string(), kind: z.string(), year: numeric.int(), sha256: hash, publication_date: z.string().nullable(), http_last_modified: z.string().nullable(), retrieved_at: z.string() })).min(1),
  limitations: z.array(z.string()), annual_context: annual,
}).refine(d => d.dataset_version === d.quality.dataset_version && (d.series.length > 0 || d.experiment.forecast.status === 'unavailable')
  && d.series.every((r, i) => r.period === `${r.year} Q${r.quarter}` && (i === 0 || r.year * 4 + r.quarter - (d.series[i-1].year * 4 + d.series[i-1].quarter) === 1)));

export function validateIntelligence(value: unknown): AgriculturalIntelligence {
  if (!schema.safeParse(value).success) throw new Error('Validated agricultural intelligence artifact is incomplete or invalid. Restore the verified cached snapshot or retry the data request.');
  // Return the original object: validation must not insert values or strip provenance.
  return value as AgriculturalIntelligence;
}
