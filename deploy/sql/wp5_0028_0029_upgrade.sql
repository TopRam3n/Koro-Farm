BEGIN;

-- Running upgrade 0027_supabase_data_api_hardening -> 0028_notifications_consent

CREATE TABLE contact_consents (
    id UUID NOT NULL, 
    organization_id UUID NOT NULL, 
    subject_type VARCHAR(20) NOT NULL, 
    subject_id UUID NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    address VARCHAR(320) NOT NULL, 
    state VARCHAR(20) NOT NULL, 
    purposes JSON NOT NULL, 
    wording_version VARCHAR(40) NOT NULL, 
    how_given VARCHAR(200) NOT NULL, 
    evidence_reference VARCHAR(500), 
    supersedes_id UUID, 
    recorded_by_user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_contact_consent_subject_type CHECK (subject_type in ('FARMER', 'BUYER')), 
    CONSTRAINT ck_contact_consent_channel CHECK (channel in ('SMS', 'WHATSAPP', 'EMAIL')), 
    CONSTRAINT ck_contact_consent_state CHECK (state in ('GRANTED', 'WITHDRAWN')), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(supersedes_id) REFERENCES contact_consents (id)
);

CREATE INDEX ix_contact_consents_organization_id ON contact_consents (organization_id);

CREATE INDEX ix_contact_consents_subject_id ON contact_consents (subject_id);

CREATE INDEX ix_contact_consents_current ON contact_consents (organization_id, subject_type, subject_id, channel, created_at);

CREATE TABLE notifications (
    id UUID NOT NULL, 
    organization_id UUID NOT NULL, 
    source_event_id UUID, 
    requirement_id UUID, 
    template_key VARCHAR(60) NOT NULL, 
    template_version INTEGER NOT NULL, 
    purpose VARCHAR(40) NOT NULL, 
    recipient_type VARCHAR(20) NOT NULL, 
    recipient_id UUID NOT NULL, 
    channel VARCHAR(20), 
    consent_id UUID, 
    body VARCHAR(2000) NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    provider VARCHAR(40), 
    provider_message_id VARCHAR(200), 
    attempts INTEGER DEFAULT '0' NOT NULL, 
    last_error VARCHAR(500), 
    next_attempt_at TIMESTAMP WITH TIME ZONE, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_notification_per_event_recipient UNIQUE (source_event_id, template_key, recipient_type, recipient_id), 
    CONSTRAINT ck_notification_attempts CHECK (attempts >= 0), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(source_event_id) REFERENCES domain_events (id), 
    FOREIGN KEY(requirement_id) REFERENCES requirements (id), 
    FOREIGN KEY(consent_id) REFERENCES contact_consents (id)
);

CREATE INDEX ix_notifications_organization_id ON notifications (organization_id);

CREATE INDEX ix_notifications_source_event_id ON notifications (source_event_id);

CREATE INDEX ix_notifications_requirement_id ON notifications (requirement_id);

CREATE INDEX ix_notifications_status ON notifications (status);

CREATE INDEX ix_notifications_due ON notifications (status, next_attempt_at);

CREATE TABLE notification_status_events (
    id UUID NOT NULL, 
    notification_id UUID NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    detail VARCHAR(500), 
    provider VARCHAR(40), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(notification_id) REFERENCES notifications (id)
);

CREATE INDEX ix_notification_status_events_notification_id ON notification_status_events (notification_id);

do $$
declare
    item text;
begin
    if not exists (select 1 from pg_roles where rolname in ('anon', 'authenticated', 'service_role')) then
        return;
    end if;
    foreach item in array array['contact_consents', 'notifications', 'notification_status_events'] loop
        execute format('alter table public.%I enable row level security', item);
    end loop;
end
$$;;

UPDATE alembic_version SET version_num='0028_notifications_consent' WHERE alembic_version.version_num = '0027_supabase_data_api_hardening';

-- Running upgrade 0028_notifications_consent -> 0029_agricultural_intelligence

do $$
begin
    if not exists (select 1 from pg_namespace where nspname = 'agri')
       and not has_database_privilege(current_database(), 'CREATE') then
        raise exception 'migration 0029 creates the agri schema: the migration role needs CREATE on database % (GRANT CREATE ON DATABASE ... TO <migration role>)', current_database();
    end if;
end
$$;;

create schema if not exists agri;
comment on schema agri is 'KoroFarm agricultural intelligence: public statistics, provenance and forecasts. Separate from operational trade data.';

