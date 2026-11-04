"""keep KoroFarm's tables out of Supabase's Data API (no client-role grants; row-level security on)

Revision ID: 0026_supabase_data_api_lockdown
Revises: 0025_physical_event_times

Applies only on PostgreSQL where Supabase's client roles (anon, authenticated, service_role) exist; elsewhere it
does nothing. No rows are read or changed.
* Revokes every privilege those roles hold on the public schema's tables, sequences and functions, and the default
  privileges that would grant them on objects the migration role creates later.
* Enables row-level security, with no policies, on every public table the migration role owns. The owner (the role
  the backend connects as) is not subject to it; the client roles see no rows.
See app/infrastructure/database/data_api.py. Downgrade does nothing: re-exposing tables is never automated.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026_supabase_data_api_lockdown"
down_revision: Union[str, None] = "0025_physical_event_times"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOCKDOWN = """
do $$
declare
    grantees text;
    item record;
begin
    select string_agg(quote_ident(rolname), ', ' order by rolname) into grantees
    from pg_roles where rolname in ('anon', 'authenticated', 'service_role');
    if grantees is null then
        return;
    end if;
    execute format('revoke all on all tables in schema public from %s', grantees);
    execute format('revoke all on all sequences in schema public from %s', grantees);
    execute format('revoke all on all functions in schema public from %s', grantees);
    execute format('alter default privileges in schema public revoke all on tables from %s', grantees);
    execute format('alter default privileges in schema public revoke all on sequences from %s', grantees);
    execute format('alter default privileges in schema public revoke all on functions from %s', grantees);
    for item in
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity
          and pg_get_userbyid(c.relowner) = current_user
    loop
        execute format('alter table public.%I enable row level security', item.relname);
    end loop;
end
$$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(LOCKDOWN)


def downgrade() -> None:
    pass
