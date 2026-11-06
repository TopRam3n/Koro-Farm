"""forecast lineage and explicit rights decisions for derived data (R1 WP5 review correction)

Revision ID: 0030_forecast_lineage
Revises: 0029_agricultural_intelligence

PostgreSQL only (like 0029). Additive; nothing existing changes and no row is inserted.
* agri.model_run_inputs: the observations each model run was trained or evaluated on, one row per observation. With
  observations -> datasets -> sources this gives every forecast a traceable source lineage (the earlier
  model_runs.data_snapshot JSON is kept as it was).
* agri.derived_rights_decisions: append-only, explicit decisions about what may be done with a model run's derived
  output (for example EXTERNAL_LLM: sending its forecasts to an external model provider), with the basis, the source
  licence statuses seen when deciding, who decided and the approval reference. The current decision is the newest row
  per run and purpose. Code never infers a derived-data decision from the source licences: no decision means no.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_forecast_lineage"
down_revision: Union[str, None] = "0029_agricultural_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = """
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

revoke all on agri.model_run_inputs, agri.derived_rights_decisions from public;
"""

CLIENT_ROLES_SQL = """
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
$$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(UPGRADE_SQL)
    op.execute(CLIENT_ROLES_SQL)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
do $$
begin
    if exists (select 1 from agri.derived_rights_decisions) or exists (select 1 from agri.model_run_inputs) then
        raise exception 'lineage or rights decisions are recorded; refusing to drop them (export them deliberately first)';
    end if;
end
$$;
drop table agri.derived_rights_decisions;
drop table agri.model_run_inputs;
""")