create table agri.sources (
    id uuid primary key,
    code varchar(60) not null unique,
    name varchar(200) not null,
    publisher varchar(200) not null,
    homepage_url varchar(500),
    licence_name varchar(120),
    licence_url varchar(500),
    licence_review_status varchar(30) not null default 'NOT_REVIEWED',
    reuse_conditions text,
    attribution_text text,
    contact varchar(300),
    active boolean not null default true,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_sources_licence_review check (licence_review_status in
        ('NOT_REVIEWED', 'PERMISSION_REQUIRED', 'PERMISSION_REQUESTED', 'APPROVED', 'REJECTED'))
);

create table agri.datasets (
    id uuid primary key,
    source_id uuid not null references agri.sources (id),
    code varchar(80) not null,
    title varchar(300) not null,
    landing_url varchar(500),
    format varchar(20) not null,
    frequency varchar(20) not null,
    geographic_level varchar(30) not null,
    measures jsonb not null default '[]'::jsonb,
    notes text,
    created_at timestamptz not null default now(),
    constraint uq_datasets_source_code unique (source_id, code),
    constraint ck_datasets_format check (format in ('PDF', 'CSV', 'XLSX', 'API', 'HTML')),
    constraint ck_datasets_frequency check (frequency in ('ANNUAL', 'QUARTERLY', 'MONTHLY', 'IRREGULAR')),
    constraint ck_datasets_level check (geographic_level in ('COUNTRY', 'PARISH', 'REGION', 'EXTENSION_AREA', 'MIXED'))
);

create table agri.publications (
    id uuid primary key,
    dataset_id uuid not null references agri.datasets (id),
    version_label varchar(120) not null,
    period_label varchar(120),
    published_on date,
    retrieved_at timestamptz not null,
    retrieval_url varchar(500),
    file_name varchar(300),
    content_sha256 char(64) not null,
    byte_size bigint,
    retrieved_by varchar(200) not null,
    status varchar(20) not null default 'RETRIEVED',
    supersedes_publication_id uuid references agri.publications (id),
    notes text,
    created_at timestamptz not null default now(),
    constraint uq_publications_dataset_content unique (dataset_id, content_sha256),
    constraint ck_publications_status check (status in ('RETRIEVED', 'PARSED', 'SUPERSEDED', 'WITHDRAWN')),
    constraint ck_publications_sha256 check (content_sha256 ~ '^[0-9a-f]{64}$'),
    constraint ck_publications_not_self check (supersedes_publication_id is null or supersedes_publication_id <> id)
);
create index ix_publications_dataset on agri.publications (dataset_id);

create table agri.units (
    code varchar(30) primary key,
    dimension varchar(20) not null,
    canonical_code varchar(30) not null,
    factor_to_canonical numeric(24, 12) not null,
    description varchar(200) not null,
    constraint ck_units_dimension check (dimension in ('AREA', 'MASS', 'YIELD', 'PRICE_PER_MASS', 'COUNT', 'RATIO')),
    constraint ck_units_factor check (factor_to_canonical > 0)
);

create table agri.measures (
    code varchar(40) primary key,
    name varchar(120) not null,
    canonical_unit_code varchar(30) not null references agri.units (code),
    definition text not null,
    non_negative boolean not null default true
);

create table agri.crops (
    id uuid primary key,
    code varchar(64) not null unique,
    name varchar(200) not null,
    scientific_name varchar(200),
    category varchar(60),
    operational_crop_code varchar(64),
    fao_item_code integer,
    fao_item_code_verified boolean not null default false,
    created_at timestamptz not null default now()
);

create table agri.crop_aliases (
    id uuid primary key,
    crop_id uuid not null references agri.crops (id),
    source_id uuid references agri.sources (id),
    alias varchar(200) not null,
    alias_normalized varchar(200) not null,
    created_at timestamptz not null default now()
);
create unique index uq_crop_aliases_source_alias on agri.crop_aliases
    (coalesce(source_id, '00000000-0000-0000-0000-000000000000'::uuid), alias_normalized);

create table agri.geo_areas (
    id uuid primary key,
    code varchar(40) not null unique,
    name varchar(200) not null,
    level varchar(30) not null,
    parent_id uuid references agri.geo_areas (id),
    iso_3166_code varchar(10),
    m49_code varchar(10),
    fao_area_code integer,
    valid_from date,
    valid_to date,
    created_at timestamptz not null default now(),
    constraint ck_geo_areas_level check (level in ('COUNTRY', 'PARISH', 'REGION', 'EXTENSION_AREA')),
    constraint ck_geo_areas_validity check (valid_to is null or valid_from is null or valid_to >= valid_from)
);

