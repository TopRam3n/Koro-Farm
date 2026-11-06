BEGIN;

-- Running upgrade 0029_agricultural_intelligence -> 0030_forecast_lineage

create table agri.model_run_inputs (
    model_run_id uuid not null references agri.model_runs (id),
    observation_id uuid not null references agri.observations (id),
    created_at timestamptz not null default now(),
    constraint pk_model_run_inputs primary key (model_run_id, observation_id)
);
create index ix_model_run_inputs_observation on agri.model_run_inputs (observation_id);

create table agri.derived_rights_decisions (
    id uuid primary key,
    model_run_id uuid not null references agri.model_runs (id),
    purpose varchar(40) not null,
    decision varchar(20) not null,
    basis text not null,
    source_statuses jsonb not null default '[]'::jsonb,
    decided_by varchar(200) not null,
    approval_reference varchar(200),
    created_at timestamptz not null default now(),
    constraint ck_derived_rights_purpose check (purpose in ('EXTERNAL_LLM', 'PUBLICATION', 'COMMERCIAL_USE')),
    constraint ck_derived_rights_decision check (decision in ('PERMITTED', 'NOT_PERMITTED')),
    constraint ck_derived_rights_reference check (decision <> 'PERMITTED' or coalesce(approval_reference, '') <> '')
);
create index ix_derived_rights_run_purpose on agri.derived_rights_decisions (model_run_id, purpose, created_at);

revoke all on agri.model_run_inputs, agri.derived_rights_decisions from public;;

do $$
declare
    grantees text;
begin
    select string_agg(quote_ident(rolname), ', ' order by rolname) into grantees
    from pg_roles where rolname in ('anon', 'authenticated', 'service_role');
    if grantees is null then
        return;
    end if;
    execute format('revoke all on agri.model_run_inputs, agri.derived_rights_decisions from %s', grantees);
end
$$;;

UPDATE alembic_version SET version_num='0030_forecast_lineage' WHERE alembic_version.version_num = '0029_agricultural_intelligence';

COMMIT;

