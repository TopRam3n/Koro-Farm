"""Strict offline serving contract. Validation never supplies missing statistics."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
NonNegative = Annotated[Number, Field(ge=0)]
Count = Annotated[int, Field(ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow', allow_inf_nan=False)


class Observation(Contract):
    period: str
    year: int
    quarter: Annotated[int, Field(ge=1, le=4)]
    production_tonnes: NonNegative | None
    farmgate_price_jmd_kg: NonNegative | None
    area_hectares: NonNegative | None


class Metric(Contract):
    n: Count
    mae_tonnes: NonNegative | None
    wape_pct: NonNegative | None
    bias_tonnes: Number | None

    @model_validator(mode='after')
    def measurements(self):
        if self.n and (self.mae_tonnes is None or self.bias_tonnes is None):
            raise ValueError('Evaluated targets require measured MAE and bias')
        if not self.n and any(v is not None for v in (self.mae_tonnes, self.wape_pct, self.bias_tonnes)):
            raise ValueError('No targets: metrics must be unavailable')
        return self


class Models(Contract):
    previous_quarter: Metric
    seasonal_naive: Metric
    seasonal_average: Metric
    ridge_lags: Metric


class Metrics(Contract):
    all: Models
    selection: Models
    holdout: Models  # Existing wire key; later evaluation also influenced selection.


class Configuration(Contract):
    version: str
    ridge_alpha: NonNegative
    first_test_period: str
    selection_end: str
    holdout_start: str
    min_valid_history: Count
    min_ridge_rows: Count


class Predictions(Contract):
    previous_quarter: NonNegative
    seasonal_naive: NonNegative
    seasonal_average: NonNegative
    ridge_lags: NonNegative


class Evaluation(Contract):
    period: str
    training_end: str
    training_valid_count: Count
    actual: NonNegative
    predictions: Predictions


class Forecast(Contract):
    status: Literal['available', 'unavailable']
    value_tonnes: NonNegative | None
    period: str | None
    horizon_quarters: Literal[1]
    data_cutoff: str | None
    model: Literal['previous_quarter', 'seasonal_naive', 'seasonal_average', 'ridge_lags']
    interval: None
    label: str
    unavailable_reason: str | None

    @model_validator(mode='after')
    def availability(self):
        if self.status == 'available' and (self.value_tonnes is None or not self.period or not self.data_cutoff):
            raise ValueError('Available forecast requires value, period and cutoff')
        if self.status == 'unavailable' and (self.value_tonnes is not None or not self.unavailable_reason):
            raise ValueError('Unavailable forecast requires null value and reason')
        return self


class Experiment(Contract):
    config: Configuration
    method: str
    availability_assumption: str
    evaluation_status: Literal['retrospective_latest_vintage']
    metrics: Metrics
    forecasts: list[Evaluation]
    skipped_test_periods: list[str]
    selected_model: Literal['previous_quarter', 'seasonal_naive', 'seasonal_average', 'ridge_lags']
    candidate_qualifies: bool
    selection_rule: str
    forecast: Forecast


class ConflictValue(Contract):
    value: NonNegative
    url: str
    page: Annotated[int, Field(ge=1)]


class Conflict(Contract):
    id: str
    period: str
    measurement: str
    reason: str
    values: list[ConflictValue]


class Counts(Contract):
    production: Count
    area: Count
    price: Count


class Quality(Contract):
    dataset_version: str
    validated_counts: Counts
    gaps: list[str]
    conflicts: list[Conflict]
    notes: list[str]
    sanity_checks_passed: Literal[True]


class Source(Contract):
    url: str
    index_url: str
    local_path: str
    label: str
    kind: str
    year: int
    sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    publication_date: str | None
    http_last_modified: str | None
    retrieved_at: str


class AnnualRecord(Contract):
    id: str
    year: int
    frequency: Literal['annual']
    quarter: None
    measurement: str
    value: NonNegative
    unit: str
    flag: str
    flag_description: str


class Item(Contract):
    code: str
    label: str


class AnnualValidation(Contract):
    observations: Count
    years: list[int]
    missing_requested_years: list[int]
    items: list[Item]
    flags: dict[str, Count]


class AnnualAvailable(Contract):
    status: Literal['available']
    frequency: Literal['annual']
    item_label: str
    source_url: str
    retrieved_at: str
    dataset_version: str
    validation: AnnualValidation
    records: Annotated[list[AnnualRecord], Field(min_length=1)]


class AnnualUnavailable(Contract):
    status: Literal['unavailable']
    frequency: Literal['annual']
    records: Annotated[list[AnnualRecord], Field(max_length=0)]
    reason: str


class IntelligenceArtifact(Contract):
    schema_version: Literal[1]
    status: Literal['available']
    country: Literal['Jamaica']
    geography: Literal['national']
    crop: Literal['iceberg_lettuce']
    crop_label: str
    dataset_version: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    artifact_version: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    generated_at: str
    last_ingested_at: str
    series: list[Observation]
    experiment: Experiment
    quality: Quality
    sources: Annotated[list[Source], Field(min_length=1)]
    limitations: list[str]
    annual_context: AnnualAvailable | AnnualUnavailable

    @model_validator(mode='after')
    def consistency(self):
        if self.dataset_version != self.quality.dataset_version:
            raise ValueError('Dataset identities disagree')
        if not self.series and self.experiment.forecast.status == 'available':
            raise ValueError('No history for available forecast')
        if any(r.period != f'{r.year} Q{r.quarter}' for r in self.series):
            raise ValueError('Invalid reporting period')
        if any(b.year*4+b.quarter - (a.year*4+a.quarter) != 1 for a,b in zip(self.series, self.series[1:])):
            raise ValueError('Missing or duplicate calendar quarters')
        return self
