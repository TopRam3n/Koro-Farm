"""ORM mapping of the `agri` schema (migration 0029). PostgreSQL only.

Deliberately on its own declarative base and metadata, not the operational `Base`: the agricultural intelligence
data is public statistics and analysis, kept apart from tenant trade records. `Base.metadata.create_all` (SQLite
tests, development) never touches it; the schema exists only where the migration ran. A test compares this mapping
with the migrated database (tests/test_agriculture_postgres.py).
"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "agri"


class AgriBase(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


def _fk(target: str) -> ForeignKey:
    return ForeignKey(f"{SCHEMA}.{target}")


class Source(AgriBase):
    __tablename__ = "sources"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    publisher: Mapped[str] = mapped_column(String(200))
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    licence_name: Mapped[str | None] = mapped_column(String(120))
    licence_url: Mapped[str | None] = mapped_column(String(500))
    licence_review_status: Mapped[str] = mapped_column(String(30), default="NOT_REVIEWED")
    reuse_conditions: Mapped[str | None] = mapped_column(Text)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Dataset(AgriBase):
    __tablename__ = "datasets"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(_fk("sources.id"))
    code: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    landing_url: Mapped[str | None] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(20))
    frequency: Mapped[str] = mapped_column(String(20))
    geographic_level: Mapped[str] = mapped_column(String(30))
    measures: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Publication(AgriBase):
    __tablename__ = "publications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(_fk("datasets.id"))
    version_label: Mapped[str] = mapped_column(String(120))
    period_label: Mapped[str | None] = mapped_column(String(120))
    published_on: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieval_url: Mapped[str | None] = mapped_column(String(500))
    file_name: Mapped[str | None] = mapped_column(String(300))
    content_sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    retrieved_by: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="RETRIEVED")
    supersedes_publication_id: Mapped[UUID | None] = mapped_column(_fk("publications.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Unit(AgriBase):
    __tablename__ = "units"
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(20))
    canonical_code: Mapped[str] = mapped_column(String(30))
    factor_to_canonical: Mapped[Decimal] = mapped_column(Numeric(24, 12))
    description: Mapped[str] = mapped_column(String(200))


class Measure(AgriBase):
    __tablename__ = "measures"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    canonical_unit_code: Mapped[str] = mapped_column(_fk("units.code"))
    definition: Mapped[str] = mapped_column(Text)
    non_negative: Mapped[bool] = mapped_column(Boolean, default=True)


class Crop(AgriBase):
    __tablename__ = "crops"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    scientific_name: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(60))
    operational_crop_code: Mapped[str | None] = mapped_column(String(64))
    fao_item_code: Mapped[int | None] = mapped_column(Integer)
    fao_item_code_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CropAlias(AgriBase):
    __tablename__ = "crop_aliases"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    crop_id: Mapped[UUID] = mapped_column(_fk("crops.id"))
    source_id: Mapped[UUID | None] = mapped_column(_fk("sources.id"))
    alias: Mapped[str] = mapped_column(String(200))
    alias_normalized: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeoArea(AgriBase):
    __tablename__ = "geo_areas"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    level: Mapped[str] = mapped_column(String(30))
    parent_id: Mapped[UUID | None] = mapped_column(_fk("geo_areas.id"))
    iso_3166_code: Mapped[str | None] = mapped_column(String(10))
    m49_code: Mapped[str | None] = mapped_column(String(10))
    fao_area_code: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeoAlias(AgriBase):
    __tablename__ = "geo_aliases"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    geo_area_id: Mapped[UUID] = mapped_column(_fk("geo_areas.id"))
    source_id: Mapped[UUID | None] = mapped_column(_fk("sources.id"))
    alias: Mapped[str] = mapped_column(String(200))
    alias_normalized: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(AgriBase):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(_fk("datasets.id"))
    publication_id: Mapped[UUID | None] = mapped_column(_fk("publications.id"))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    parser_code: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    operator: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


class RawObservation(AgriBase):
    __tablename__ = "raw_observations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(_fk("ingestion_runs.id"))
    publication_id: Mapped[UUID] = mapped_column(_fk("publications.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSONB)
    row_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ValidationIssue(AgriBase):
    __tablename__ = "validation_issues"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ingestion_run_id: Mapped[UUID] = mapped_column(_fk("ingestion_runs.id"))
    raw_observation_id: Mapped[UUID | None] = mapped_column(_fk("raw_observations.id"))
    row_number: Mapped[int | None] = mapped_column(Integer)
    rule_code: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(10))
    field: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Observation(AgriBase):
    __tablename__ = "observations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(_fk("datasets.id"))
    publication_id: Mapped[UUID] = mapped_column(_fk("publications.id"))
    raw_observation_id: Mapped[UUID | None] = mapped_column(_fk("raw_observations.id"))
    measure_code: Mapped[str] = mapped_column(_fk("measures.code"))
    crop_id: Mapped[UUID] = mapped_column(_fk("crops.id"))
    geo_area_id: Mapped[UUID] = mapped_column(_fk("geo_areas.id"))
    period_type: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    unit_code: Mapped[str] = mapped_column(_fk("units.code"))
    value_canonical: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    canonical_unit_code: Mapped[str] = mapped_column(_fk("units.code"))
    status: Mapped[str] = mapped_column(String(20))
    quality_flag: Mapped[str | None] = mapped_column(String(40))
    source_flag: Mapped[str | None] = mapped_column(String(20))
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(_fk("observations.id"))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FaostatObservation(AgriBase):
    __tablename__ = "faostat_observations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    publication_id: Mapped[UUID] = mapped_column(_fk("publications.id"))
    raw_observation_id: Mapped[UUID | None] = mapped_column(_fk("raw_observations.id"))
    area_code: Mapped[int] = mapped_column(Integer)
    area_m49: Mapped[str | None] = mapped_column(String(10))
    area_name: Mapped[str] = mapped_column(String(200))
    item_code: Mapped[int] = mapped_column(Integer)
    item_cpc: Mapped[str | None] = mapped_column(String(20))
    item_name: Mapped[str] = mapped_column(String(200))
    element_code: Mapped[int] = mapped_column(Integer)
    element_name: Mapped[str] = mapped_column(String(200))
    year: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(40))
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    flag: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DerivedIndicator(AgriBase):
    __tablename__ = "derived_indicators"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    indicator_code: Mapped[str] = mapped_column(String(80))
    crop_id: Mapped[UUID | None] = mapped_column(_fk("crops.id"))
    geo_area_id: Mapped[UUID | None] = mapped_column(_fk("geo_areas.id"))
    period_type: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    unit_code: Mapped[str | None] = mapped_column(_fk("units.code"))
    method_code: Mapped[str] = mapped_column(String(80))
    method_version: Mapped[str] = mapped_column(String(40))
    input_observation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeatureSet(AgriBase):
    __tablename__ = "feature_sets"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeatureValue(AgriBase):
    __tablename__ = "feature_values"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    feature_set_id: Mapped[UUID] = mapped_column(_fk("feature_sets.id"))
    crop_id: Mapped[UUID] = mapped_column(_fk("crops.id"))
    geo_area_id: Mapped[UUID] = mapped_column(_fk("geo_areas.id"))
    period_type: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[date] = mapped_column(Date)
    feature_payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRun(AgriBase):
    __tablename__ = "model_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    model_code: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(20))
    feature_set_id: Mapped[UUID | None] = mapped_column(_fk("feature_sets.id"))
    training_start: Mapped[date | None] = mapped_column(Date)
    training_end: Mapped[date | None] = mapped_column(Date)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    code_version: Mapped[str | None] = mapped_column(String(64))
    data_snapshot: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(200))


class Forecast(AgriBase):
    __tablename__ = "forecasts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    model_run_id: Mapped[UUID] = mapped_column(_fk("model_runs.id"))
    measure_code: Mapped[str] = mapped_column(_fk("measures.code"))
    crop_id: Mapped[UUID] = mapped_column(_fk("crops.id"))
    geo_area_id: Mapped[UUID] = mapped_column(_fk("geo_areas.id"))
    period_type: Mapped[str] = mapped_column(String(10))
    target_period_start: Mapped[date] = mapped_column(Date)
    horizon: Mapped[int] = mapped_column(Integer)
    point: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    lower: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    upper: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    interval_level: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    unit_code: Mapped[str] = mapped_column(_fk("units.code"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelEvaluation(AgriBase):
    __tablename__ = "model_evaluations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    model_run_id: Mapped[UUID] = mapped_column(_fk("model_runs.id"))
    metric_code: Mapped[str] = mapped_column(String(40))
    value: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    window_start: Mapped[date | None] = mapped_column(Date)
    window_end: Mapped[date | None] = mapped_column(Date)
    baseline_model_code: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