create table agri.geo_aliases (
    id uuid primary key,
    geo_area_id uuid not null references agri.geo_areas (id),
    source_id uuid references agri.sources (id),
    alias varchar(200) not null,
    alias_normalized varchar(200) not null,
    created_at timestamptz not null default now()
);
create unique index uq_geo_aliases_source_alias on agri.geo_aliases
    (coalesce(source_id, '00000000-0000-0000-0000-000000000000'::uuid), alias_normalized);

create table agri.ingestion_runs (
    id uuid primary key,
    dataset_id uuid not null references agri.datasets (id),
    publication_id uuid references agri.publications (id),
    idempotency_key varchar(200) not null unique,
    parser_code varchar(80) not null,
    parser_version varchar(40) not null,
    mode varchar(10) not null,
    status varchar(20) not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    rows_read integer not null default 0,
    rows_accepted integer not null default 0,
    rows_rejected integer not null default 0,
    rows_duplicate integer not null default 0,
    operator varchar(200) not null,
    notes text,
    constraint ck_ingestion_runs_mode check (mode in ('DRY_RUN', 'APPLY')),
    constraint ck_ingestion_runs_status check (status in ('RUNNING', 'SUCCEEDED', 'FAILED', 'REJECTED')),
    constraint ck_ingestion_runs_counts check (rows_read >= 0 and rows_accepted >= 0 and rows_rejected >= 0 and rows_duplicate >= 0)
);

create table agri.raw_observations (
    id uuid primary key,
    ingestion_run_id uuid not null references agri.ingestion_runs (id),
    publication_id uuid not null references agri.publications (id),
    row_number integer not null,
    raw jsonb not null,
    row_sha256 char(64) not null,
    created_at timestamptz not null default now(),
    constraint uq_raw_observations_publication_row unique (publication_id, row_sha256)
);
create index ix_raw_observations_run on agri.raw_observations (ingestion_run_id);

create table agri.validation_issues (
    id uuid primary key,
    ingestion_run_id uuid not null references agri.ingestion_runs (id),
    raw_observation_id uuid references agri.raw_observations (id),
    row_number integer,
    rule_code varchar(80) not null,
    severity varchar(10) not null,
    field varchar(80),
    message varchar(1000) not null,
    created_at timestamptz not null default now(),
    constraint ck_validation_issues_severity check (severity in ('ERROR', 'WARNING', 'INFO'))
);
create index ix_validation_issues_run on agri.validation_issues (ingestion_run_id);

create table agri.observations (
    id uuid primary key,
    dataset_id uuid not null references agri.datasets (id),
    publication_id uuid not null references agri.publications (id),
    raw_observation_id uuid references agri.raw_observations (id),
    measure_code varchar(40) not null references agri.measures (code),
    crop_id uuid not null references agri.crops (id),
    geo_area_id uuid not null references agri.geo_areas (id),
    period_type varchar(10) not null,
    period_start date not null,
    period_end date not null,
    value numeric(24, 6) not null,
    unit_code varchar(30) not null references agri.units (code),
    value_canonical numeric(28, 10) not null,
    canonical_unit_code varchar(30) not null references agri.units (code),
    status varchar(20) not null,
    quality_flag varchar(40),
    source_flag varchar(20),
    revision_number integer not null default 1,
    supersedes_id uuid references agri.observations (id),
    is_current boolean not null default true,
    recorded_at timestamptz not null default now(),
    constraint ck_observations_period_type check (period_type in ('YEAR', 'QUARTER', 'MONTH')),
    constraint ck_observations_period check (period_end >= period_start),
    constraint ck_observations_value check (value >= 0 and value_canonical >= 0),
    constraint ck_observations_status check (status in ('PROVISIONAL', 'REVISED', 'FINAL', 'ESTIMATE')),
    constraint ck_observations_revision check (revision_number >= 1)
);
create unique index uq_observations_current on agri.observations
    (dataset_id, measure_code, crop_id, geo_area_id, period_type, period_start) where is_current;
create index ix_observations_series on agri.observations (measure_code, crop_id, geo_area_id, period_start);
create index ix_observations_publication on agri.observations (publication_id);

create table agri.faostat_observations (
    id uuid primary key,
    publication_id uuid not null references agri.publications (id),
    raw_observation_id uuid references agri.raw_observations (id),
    area_code integer not null,
    area_m49 varchar(10),
    area_name varchar(200) not null,
    item_code integer not null,
    item_cpc varchar(20),
    item_name varchar(200) not null,
    element_code integer not null,
    element_name varchar(200) not null,
    year integer not null,
    unit varchar(40) not null,
    value numeric(24, 6),
    flag varchar(10),
    note text,
    created_at timestamptz not null default now(),
    constraint uq_faostat_observation unique (publication_id, area_code, item_code, element_code, year),
    constraint ck_faostat_year check (year between 1900 and 2200)
);
create index ix_faostat_series on agri.faostat_observations (area_code, item_code, element_code, year);

create table agri.derived_indicators (
    id uuid primary key,
    indicator_code varchar(80) not null,
    crop_id uuid references agri.crops (id),
    geo_area_id uuid references agri.geo_areas (id),
    period_type varchar(10) not null,
    period_start date not null,
    value numeric(28, 10),
    unit_code varchar(30) references agri.units (code),
    method_code varchar(80) not null,
    method_version varchar(40) not null,
    input_observation_ids jsonb not null default '[]'::jsonb,
    computed_at timestamptz not null default now(),
    constraint uq_derived_indicator unique (indicator_code, crop_id, geo_area_id, period_type, period_start, method_version)
);

create table agri.feature_sets (
    id uuid primary key,
    code varchar(80) not null,
    version integer not null,
    definition jsonb not null,
    created_at timestamptz not null default now(),
    constraint uq_feature_sets_code_version unique (code, version),
    constraint ck_feature_sets_version check (version >= 1)
);

create table agri.feature_values (
    id uuid primary key,
    feature_set_id uuid not null references agri.feature_sets (id),
    crop_id uuid not null references agri.crops (id),
    geo_area_id uuid not null references agri.geo_areas (id),
    period_type varchar(10) not null,
    period_start date not null,
    feature_payload jsonb not null,
    created_at timestamptz not null default now(),
    constraint uq_feature_values_key unique (feature_set_id, crop_id, geo_area_id, period_type, period_start)
);

create table agri.model_runs (
    id uuid primary key,
    model_code varchar(80) not null,
    model_version varchar(40) not null,
    purpose varchar(20) not null,
    feature_set_id uuid references agri.feature_sets (id),
    training_start date,
    training_end date,
    parameters jsonb not null default '{}'::jsonb,
    code_version varchar(64),
    data_snapshot jsonb not null default '[]'::jsonb,
    status varchar(20) not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    created_by varchar(200) not null,
    constraint ck_model_runs_purpose check (purpose in ('BACKTEST', 'FORECAST', 'EVALUATION')),
    constraint ck_model_runs_status check (status in ('RUNNING', 'SUCCEEDED', 'FAILED')),
    constraint ck_model_runs_window check (training_end is null or training_start is null or training_end >= training_start)
);

create table agri.forecasts (
    id uuid primary key,
    model_run_id uuid not null references agri.model_runs (id),
    measure_code varchar(40) not null references agri.measures (code),
    crop_id uuid not null references agri.crops (id),
    geo_area_id uuid not null references agri.geo_areas (id),
    period_type varchar(10) not null,
    target_period_start date not null,
    horizon integer not null,
    point numeric(28, 10) not null,
    lower numeric(28, 10),
    upper numeric(28, 10),
    interval_level numeric(4, 3),
    unit_code varchar(30) not null references agri.units (code),
    created_at timestamptz not null default now(),
    constraint uq_forecast_target unique (model_run_id, measure_code, crop_id, geo_area_id, period_type, target_period_start),
    constraint ck_forecasts_horizon check (horizon >= 1),
    constraint ck_forecasts_interval check ((lower is null or lower <= point) and (upper is null or point <= upper)),
    constraint ck_forecasts_level check (interval_level is null or (interval_level > 0 and interval_level < 1))
);

create table agri.model_evaluations (
    id uuid primary key,
    model_run_id uuid not null references agri.model_runs (id),
    metric_code varchar(40) not null,
    value numeric(28, 10) not null,
    window_start date,
    window_end date,
    baseline_model_code varchar(80),
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

revoke all on schema agri from public;
revoke all on all tables in schema agri from public;
revoke all on all sequences in schema agri from public;
alter default privileges in schema agri revoke all on tables from public;
alter default privileges in schema agri revoke all on sequences from public;;

do $$
declare
    grantees text;
begin
    select string_agg(quote_ident(rolname), ', ' order by rolname) into grantees
    from pg_roles where rolname in ('anon', 'authenticated', 'service_role');
    if grantees is null then
        return;
    end if;
    execute format('revoke all on schema agri from %s', grantees);
    execute format('revoke all on all tables in schema agri from %s', grantees);
    execute format('revoke all on all sequences in schema agri from %s', grantees);
    execute format('alter default privileges in schema agri revoke all on tables from %s', grantees);
    execute format('alter default privileges in schema agri revoke all on sequences from %s', grantees);
    execute format('alter default privileges in schema agri revoke all on functions from %s', grantees);
end
$$;;

UPDATE alembic_version SET version_num='0029_agricultural_intelligence' WHERE alembic_version.version_num = '0028_notifications_consent';

COMMIT;

